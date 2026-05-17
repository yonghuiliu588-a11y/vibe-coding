import json
import urllib.request
import urllib.error
from anthropic import Anthropic
from anthropic.types import TextBlock
from openai import OpenAI
from config import CLAUDE_API_KEY, DEEPSEEK_API_KEY, DIFY_BASE_URL, DIFY_PAPER_ANALYSIS_KEY, DIFY_SLIDE_GEN_KEY, DIFY_CHAT_ASSISTANT_KEY

# Module-level cached client
_CLIENT = None
_CLIENT_TYPE = None  # "deepseek" | "claude"


def _get_provider():
    """Return (provider_name, api_key, model) from user settings."""
    from models import get_setting
    provider = get_setting("provider") or "deepseek"
    api_key = get_setting("api_key") or ""
    model = get_setting("model") or ""

    if provider == "deepseek":
        if not model:
            model = "deepseek-v4-pro"
    else:
        if not model:
            model = "claude-sonnet-4-6"
    return provider, api_key, model


def clear_client_cache():
    global _CLIENT, _CLIENT_TYPE
    _CLIENT = None
    _CLIENT_TYPE = None


def _get_api_key():
    """Check whether user has configured an API key."""
    provider, api_key, _ = _get_provider()
    fallback = DEEPSEEK_API_KEY if provider == "deepseek" else CLAUDE_API_KEY
    return bool(api_key or fallback)


def _call_llm(system_prompt, messages, max_tokens=4096):
    """Unified LLM call – routes to DeepSeek or Claude based on user settings."""
    provider, api_key, model = _get_provider()
    if not api_key:
        api_key = DEEPSEEK_API_KEY if provider == "deepseek" else CLAUDE_API_KEY
    if not api_key:
        raise RuntimeError("API key not configured")

    global _CLIENT, _CLIENT_TYPE

    if provider == "deepseek":
        if _CLIENT is None or _CLIENT_TYPE != "deepseek":
            _CLIENT = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
            _CLIENT_TYPE = "deepseek"
        resp = _CLIENT.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system_prompt}] + messages,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content
    else:
        if _CLIENT is None or _CLIENT_TYPE != "claude":
            _CLIENT = Anthropic(api_key=api_key, timeout=600)
            _CLIENT_TYPE = "claude"
        resp = _CLIENT.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
        )
        for block in resp.content:
            if isinstance(block, TextBlock):
                return block.text
        return ""


