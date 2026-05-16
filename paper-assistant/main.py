import os
import json
import shutil
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import UPLOAD_DIR, OUTPUT_DIR, CLAUDE_API_KEY
from models import (
    init_db, insert_paper, update_paper, get_all_papers,
    get_paper, delete_paper, insert_presentation, get_all_presentations
)
from parser import parse_pdf
from analyzer import analyze_paper, generate_slide_content
from generator import create_presentation

app = FastAPI(title="论文助手")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs("static", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

init_db()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    papers = get_all_papers()
    api_key_set = bool(CLAUDE_API_KEY)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "papers": papers,
        "api_key_set": api_key_set,
    })


@app.get("/paper/{paper_id}", response_class=HTMLResponse)
async def paper_detail(request: Request, paper_id: int):
    paper = get_paper(paper_id)
    if not paper:
        return HTMLResponse("Paper not found", status_code=404)

    sections_data = []
    if paper.get("sections") and paper["sections"] != "[]":
        try:
            parsed = json.loads(paper["sections"])
            sections_data = parsed if isinstance(parsed, list) else parsed.get("sections", [])
        except (json.JSONDecodeError, TypeError):
            sections_data = []

    return templates.TemplateResponse("detail.html", {
        "request": request,
        "paper": paper,
        "sections_data": sections_data,
    })


@app.post("/upload")
async def upload_paper(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        return RedirectResponse("/", status_code=303)

    filepath = os.path.join(UPLOAD_DIR, file.filename)
    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        # Step 1: Parse PDF with PyMuPDF
        parsed = parse_pdf(filepath)
        paper_id = insert_paper(
            filename=file.filename,
            title=parsed["title"],
            authors=parsed["authors"],
            year=parsed["year"],
            abstract=parsed["abstract"],
        )

        # Step 2: Analyze with Claude API (if available)
        if CLAUDE_API_KEY:
            try:
                analysis = analyze_paper(parsed["full_text"])
                update_paper(
                    paper_id,
                    title=analysis.get("title", parsed["title"]),
                    authors=analysis.get("authors", parsed["authors"]),
                    year=analysis.get("year", parsed["year"]),
                    abstract=analysis.get("abstract", parsed["abstract"]),
                    sections=json.dumps(analysis.get("sections", []), ensure_ascii=False),
                    figures=json.dumps(parsed.get("figure_count", 0)),
                    status="done",
                )
            except Exception as e:
                update_paper(paper_id, status="error")
                print(f"Claude API analysis failed: {e}")
        else:
            update_paper(
                paper_id,
                sections=json.dumps([], ensure_ascii=False),
                status="done",
            )
    except Exception as e:
        print(f"PDF parsing failed: {e}")
        return RedirectResponse("/", status_code=303)

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

    api_key_set = bool(CLAUDE_API_KEY)
    return templates.TemplateResponse("generate.html", {
        "request": request,
        "papers": papers,
        "paper_ids": ids,
        "api_key_set": api_key_set,
    })


@app.post("/generate")
async def generate_ppt(request: Request, paper_ids: list[int] = Form(...)):
    if not CLAUDE_API_KEY:
        return RedirectResponse("/", status_code=303)

    paper_slides = []
    paper_meta = []

    for pid in paper_ids:
        paper = get_paper(pid)
        if not paper:
            continue

        paper_meta.append(paper)
        sections_str = paper.get("sections", "[]")

        # Use cached sections if available
        if sections_str and sections_str != "[]":
            try:
                cached = json.loads(sections_str)
                content = generate_slide_content({"sections": cached, "title": paper["title"],
                                                   "authors": paper["authors"], "year": paper["year"]})
                paper_slides.append(content)
                continue
            except Exception as e:
                print(f"Cached slide generation failed, re-parsing: {e}")

    if not paper_slides:
        return HTMLResponse("No valid papers to generate slides from.", status_code=400)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_name = f"group_meeting_{timestamp}.pptx"
    pptx_path = create_presentation(paper_slides, output_name)

    # Record in DB
    insert_presentation(
        name=f"组会汇报 {timestamp}",
        paper_ids=paper_ids,
        slides_json=json.dumps(paper_slides, ensure_ascii=False),
        pptx_path=pptx_path,
    )

    return FileResponse(pptx_path, filename=output_name,
                        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")


@app.get("/download/{filename}")
async def download(filename: str):
    path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(path):
        return HTMLResponse("File not found", status_code=404)
    return FileResponse(path, filename=filename,
                        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
