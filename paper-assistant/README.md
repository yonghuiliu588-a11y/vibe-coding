# Paper Assistant · 论文助手

AI-powered academic paper assistant — upload PDFs, extract insights, chat with papers, compare multiple papers, and generate group meeting PPTs with one click.

## Features

| Module | Description |
|--------|-------------|
| **Paper Library** | Upload PDFs, auto-extract metadata & full text |
| **Deep Read** | AI structural analysis + chat with any paper |
| **Multi-Paper Discussion** | Cross-paper comparison with source citations |
| **PPT Generator** | One-click group meeting slides (2–6 slides per paper, append mode supported) |
| **Academic Search** | arXiv + OpenAlex search with RRF ranking |
| **Figure Generator** | Generate publication-quality matplotlib code |
| **Text Polisher** | Polish academic writing to Nature journal standards |
| **AI Assistant** | Floating chat widget on all pages |

## Tech Stack

- **Backend**: Python 3.10+ / FastAPI / SQLite / Jinja2
- **PDF**: PyMuPDF (fitz)
- **PPT**: python-pptx
- **AI**: DeepSeek API (OpenAI SDK) / Claude API (Anthropic SDK) / Dify workflows
- **Search**: arXiv API / OpenAlex API / CrossRef
- **Math**: MathJax 3

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run
cd paper-assistant
python main.py

# 3. Open
# http://127.0.0.1:8000
```

## Configuration

Go to **Settings** (`http://127.0.0.1:8000/settings`) to configure your AI provider:

- **DeepSeek**: Input your API key, choose `deepseek-v4-pro` / `deepseek-chat` / `deepseek-reasoner`
- **Claude**: Input your API key, choose `claude-sonnet-4-6` / `claude-opus-4-7` / `claude-haiku-4-5`

Settings are stored locally in SQLite and applied immediately.

Or set environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | — | DeepSeek API key |
| `CLAUDE_API_KEY` | — | Claude API key |
| `DIFY_BASE_URL` | `http://localhost/v1` | Dify server URL |
| `DIFY_PAPER_ANALYSIS_KEY` | — | Dify workflow for paper analysis |
| `DIFY_SLIDE_GEN_KEY` | — | Dify workflow for slide generation |
| `DIFY_CHAT_ASSISTANT_KEY` | — | Dify workflow for floating assistant |

## Project Structure

```
paper-assistant/
├── main.py           # FastAPI app — all routes & endpoints
├── config.py         # Configuration with env var overrides
├── models.py         # SQLite ORM (papers, presentations, settings)
├── parser.py         # PDF text + image extraction
├── analyzer.py       # AI logic — unified DeepSeek/Claude client
├── generator.py      # PPTX creation & append
├── searcher.py       # arXiv + OpenAlex RRF search
├── skills.py         # Figure & polish system prompts
├── templates/        # Jinja2 pages (10 templates)
├── static/           # CSS
├── uploads/          # Uploaded PDFs
├── output/           # Generated PPTX files
└── requirements.txt  # Python dependencies
```

## API Overview

### Pages
`/` `/paper/{id}` `/deepread` `/discuss` `/search` `/figure` `/polish` `/settings`

### Core APIs
- `POST /upload` — Upload PDF
- `POST /deepread/analyze/{id}` — Trigger AI analysis
- `POST /deepread/chat/{id}` — Chat about a paper
- `POST /discuss/chat` — Multi-paper discussion
- `POST /generate` — Generate PPT
- `POST /api/search` — Search arXiv + OpenAlex

## License

MIT
