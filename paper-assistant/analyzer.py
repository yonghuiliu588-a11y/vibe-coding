import json
from anthropic import Anthropic
from config import CLAUDE_API_KEY

client = Anthropic(api_key=CLAUDE_API_KEY)

SYSTEM_PROMPT = """You are a research paper analyzer. Your task is to read academic paper text and output structured JSON.

Rules:
- Be accurate. Only include information actually present in the provided text.
- If you cannot find a piece of information, use an empty string or empty list.
- Return ONLY valid JSON, no markdown fences, no extra text.
- Keep summaries concise: 1-2 sentences per section."""

ANALYZE_PROMPT = """Analyze the following academic paper text. Extract structured information as JSON:

{
  "title": "full paper title as it appears in the paper",
  "authors": "author names as they appear",
  "year": 2024,
  "abstract": "the full abstract text",
  "sections": [
    {
      "heading": "Section name",
      "summary": "Concise 1-2 sentence summary of what this section covers",
      "key_points": ["Key finding or argument 1", "Key finding or argument 2"]
    }
  ]
}

Identify the major sections: typically Introduction, Related Work/Background, Method/Approach/Model, Experiments/Results, and Conclusion.
Each section should have exactly 2-4 key points.
Skip reference sections, acknowledgments, and appendices.

Paper text:
{text}"""

SLIDE_PROMPT = """Create presentation slide content for a group meeting based on the following paper information.

Paper data:
{paper_json}

Generate exactly 4 slides as JSON:

{
  "slides": [
    {
      "title": "Title Slide",
      "bullets": ["Full Paper Title", "Authors (Year)", "Venue or preprint server", "One-line summary of contribution"]
    },
    {
      "title": "Background & Motivation",
      "bullets": ["What problem does this paper address?", "Why are existing solutions insufficient?", "What is the paper's main goal?", "What is the key contribution?"]
    },
    {
      "title": "Method",
      "bullets": ["Core idea in one sentence", "Key technical component 1", "Key technical component 2", "What makes this approach novel?"]
    },
    {
      "title": "Results & Conclusion",
      "bullets": ["Main experimental result", "Second important finding", "What does this mean for the field?", "Limitations or future work if mentioned"]
    }
  ]
}

Rules:
- Each bullet must be a single sentence under 30 words.
- Replace placeholder text with actual content from the paper.
- 3-5 bullets per slide.
- Return ONLY valid JSON, no markdown fences, no extra text.
- If information for a bullet is not in the paper, write "Not specified in paper." instead of inventing."""


def analyze_paper(full_text):
    """Send paper text to Claude and get structured analysis back."""
    if not CLAUDE_API_KEY:
        raise RuntimeError("CLAUDE_API_KEY is not set. Set it via environment variable or in config.py.")

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": ANALYZE_PROMPT.replace("{text}", full_text)
        }]
    )
    result_text = response.content[0].text
    result_text = result_text.strip()
    if result_text.startswith("```"):
        result_text = result_text.split("\n", 1)[1]
        if result_text.endswith("```"):
            result_text = result_text[:-3]
    return json.loads(result_text)


def generate_slide_content(paper_data):
    """Generate 4-slide bullet-point content for one paper."""
    if not CLAUDE_API_KEY:
        raise RuntimeError("CLAUDE_API_KEY is not set. Set it via environment variable or in config.py.")

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": SLIDE_PROMPT.replace("{paper_json}", json.dumps(paper_data, ensure_ascii=False))
        }]
    )
    result_text = response.content[0].text
    result_text = result_text.strip()
    if result_text.startswith("```"):
        result_text = result_text.split("\n", 1)[1]
        if result_text.endswith("```"):
            result_text = result_text[:-3]
    return json.loads(result_text)
