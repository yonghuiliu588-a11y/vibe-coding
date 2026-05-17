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

    if not _is_valid_title(title):
        title = _guess_title(full_text)
    if not _is_valid_authors(authors):
        authors = _guess_authors(full_text)

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


def _is_valid_title(title):
    """Reject generic/placeholder titles that are clearly not real paper titles."""
    if not title or len(title.strip()) < 5:
        return False
    t = title.strip().lower()
    garbage = {
        "bachelor dissertation", "master thesis", "untitled", "unknown",
        "microsoft word", "word document", "pdf document", "empty",
        "no title", "title", "thesis", "dissertation", "paper",
        "document", "untitled document", "presentation", "slide",
    }
    if t in garbage:
        return False
    if len(t) < 15:
        return False
    return True


def _is_valid_authors(authors):
    """Reject garbage author strings like OS usernames."""
    if not authors or len(authors.strip()) < 2:
        return False
    a = authors.strip().lower()
    garbage = {
        "windows user", "windows 用户", "administrator", "admin",
        "user", "owner", "author", "unknown", "anonymous",
        "microsoft", "hp", "dell", "lenovo",
    }
    if a in garbage:
        return False
    # Must contain at least one letter
    if not any(c.isalpha() for c in a):
        return False
    return True


def _guess_authors(text):
    """Try to extract author names from the first page of a paper."""
    lines = text.strip().split("\n")
    head = lines[:40]
    title_garbage = {
        "bachelor dissertation", "master thesis", "untitled", "unknown",
        "microsoft word", "word document", "pdf document", "empty",
        "no title", "title", "thesis", "dissertation", "paper",
        "document", "untitled document", "presentation", "slide",
    }
    # First pass: look for the line AFTER "By" or "by" (common in thesis covers)
    for i, line in enumerate(head):
        line_stripped = line.strip()
        if line_stripped.lower() == "by" and i + 1 < len(head):
            candidate = head[i + 1].strip()
            if 3 < len(candidate) < 100 and not re.search(r'(?i)university|institute|college|department|school|supervised|prof\.?|dr\.?|http|@', candidate):
                return candidate

    # Second pass: look for a short line with name-like pattern
    for i, line in enumerate(head):
        line = line.strip()
        if not line or len(line) < 3 or len(line) > 100:
            continue
        if line.lower() in title_garbage:
            continue
        # Author lines are typically short (2-4 words) with capitalized words
        words = line.split()
        if not (1 <= len(words) <= 5):
            continue
        if not all(w[0].isupper() or not w[0].isalpha() for w in words if w[0].isalpha()):
            continue
        # Skip affiliations and headers
        if re.search(r'(?i)university|institute|college|department|school|lab(oratory)?\b|corp(oratio)?\b|inc\.?|ltd\.?|©|http|@|doi', line):
            continue
        if re.match(r'(?i)^(abstract|introduction|1\.?|i\.|related|background|method|result|conclusion|reference|acknowledgment|appendix|supervised)\b', line):
            continue
        # Skip lines that look like titles (too many long words or contain title keywords)
        title_keywords = {'neural', 'network', 'learning', 'model', 'method', 'approach',
                         'research', 'study', 'analysis', 'based', 'using', 'system', 'data'}
        if len(words) >= 3 and any(w.lower() in title_keywords for w in words):
            continue
        return line
    return ""


def _guess_title(text):
    """Use the first substantial non-empty line as title if metadata is missing."""
    lines = text.strip().split("\n")
    for line in lines:
        line = line.strip()
        if len(line) > 20 and not line.startswith(("http", "arXiv", "©", "DOI")):
            if _is_valid_title(line):
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


def extract_images(filepath, paper_id, images_dir):
    """Extract embedded images from a PDF file and save them to disk.

    Returns a list of dicts: [{page, filename, width, height}, ...]
    Only keeps images larger than 100x100 pixels (filters out icons/ornaments).
    """
    import os
    os.makedirs(os.path.join(images_dir, str(paper_id)), exist_ok=True)

    doc = fitz.open(filepath)
    results = []
    seen_hashes = set()

    for page_num in range(len(doc)):
        page = doc[page_num]
        images = page.get_images(full=True)

        for idx, img_info in enumerate(images):
            xref = img_info[0]
            try:
                img_data = doc.extract_image(xref)
            except Exception:
                continue

            image_bytes = img_data.get("image")
            if not image_bytes:
                continue

            w, h = img_data.get("width", 0), img_data.get("height", 0)

            # Skip tiny images (icons, ornamental elements)
            if w < 100 or h < 100:
                continue

            # Deduplicate by image hash
            img_hash = hash(image_bytes)
            if img_hash in seen_hashes:
                continue
            seen_hashes.add(img_hash)

            ext = img_data.get("ext", "png")
            if ext not in ("png", "jpeg", "jpg"):
                ext = "png"

            filename = f"page{page_num + 1}_img{idx + 1}.{ext}"
            filepath_out = os.path.join(images_dir, str(paper_id), filename)

            with open(filepath_out, "wb") as f:
                f.write(image_bytes)

            results.append({
                "page": page_num + 1,
                "filename": filename,
                "width": w,
                "height": h,
            })

    doc.close()
    return results