def _dify_call(api_key, inputs):
    """Call a Dify workflow via HTTP API. Returns the 'text' output field."""
    url = f"{DIFY_BASE_URL}/workflows/run"
    body = json.dumps({
        "inputs": inputs,
        "response_mode": "blocking",
        "user": "paper-assistant",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Dify API error ({e.code}): {e.reason}")
    outputs = data.get("data", {}).get("outputs", {})
    text = outputs.get("result", "") or outputs.get("text", "")
    if not text:
        raise RuntimeError("Dify workflow returned empty output")
    return text


def _parse_json(text):
    """Parse JSON from LLM response, stripping markdown fences if present."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
    return json.loads(text)


# ===== Prompts (used when Dify is unavailable) =====

SYSTEM_PROMPT ="""You are a senior research scientist helping prepare a Chinese group meeting presentation. Read academic paper text and output structured JSON with deep technical insight. Focus heavily on algorithm details, mathematical formulations, and quantitative experimental results.

Rules:
- Extract mathematical formulas and equations. Each formula MUST be a PURE, COMPACT LaTeX mathematical expression — NOT a sentence, NOT a description, NOT a paragraph. For example: `\\mathcal{L}_{CE} = -\\frac{1}{N}\\sum_{i=1}^{N} y_i \\log(\\hat{y}_i)` is correct. `The cross-entropy loss function is defined as...` is WRONG.
- Do NOT include $...$ or $$...$$ delimiters in formulas. Output ONLY the raw LaTeX math expression.
- Identify and describe key figures/tables and what they demonstrate.
- Focus on the NOVELTY of the approach — what is the core algorithmic innovation?
- Report specific experimental numbers (accuracy, F1, BLEU, etc.) with baseline comparisons.
- The "overview" field MUST be written in Chinese (中文). All other fields (section headings, summaries, key_points) should be in Chinese.
- Return ONLY valid JSON, no markdown fences, no extra text."""

ANALYZE_PROMPT = """Analyze the following academic paper text. Extract structured information as JSON:

{
  "title": "full paper title",
  "authors": "author names",
  "year": 2024,
  "abstract": "the full abstract text",
  "overview": "用中文写一段4-5句话的论文梗概，覆盖：(1) 研究什么问题，(2) 现有方法为什么不足，(3) 本文提出什么方案，(4) 核心算法创新点，(5) 主要实验结果和数字。要像给同事做汇报一样简洁清晰。",
  "formulas": ["\\mathcal{L} = -\\frac{1}{N}\\sum_{i=1}^{N} y_i \\log(\\hat{y}_i)", "\\text{Attention}(Q,K,V) = \\text{softmax}(\\frac{QK^T}{\\sqrt{d_k}})V"],
  "figures": ["Figure 1 description and what it shows", "Figure 2 description and what it shows"],
  "sections": [
    {
      "heading": "Section name",
      "summary": "2-3 sentence technical summary of this section",
      "key_points": ["Technical point 1 with specifics", "Technical point 2 with specifics"]
    }
  ]
}

Rules:
- Identify 5-7 major sections. Write section headings, summaries, and key_points in Chinese (中文).
- formulas: extract the most important equations from the method section (max 3). Each formula MUST be a PURE LaTeX math expression — compact, precise, only the equation itself. NO surrounding $ signs, NO explanatory words, NO descriptions. It should look like a line from a math textbook.
- figures: describe the KEY experimental result figures/tables. For each, state: (1) what type of chart it is (line chart, bar chart, table, etc.), (2) what data/metrics it compares, (3) the main quantitative finding shown. Write in Chinese. Max 3 entries, must be substantive.
- Each key_point should be technically specific — include numbers, method names, dataset names.
- overview: 用中文写，简洁清晰，传达论文核心贡献。

Paper text:
{text}"""


def _slide_prompt_for_count(num_slides):
    slide_specs = {
        2: [
            ("Overview & Background", ["Problem statement", "Existing limitations", "Paper's key idea", "Core contribution"]),
            ("Method & Results", ["Algorithm/approach details (include formulas if any)", "Key technical innovations", "Main experimental results (with numbers)", "Takeaway: why this matters"]),
        ],
        3: [
            ("Problem & Motivation", ["What problem does this paper address?", "Why are existing solutions insufficient?", "Paper's main objective"]),
            ("Algorithm & Innovation", ["Core algorithmic idea (include key formulas in LaTeX $...$)", "What makes this approach novel?", "Technical architecture / pipeline"]),
            ("Experiments & Results", ["Datasets used, evaluation metrics", "Main results vs. baselines (with numbers)", "Ablation studies / key insights", "Limitations & conclusions"]),
        ],
        4: [
            ("Background & Motivation", ["Research problem and its significance", "Limitations of prior work", "Paper's objective and key insight"]),
            ("Algorithm Design", ["Core method description", "Key formulas (LaTeX: $...$ or $$...$$)", "Algorithm pseudocode or pipeline description", "Novelty compared to prior methods"]),
            ("Experimental Evaluation", ["Datasets and metrics", "Main results with baseline comparison (numbers required)", "Key figures/tables and what they show", "Ablation or analysis"]),
            ("Conclusion & Discussion", ["Summary of contributions", "Quantitative takeaway", "Limitations", "Potential future work"]),
        ],
        5: [
            ("Motivation", ["Research problem", "Why existing work falls short", "Paper's goal"]),
            ("Method Overview", ["High-level approach", "Key innovation in one sentence"]),
            ("Algorithm Details", ["Detailed algorithm description", "Key formulas in LaTeX ($...$ or $$...$$)", "Training/inference procedure"]),
            ("Experiments", ["Setup: datasets, baselines, metrics", "Main results table with numbers", "Analysis of why the method works"]),
            ("Conclusion", ["Summary of contributions", "Key numbers to remember", "Limitations and future directions"]),
        ],
        6: [
            ("Motivation", ["Problem significance", "Limitations of existing methods"]),
            ("Related Work", ["Key prior approaches", "How this paper differs"]),
            ("Method: Overview", ["High-level pipeline", "Core innovation"]),
            ("Method: Technical Details", ["Key formulas in LaTeX ($...$ or $$...$$)", "Algorithm walkthrough"]),
            ("Experiments & Analysis", ["Setup and datasets", "Main results vs. baselines with numbers", "Ablation insights", "Figure/table descriptions"]),
            ("Conclusion & Contribution", ["Main contributions summarized", "Quantitative takeaways", "Future directions"]),
        ],
    }
    specs = slide_specs.get(num_slides, slide_specs[4])
    slide_json = {"slides": [{"title": t, "bullets": b} for t, b in specs]}
    return """Create presentation slides for a group meeting. The audience is technical — they expect to see formulas, numbers, and algorithm details.

Generate exactly {n} slides as JSON:

{schema}

Paper data:
{paper_json}

CRITICAL RULES:
- Each bullet must be technically substantive (under 35 words, include specifics).
- Include LaTeX formulas where the paper has them. Use $...$ for inline, $$...$$ for display. Formulas MUST be pure compact math expressions, not text descriptions.
- Include figure/table descriptions — describe what key figures show.
- Focus ~60% of content on algorithm/method and experimental results.
- Mention specific datasets, metrics, and numbers (e.g., "Outperforms baseline by 3.2% on CIFAR-100" not "shows improvement").
- 4-5 bullets per slide.
- Return ONLY valid JSON, no markdown fences.""".format(
        n=num_slides, schema=json.dumps(slide_json, indent=2), paper_json="{paper_json}"
    )


# ===== Public API =====

def analyze_paper(full_text):
    """Analyze paper text via Dify workflow or direct Claude API. Returns structured dict."""
    if DIFY_PAPER_ANALYSIS_KEY:
        text = _dify_call(DIFY_PAPER_ANALYSIS_KEY, {"text": full_text})
        return _parse_json(text)

    if not _get_api_key():
        raise RuntimeError("CLAUDE_API_KEY is not set and no Dify workflow configured.")

    text = _call_llm(SYSTEM_PROMPT, [{"role": "user", "content": ANALYZE_PROMPT.replace("{text}", full_text)}], max_tokens=4096)
    if not text:
        raise RuntimeError("No text in LLM response")
    return _parse_json(text)


CHAT_SYSTEM_PROMPT = """你是一位资深研究科学家，正在帮助同事深入理解一篇学术论文。你可以访问论文的完整内容。请用中文回答，兼具技术深度和精确性。

## 论文研读方法论

1. **识别论文类型** — 判断这是实证论文（提出方法+实验）、理论论文（数学推导为主）、综述论文（大量引用、分类体系）还是系统论文（工程实现、基准测试）。根据论文类型调整分析角度。

2. **带着批判性问题阅读** — 讨论论文时，务必涉及：
   - 核心创新：这篇论文的新贡献是什么？与已有方法的本质区别在哪？
   - 方法可靠性：Baseline 对比是否公平？消融实验是否充分？超参数是否正确调优？
   - 证据质量：实验结果是否真正支撑了论文的结论？哪些结论缺少足够的证据？
   - 局限性：论文承认了哪些不足？未提及的潜在缺陷有哪些？方法不能做什么？

3. **答案必须基于论文内容** — 引用具体的章节、图表、表格、公式和实验数据。必要时直接引用原文。如果论文没有涉及某个问题，诚实说明，并区分"论文直接说的"和"可以推断的"。

4. **清晰解释** — 假设读者具有机器学习和计算机科学的基础知识。逐步拆解复杂概念。必要时使用类比。讨论公式时，使用 LaTeX 格式（$...$ 内联，$$...$$ 独立显示），并解释公式背后的直觉。

5. **言之有物，拒绝空话** — 给出具体的数字、方法名和对比数据。避免笼统的赞美或模糊的批评。每一条判断都必须有论文中的具体证据支撑。"""


def chat_about_paper(paper_context, messages, user_question, system_prompt=None):
    """Answer a question about a paper using Claude API with conversation history.

    Args:
        paper_context: str, the paper's structured content
        messages: list of {role, content} dicts for conversation history
        user_question: str, the latest user question
        system_prompt: str or None, custom system prompt (uses CHAT_SYSTEM_PROMPT if None)

    Returns:
        str, the AI assistant's response in Chinese
    """
    if not _get_api_key():
        raise RuntimeError("CLAUDE_API_KEY is not set")

    # Build the messages array for Claude
    api_messages = [
        {"role": "user", "content": f"以下是一篇学术论文的内容：\n\n{paper_context}"},
        {"role": "assistant", "content": "我已经仔细阅读了这篇论文。请随时向我提问，我会用中文详细解答。"},
    ]

    # Add conversation history (skip the initial context exchange)
    for msg in messages:
        api_messages.append({"role": msg["role"], "content": msg["content"]})

    # Add the latest user question if not already in messages
    if user_question and (not messages or messages[-1].get("role") != "user" or messages[-1].get("content") != user_question):
        api_messages.append({"role": "user", "content": user_question})

    return _call_llm(system_prompt or CHAT_SYSTEM_PROMPT, api_messages, max_tokens=2048)


MULTI_CHAT_SYSTEM_PROMPT = """你是一位资深研究科学家，正在同时讨论多篇学术论文。你可以访问所有选中论文的完整内容。

## 核心规则

1. **标注来源** — 每提到一个具体论点、数据、方法，必须用 `[论文N]` 标注来源，N 为论文编号。例如："ResNet 在 ImageNet 上达到 76.1% top-1 准确率 [论文1]"
2. **主动对比** — 当论文之间存在异同、矛盾或互补时，主动指出。不要只是逐篇罗列摘要。
3. **横向比较** — 当用户问对比性问题（"哪篇更好"、"有什么区别"），必须给出带具体数据的横向比较表格或列表。
4. **区分事实与推断** — 区分"论文直接说的结论"和"基于论文内容可以推断的"。推断部分要明确标注"推断："
5. **技术深度** — 回答要有技术深度，引用具体方法名、数据集名、指标数值。避免笼统的概括。
6. **诚实** — 如果某篇论文没有涉及用户问题的内容，诚实说明。不要编造。

## 回答格式建议

当进行横向对比时，使用如下格式：

| 维度 | [论文1简称] | [论文2简称] | ... |
| 方法 | ... | ... | ... |
| 数据集 | ... | ... | ... |
| 关键指标 | ... | ... | ... |
| 创新点 | ... | ... | ... |
| 局限性 | ... | ... | ... |

用中文回答，公式使用 LaTeX 格式。"""


def chat_about_multiple_papers(papers_context, messages, user_question, system_prompt=None):
    """Answer a question across multiple papers using Claude API.

    Args:
        papers_context: list of dicts, each with id, title, overview, sections, formulas, figures, abstract, ...
        messages: list of {role, content} dicts for conversation history
        user_question: str, the latest user question
        system_prompt: str or None, custom system prompt

    Returns:
        str, the AI assistant's response in Chinese with [论文N] source annotations
    """
    if not _get_api_key():
        raise RuntimeError("CLAUDE_API_KEY is not set")
    if not papers_context:
        raise RuntimeError("No papers selected")

    context_parts = []
    for i, paper in enumerate(papers_context, 1):
        parts = [
            f"--- 论文 {i} ---",
            f"标题：{paper.get('title', '未知')}",
            f"作者：{paper.get('authors', '未知')}",
            f"年份：{paper.get('year', '未知')}",
        ]
        if paper.get("abstract"):
            parts.append(f"摘要：{paper.get('abstract')}")
        if paper.get("overview"):
            parts.append(f"AI梗概：{paper.get('overview')}")

        sections = paper.get("sections", [])
        if isinstance(sections, str):
            try:
                sections = json.loads(sections)
            except (json.JSONDecodeError, TypeError):
                sections = []
        if isinstance(sections, dict):
            sections = sections.get("sections", [])
        if sections:
            sec_lines = []
            for sec in sections:
                if isinstance(sec, dict):
                    sec_lines.append(f"  - {sec.get('heading', '')}: {sec.get('summary', '')}")
                    if sec.get("key_points"):
                        for pt in sec["key_points"]:
                            sec_lines.append(f"    * {pt}")
            if sec_lines:
                parts.append("论文结构：\n" + "\n".join(sec_lines))

        formulas = paper.get("formulas", [])
        if isinstance(formulas, str):
            try:
                formulas = json.loads(formulas)
            except (json.JSONDecodeError, TypeError):
                formulas = []
        if formulas:
            parts.append("核心公式：\n" + "\n".join(formulas))

        figures = paper.get("figures", paper.get("proper_figures", []))
        if isinstance(figures, str):
            try:
                figures = json.loads(figures)
            except (json.JSONDecodeError, TypeError):
                figures = []
        if figures:
            parts.append("图表描述：\n" + "\n".join(figures))

        context_parts.append("\n".join(parts))

    all_papers_context = "\n\n".join(context_parts)

    paper_summary = "\n".join([
        f"[论文{i}] {p.get('title', '未知')[:80]}"
        for i, p in enumerate(papers_context, 1)
    ])

    api_messages = [
        {"role": "user", "content": f"以下是我选中的 {len(papers_context)} 篇论文的内容：\n\n{all_papers_context}\n\n论文索引：\n{paper_summary}"},
        {"role": "assistant", "content": f"我已经仔细阅读了这 {len(papers_context)} 篇论文。可以随时就它们进行讨论、对比、分析。请告诉我你想了解什么？"},
    ]

    for msg in messages:
        api_messages.append({"role": msg["role"], "content": msg["content"]})

    if user_question and (not messages or messages[-1].get("role") != "user" or messages[-1].get("content") != user_question):
        api_messages.append({"role": "user", "content": user_question})

    return _call_llm(system_prompt or MULTI_CHAT_SYSTEM_PROMPT, api_messages, max_tokens=4096)


def chat_assistant(query, conversation_id=""):
    """Call the general-purpose Dify Chat workflow assistant.

    Uses the Dify Workflow API (/workflows/run) for conversational AI.
    Supports multi-turn conversation via conversation history in the query.

    Args:
        query: str, the user's question (with conversation history embedded)
        conversation_id: str, unused for workflow API (kept for compatibility)

    Returns:
        dict with keys: answer (str), conversation_id (str)
    """
    if not DIFY_CHAT_ASSISTANT_KEY:
        raise RuntimeError("DIFY_CHAT_ASSISTANT_KEY is not set")

    from models import get_setting
    input_key = get_setting("workflow_input_key") or "hhh"

    url = f"{DIFY_BASE_URL}/workflows/run"
    body = json.dumps({
        "inputs": {input_key: query, "input.files": []},
        "response_mode": "blocking",
        "user": "paper-assistant",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {DIFY_CHAT_ASSISTANT_KEY}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Dify API error ({e.code}): {err_body}")

    outputs = data.get("data", {}).get("outputs", {})
    answer = outputs.get("result", "") or outputs.get("text", "")
    if not answer and outputs:
        answer = next(iter(outputs.values()), "")
    if not answer:
        raise RuntimeError("Dify workflow returned empty output")
    return {"answer": answer, "conversation_id": conversation_id}


def call_claude(system_prompt, user_message, max_tokens=4096):
    """Generic Claude API call with custom system prompt. Returns text response."""
    if not _get_api_key():
        raise RuntimeError("API key is not set")
    return _call_llm(system_prompt, [{"role": "user", "content": user_message}], max_tokens=max_tokens)


def generate_slide_content(paper_data, num_slides=4):
    """Generate slide content via Dify workflow or direct Claude API. Returns dict with 'slides' key."""
    if DIFY_SLIDE_GEN_KEY:
        text = _dify_call(DIFY_SLIDE_GEN_KEY, {
            "paper_json": json.dumps(paper_data, ensure_ascii=False),
            "num_slides": str(num_slides),
        })
        return _parse_json(text)

    if not _get_api_key():
        raise RuntimeError("CLAUDE_API_KEY is not set and no Dify workflow configured.")

    prompt = _slide_prompt_for_count(num_slides)
    text = _call_llm(SYSTEM_PROMPT, [{"role": "user", "content": prompt.replace("{paper_json}", json.dumps(paper_data, ensure_ascii=False))}], max_tokens=4096)
    if not text:
        raise RuntimeError("No text in LLM response")
    return _parse_json(text)
