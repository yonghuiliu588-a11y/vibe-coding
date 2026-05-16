import json
from anthropic import Anthropic
from anthropic.types import TextBlock
from config import CLAUDE_API_KEY

client = Anthropic(api_key=CLAUDE_API_KEY)


def _get_text(response):
    """Extract text from Claude response, handling ThinkingBlock."""
    for block in response.content:
        if isinstance(block, TextBlock):
            return block.text
    return ""


SYSTEM_PROMPT = """You are a senior research scientist helping prepare a Chinese group meeting presentation. Read academic paper text and output structured JSON with deep technical insight. Focus heavily on algorithm details, mathematical formulations, and quantitative experimental results.

Rules:
- Extract mathematical formulas and equations where present (use LaTeX notation: $...$ for inline, $$...$$ for display).
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
  "formulas": ["Key formula 1 in LaTeX", "Key formula 2 in LaTeX"],
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
- formulas: extract the most important equations from the method section in LaTeX (max 3).
- figures: describe the key figures/tables and what they demonstrate in Chinese (max 3).
- Each key_point should be technically specific — include numbers, method names, dataset names.
- overview: 用中文写，简洁清晰，传达论文核心贡献。

Paper text:
{text}"""


def _slide_prompt_for_count(num_slides):
    """Build a slide generation prompt for a specific number of slides."""
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

    slide_json = {
        "slides": [
            {"title": title, "bullets": bullets}
            for title, bullets in specs
        ]
    }

    return """Create presentation slides for a group meeting. The audience is technical — they expect to see formulas, numbers, and algorithm details.

Generate exactly {n} slides as JSON:

{schema}

Paper data:
{paper_json}

CRITICAL RULES:
- Each bullet must be technically substantive (under 35 words, include specifics).
- Include LaTeX formulas where the paper has them. Use $...$ for inline, $$...$$ for display equations.
- Include figure/table descriptions — describe what key figures show.
- Focus ~60% of content on algorithm/method and experimental results.
- Mention specific datasets, metrics, and numbers (e.g., "Outperforms baseline by 3.2% on CIFAR-100" not "shows improvement").
- 4-5 bullets per slide.
- Return ONLY valid JSON, no markdown fences.""".format(
        n=num_slides,
        schema=json.dumps(slide_json, indent=2),
        paper_json="{paper_json}"
    )


def analyze_paper(full_text):
    """Send paper text to Claude and get structured analysis back."""
    if not CLAUDE_API_KEY:
        raise RuntimeError("CLAUDE_API_KEY is not set.")

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": ANALYZE_PROMPT.replace("{text}", full_text)
        }]
    )
    result_text = _get_text(response)
    if not result_text:
        raise RuntimeError("No text in Claude response")
    result_text = result_text.strip()
    if result_text.startswith("```"):
        result_text = result_text.split("\n", 1)[1]
        if result_text.endswith("```"):
            result_text = result_text[:-3]
    return json.loads(result_text)


def generate_slide_content(paper_data, num_slides=4):
    """Generate n-slide bullet-point content for one paper."""
    if not CLAUDE_API_KEY:
        raise RuntimeError("CLAUDE_API_KEY is not set.")

    prompt = _slide_prompt_for_count(num_slides)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": prompt.replace("{paper_json}", json.dumps(paper_data, ensure_ascii=False))
        }]
    )
    result_text = _get_text(response)
    if not result_text:
        raise RuntimeError("No text in Claude response")
    result_text = result_text.strip()
    if result_text.startswith("```"):
        result_text = result_text.split("\n", 1)[1]
        if result_text.endswith("```"):
            result_text = result_text[:-3]
    return json.loads(result_text)
