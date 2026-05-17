import os
import json
import shutil
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

from config import BASE_DIR, UPLOAD_DIR, OUTPUT_DIR, IMAGES_DIR, CLAUDE_API_KEY
from models import (
    init_db, insert_paper, update_paper, get_all_papers,
    get_paper, delete_paper, insert_presentation, get_all_presentations,
    get_setting, set_setting,
)
from parser import parse_pdf, extract_images
from searcher import search_papers
from skills import FIGURE_SYSTEM_PROMPT, POLISH_SYSTEM_PROMPT, figure_prompt, polish_prompt
from analyzer import analyze_paper, generate_slide_content, chat_about_paper, call_claude, CHAT_SYSTEM_PROMPT, chat_about_multiple_papers, MULTI_CHAT_SYSTEM_PROMPT, chat_assistant
from generator import create_presentation, append_to_presentation

app = FastAPI(title="论文助手")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs("static", exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
env = Environment(loader=FileSystemLoader(os.path.join(BASE_DIR, "templates")), auto_reload=False)
env.cache = None

init_db()


def _render(request: Request, template: str, **kwargs) -> HTMLResponse:
    tpl = env.get_template(template)
    return HTMLResponse(tpl.render(request=request, **kwargs))


def _parse_json_column(paper, column):
    """Parse a JSON column from a paper dict, returning a list."""
    val = paper.get(column, "")
    if not val or val in ("[]", "0", ""):
        return []
    try:
        parsed = json.loads(val)
        if isinstance(parsed, int):
            return []
        if isinstance(parsed, list):
            return parsed
        return []
    except (json.JSONDecodeError, TypeError):
        return []


def _api_key_available():
    return bool(get_setting("api_key") or CLAUDE_API_KEY)


def _parse_sections(paper):
    """Parse sections JSON, handling both list and {sections: [...]} formats."""
    val = paper.get("sections", "")
    if not val or val == "[]":
        return []
    try:
        parsed = json.loads(val)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return parsed.get("sections", [])
        return []
    except (json.JSONDecodeError, TypeError):
        return []


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    papers = get_all_papers()
    api_key_set = _api_key_available()
    return _render(request, "index.html", papers=papers, api_key_set=api_key_set, active_nav="ppt")


@app.get("/paper/{paper_id}", response_class=HTMLResponse)
async def paper_detail(request: Request, paper_id: int):
    paper = get_paper(paper_id)
    if not paper:
        return HTMLResponse("Paper not found", status_code=404)

    sections_data = _parse_sections(paper)
    formulas = _parse_json_column(paper, "formulas")
    figures = _parse_json_column(paper, "proper_figures")
    images = _parse_json_column(paper, "images")

    return _render(request, "detail.html", paper=paper, sections_data=sections_data,
                   formulas=formulas, figures=figures, images=images)


@app.post("/upload")
async def upload_paper(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        return RedirectResponse("/", status_code=303)

    filepath = os.path.join(UPLOAD_DIR, file.filename)
    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        parsed = parse_pdf(filepath)
        paper_id = insert_paper(
            filename=file.filename,
            title=parsed["title"],
            authors=parsed["authors"],
            year=parsed["year"],
            abstract=parsed["abstract"],
            full_text=parsed["full_text"],
        )

        # Extract embedded images from PDF
        try:
            images = extract_images(filepath, paper_id, IMAGES_DIR)
        except Exception as e:
            print(f"Image extraction failed: {e}")
            images = []

        update_paper(
            paper_id,
            images=json.dumps(images, ensure_ascii=False),
            status="uploaded",
        )
    except Exception as e:
        print(f"PDF parsing failed: {e}")
        return RedirectResponse("/", status_code=303)

    return RedirectResponse("/", status_code=303)


@app.post("/delete/{paper_id}")
async def delete_paper_route(paper_id: int):
    paper = get_paper(paper_id)
    if paper:
        filepath = os.path.join(UPLOAD_DIR, paper["filename"])
        if os.path.exists(filepath):
            os.remove(filepath)
        delete_paper(paper_id)
    return RedirectResponse("/", status_code=303)


@app.get("/generate", response_class=HTMLResponse)
async def generate_page(request: Request, paper_ids: str = ""):
    if not paper_ids:
        return RedirectResponse("/")

    ids = [int(pid) for pid in paper_ids.split(",") if pid.strip().isdigit()]
    papers = []
    for pid in ids:
        p = get_paper(pid)
        if p:
            papers.append(p)

    presentations = get_all_presentations()
    for pres in presentations:
        pres["basename"] = os.path.basename(pres.get("pptx_path", ""))
    api_key_set = _api_key_available()
    return _render(request, "generate.html", papers=papers, paper_ids=ids,
                   api_key_set=api_key_set, presentations=presentations)


@app.post("/generate")
async def generate_ppt(
    request: Request,
    paper_ids: list[int] = Form(...),
    slide_count: int = Form(4),
    append_to: str = Form(""),
):
    if not _api_key_available():
        return RedirectResponse("/", status_code=303)

    slide_count = max(2, min(6, slide_count))
    paper_slides = []

    for pid in paper_ids:
        paper = get_paper(pid)
        if not paper:
            continue

        paper_data = {
            "title": paper["title"], "authors": paper["authors"],
            "year": paper["year"], "abstract": paper.get("abstract", ""),
            "overview": paper.get("overview", ""), "paper_id": pid,
        }

        sections_data = _parse_sections(paper)
        if sections_data:
            paper_data["sections"] = sections_data

        formulas = _parse_json_column(paper, "formulas")
        if formulas:
            paper_data["formulas"] = formulas

        figures = _parse_json_column(paper, "proper_figures")
        if figures:
            paper_data["figures"] = figures

        images = _parse_json_column(paper, "images")
        if images:
            paper_data["images"] = images

        try:
            content = generate_slide_content(paper_data, num_slides=slide_count)
            paper_slides.append(content)
        except Exception as e:
            print(f"Slide generation failed for paper {pid}: {e}")

    if not paper_slides:
        return HTMLResponse("No valid papers to generate slides from.", status_code=400)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_name = f"group_meeting_{timestamp}.pptx"

    if append_to:
        append_path = os.path.join(OUTPUT_DIR, append_to)
        if os.path.exists(append_path):
            pptx_path = append_to_presentation(paper_slides, append_path, output_name)
        else:
            pptx_path = create_presentation(paper_slides, output_name)
    else:
        pptx_path = create_presentation(paper_slides, output_name)

    insert_presentation(
        name=f"组会汇报 {timestamp}",
        paper_ids=paper_ids,
        slides_json=json.dumps(paper_slides, ensure_ascii=False),
        pptx_path=pptx_path,
    )

    return FileResponse(pptx_path, filename=os.path.basename(pptx_path),
                        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")


@app.get("/download/{filename}")
async def download(filename: str):
    path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(path):
        return HTMLResponse("File not found", status_code=404)
    return FileResponse(path, filename=filename,
                        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")


@app.get("/deepread", response_class=HTMLResponse)
async def deepread_index(request: Request):
    """Redirect to the first available 'done' paper, or show a prompt."""
    papers = get_all_papers()
    available = [p for p in papers if p.get("status") in ("done", "uploaded")]
    if available:
        return RedirectResponse(f"/deepread/{available[0]['id']}", status_code=303)

    api_key_set = _api_key_available()
    return _render(request, "deepread.html", paper=None, sections_data=[],
                   formulas=[], figures=[], images=[], all_papers=papers,
                   api_key_set=api_key_set, active_nav="deepread",
                   default_system_prompt=CHAT_SYSTEM_PROMPT)


@app.get("/deepread/{paper_id}", response_class=HTMLResponse)
async def deepread_page(request: Request, paper_id: int):
    paper = get_paper(paper_id)
    if not paper:
        return HTMLResponse("Paper not found", status_code=404)

    sections_data = _parse_sections(paper)
    formulas = _parse_json_column(paper, "formulas")
    figures = _parse_json_column(paper, "proper_figures")
    images = _parse_json_column(paper, "images")
    all_papers = get_all_papers()
    api_key_set = _api_key_available()

    return _render(request, "deepread.html", paper=paper, sections_data=sections_data,
                   formulas=formulas, figures=figures, images=images,
                   all_papers=all_papers, api_key_set=api_key_set, active_nav="deepread",
                   default_system_prompt=CHAT_SYSTEM_PROMPT)


@app.post("/deepread/analyze/{paper_id}")
async def deepread_analyze(request: Request, paper_id: int):
    """Trigger AI analysis for a paper (called when user clicks '开始解析' in deepread)."""
    paper = get_paper(paper_id)
    if not paper:
        return JSONResponse({"error": "Paper not found"}, status_code=404)

    if not _api_key_available():
        return JSONResponse({"error": "CLAUDE_API_KEY is not set"}, status_code=500)

    full_text = paper.get("full_text", "")
    if not full_text:
        filepath = os.path.join(UPLOAD_DIR, paper["filename"])
        if os.path.exists(filepath):
            try:
                parsed = parse_pdf(filepath)
                full_text = parsed["full_text"]
                update_paper(paper_id, full_text=full_text)
            except Exception as e:
                return JSONResponse({"error": f"Failed to re-parse PDF: {e}"}, status_code=500)

    if not full_text:
        return JSONResponse({"error": "No text content available for this paper"}, status_code=400)

    update_paper(paper_id, status="processing")
    try:
        analysis = analyze_paper(full_text)
        update_paper(
            paper_id,
            title=analysis.get("title", paper.get("title", "")),
            authors=analysis.get("authors", paper.get("authors", "")),
            year=analysis.get("year", paper.get("year")),
            abstract=analysis.get("abstract", paper.get("abstract", "")),
            overview=analysis.get("overview", ""),
            sections=json.dumps(analysis.get("sections", []), ensure_ascii=False),
            formulas=json.dumps(analysis.get("formulas", []), ensure_ascii=False),
            proper_figures=json.dumps(analysis.get("figures", []), ensure_ascii=False),
            status="done",
        )
        return JSONResponse({"status": "done"})
    except Exception as e:
        update_paper(paper_id, status="error")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/deepread/chat/{paper_id}")
async def deepread_chat(request: Request, paper_id: int):
    paper = get_paper(paper_id)
    if not paper:
        return JSONResponse({"error": "Paper not found"}, status_code=404)

    body = await request.json()
    messages = body.get("messages", [])
    question = body.get("question", "")
    custom_system_prompt = body.get("system_prompt", "").strip()

    if not question:
        return JSONResponse({"error": "Question is required"}, status_code=400)

    sections_data = _parse_sections(paper)
    formulas = _parse_json_column(paper, "formulas")
    figures = _parse_json_column(paper, "proper_figures")

    # Build paper context string
    context_parts = [
        f"标题：{paper.get('title', '')}",
        f"作者：{paper.get('authors', '')}",
        f"年份：{paper.get('year', '')}",
        f"摘要：{paper.get('abstract', '')}",
    ]
    if paper.get("overview"):
        context_parts.append(f"AI梗概：{paper.get('overview')}")
    if sections_data:
        sec_lines = []
        for sec in sections_data:
            sec_lines.append(f"- {sec.get('heading', '')}: {sec.get('summary', '')}")
            if sec.get("key_points"):
                for pt in sec["key_points"]:
                    sec_lines.append(f"  * {pt}")
        context_parts.append("论文结构：\n" + "\n".join(sec_lines))
    if formulas:
        context_parts.append("核心公式：\n" + "\n".join(formulas))
    if figures:
        context_parts.append("论文图表描述：\n" + "\n".join(figures))

    paper_context = "\n\n".join(context_parts)

    try:
        answer = chat_about_paper(paper_context, messages, question,
                                  system_prompt=custom_system_prompt or None)
        return JSONResponse({"response": answer})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ===== Multi-Paper Discussion =====

@app.get("/discuss", response_class=HTMLResponse)
async def discuss_page(request: Request):
    papers = get_all_papers()
    available = [p for p in papers if p.get("status") == "done"]
    preselected = request.query_params.get("papers", "")
    preselected_ids = []
    if preselected:
        preselected_ids = [int(pid) for pid in preselected.split(",") if pid.strip().isdigit()]

    api_key_set = _api_key_available()
    return _render(request, "discuss.html",
                   all_papers=available, preselected_ids=preselected_ids,
                   api_key_set=api_key_set, active_nav="discuss",
                   default_system_prompt=MULTI_CHAT_SYSTEM_PROMPT)


@app.post("/discuss/chat")
async def discuss_chat(request: Request):
    if not _api_key_available():
        return JSONResponse({"error": "CLAUDE_API_KEY is not set"}, status_code=500)

    body = await request.json()
    paper_ids = body.get("paper_ids", [])
    messages = body.get("messages", [])
    question = body.get("question", "").strip()
    custom_system_prompt = body.get("system_prompt", "").strip()

    if not question:
        return JSONResponse({"error": "Question is required"}, status_code=400)
    if not paper_ids or len(paper_ids) < 2:
        return JSONResponse({"error": "Please select at least 2 papers"}, status_code=400)

    papers_context = []
    for pid in paper_ids:
        paper = get_paper(int(pid))
        if not paper:
            continue
        papers_context.append({
            "id": paper["id"],
            "title": paper.get("title", ""),
            "authors": paper.get("authors", ""),
            "year": paper.get("year"),
            "abstract": paper.get("abstract", ""),
            "overview": paper.get("overview", ""),
            "sections": paper.get("sections", "[]"),
            "formulas": paper.get("formulas", "[]"),
            "figures": paper.get("proper_figures", paper.get("figures", "[]")),
        })

    if len(papers_context) < 2:
        return JSONResponse({"error": "Need at least 2 valid papers"}, status_code=400)

    try:
        answer = chat_about_multiple_papers(papers_context, messages, question,
                                            system_prompt=custom_system_prompt or None)
        return JSONResponse({"response": answer})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/images/{paper_id}/{filename}")
async def serve_image(paper_id: int, filename: str):
    path = os.path.join(IMAGES_DIR, str(paper_id), filename)
    if not os.path.exists(path):
        return HTMLResponse("Image not found", status_code=404)
    return FileResponse(path)


@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request):
    api_key_set = _api_key_available()
    return _render(request, "search.html", api_key_set=api_key_set, active_nav="search")


@app.post("/api/search")
async def api_search(request: Request):
    body = await request.json()
    query = body.get("query", "").strip()
    limit = min(int(body.get("limit", 10)), 20)
    if not query:
        return JSONResponse({"results": []})
    try:
        results = search_papers(query, limit=limit)
        return JSONResponse({"results": results})
    except Exception as e:
        return JSONResponse({"error": str(e), "results": []}, status_code=500)


@app.post("/api/search/import")
async def api_search_import(request: Request):
    body = await request.json()
    paper_data = body.get("paper", {})
    if not paper_data or not paper_data.get("title"):
        return JSONResponse({"error": "Invalid paper data"}, status_code=400)

    title = paper_data.get("title", "")
    authors = paper_data.get("authors", "")
    year_str = paper_data.get("year", "")
    year = None
    try:
        year = int(year_str) if year_str else None
    except (ValueError, TypeError):
        year = None
    abstract = paper_data.get("abstract", "")
    url = paper_data.get("url", "")

    paper_id = insert_paper(
        filename=f"[search] {url}" if url else "[search]",
        title=title,
        authors=authors,
        year=year,
        abstract=abstract,
    )

    # Trigger AI analysis in background
    full_text = f"标题：{title}\n作者：{authors}\n年份：{year_str}\n摘要：{abstract}"
    if _api_key_available():
        try:
            analysis = analyze_paper(full_text)
            update_paper(
                paper_id,
                title=analysis.get("title", title),
                authors=analysis.get("authors", authors),
                year=analysis.get("year", year),
                abstract=analysis.get("abstract", abstract),
                overview=analysis.get("overview", ""),
                sections=json.dumps(analysis.get("sections", []), ensure_ascii=False),
                formulas=json.dumps(analysis.get("formulas", []), ensure_ascii=False),
                proper_figures=json.dumps(analysis.get("figures", []), ensure_ascii=False),
                images=json.dumps([], ensure_ascii=False),
                status="done",
            )
        except Exception as e:
            update_paper(paper_id, status="error")
            print(f"AI analysis failed for imported paper: {e}")
    else:
        update_paper(paper_id, images=json.dumps([], ensure_ascii=False), status="done")

    return JSONResponse({"paper_id": paper_id, "status": "imported"})


# ===== Figure Generation & Text Polishing =====

@app.get("/figure", response_class=HTMLResponse)
async def figure_page(request: Request):
    return _render(request, "figure.html", active_nav="figure")


@app.post("/api/figure")
async def api_figure(request: Request):
    body = await request.json()
    description = body.get("description", "").strip()
    data = body.get("data", "").strip()
    extra = body.get("extra_prompt", "").strip()
    if not description:
        return JSONResponse({"error": "Description is required"}, status_code=400)

    if not _api_key_available():
        return JSONResponse({"error": "CLAUDE_API_KEY is not set"}, status_code=500)

    try:
        code = call_claude(FIGURE_SYSTEM_PROMPT, figure_prompt(description, data, extra))
        return JSONResponse({"code": code})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/polish", response_class=HTMLResponse)
async def polish_page(request: Request):
    return _render(request, "polish.html", active_nav="polish")


@app.post("/api/polish")
async def api_polish(request: Request):
    body = await request.json()
    text = body.get("text", "").strip()
    extra = body.get("extra_prompt", "").strip()
    if not text:
        return JSONResponse({"error": "Text is required"}, status_code=400)

    if not _api_key_available():
        return JSONResponse({"error": "CLAUDE_API_KEY is not set"}, status_code=500)

    try:
        result = call_claude(POLISH_SYSTEM_PROMPT, polish_prompt(text, extra))
        return JSONResponse({"result": result})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/chat-assistant")
async def api_chat_assistant(request: Request):
    body = await request.json()
    question = body.get("question", "").strip()
    messages = body.get("messages", [])
    conversation_id = body.get("conversation_id", "")

    if not question:
        return JSONResponse({"error": "Question is required"}, status_code=400)

    if messages and len(messages) > 0:
        recent = messages[-8:]
        history_lines = []
        for msg in recent:
            role_label = "用户" if msg["role"] == "user" else "助手"
            history_lines.append(f"{role_label}：{msg['content']}")
        history = "\n".join(history_lines)
        query = f"对话历史：\n{history}\n\n用户最新问题：{question}"
    else:
        query = question

    try:
        result = chat_assistant(query, conversation_id)
        return JSONResponse({"response": result["answer"], "conversation_id": result["conversation_id"]})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return _render(request, "settings.html", active_nav="settings")


@app.get("/api/settings")
async def api_get_settings(request: Request):
    provider = get_setting("provider") or "deepseek"
    api_key = get_setting("api_key") or ""
    model = get_setting("model") or ""
    if not model:
        model = "deepseek-v4-pro" if provider == "deepseek" else "claude-sonnet-4-6"
    masked = ""
    if api_key:
        masked = api_key[:7] + "***" + api_key[-4:] if len(api_key) > 11 else "***"
    return JSONResponse({"provider": provider, "api_key_masked": masked, "model": model})


@app.post("/api/settings")
async def api_save_settings(request: Request):
    body = await request.json()
    provider = body.get("provider", "").strip()
    api_key = body.get("api_key", "").strip()
    model = body.get("model", "").strip()

    if provider:
        set_setting("provider", provider)
    if api_key:
        set_setting("api_key", api_key)
    if model:
        set_setting("model", model)

    from analyzer import clear_client_cache
    clear_client_cache()

    masked = ""
    if api_key:
        masked = api_key[:7] + "***" + api_key[-4:] if len(api_key) > 11 else "***"
    return JSONResponse({"status": "saved", "api_key_masked": masked})


@app.get("/publish", response_class=HTMLResponse)
async def publish_page(request: Request):
    return _render(request, "publish.html", active_nav="publish")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
