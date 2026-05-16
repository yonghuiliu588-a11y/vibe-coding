import fitz
import re


def parse_pdf(filepath):
    """Extract text and metadata from a PDF file. Returns a dict ready for DB insert."""
    doc = fitz.open(filepath)
    metadata = doc.metadata or {}

    title = metadata.get("title", "")
    authors = metadata.get("author", "")

    full_text = ""
    for page in doc:
        full_text += page.get_text()

    if not title or len(title) < 3:
        title = _guess_title(full_text)

    abstract = _extract_abstract(full_text)
    year = _extract_year(full_text, metadata)
    figure_count = _count_figures(full_text)

    text_for_api = full_text[:30000]

    doc.close()

    return {
        "title": title.strip(),
        "authors": authors.strip(),
        "year": year,
        "abstract": abstract.strip(),
        "full_text": text_for_api,
        "figure_count": figure_count,
    }


def _guess_title(text):
    """Use the first substantial non-empty line as title if metadata is missing."""
    lines = text.strip().split("\n")
    for line in lines:
        line = line.strip()
        if len(line) > 20 and not line.startswith(("http", "arXiv", "©", "DOI")):
            return line
    return ""


def _extract_abstract(text):
    """Extract abstract paragraph(s) from paper text."""
    patterns = [
        r'(?i)abstract\s*[—\-]*\s*\n+(.{100,3000})',
        r'(?i)a b s t r a c t\s*\n+(.{100,3000})',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.DOTALL)
        if m:
            return m.group(1).strip()
    paras = text.split("\n\n")
    for p in paras:
        p = p.strip()
        if len(p) > 200 and len(p) < 3000:
            return p
    return text[:500]


def _extract_year(text, metadata):
    """Extract publication year from text or metadata."""
    for key in ("year", "publicationYear", "date"):
        if key in metadata and metadata[key]:
            m = re.search(r"(19\d{2}|20\d{2})", str(metadata[key]))
            if m:
                return int(m.group(1))
    years = re.findall(r'\b(19\d{2}|20\d{2})\b', text[:3000])
    if years:
        return int(years[0])
    return None


def _count_figures(text):
    """Count approximate number of figures from captions."""
    return len(re.findall(r'(?i)^\s*(?:fig\.|figure)\s+\d+', text, re.MULTILINE))
