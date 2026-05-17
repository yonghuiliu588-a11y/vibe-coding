"""Academic paper search via arXiv API + OpenAlex citation enrichment + RRF ranking."""
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
import ssl
import re


def _search_arxiv_api(query, limit=30):
    """Search arXiv API. Returns raw papers with published date parsed.

    Each paper: {title, authors, year, published, abstract, venue, url, source, arxiv_id}
    """
    base = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": limit,
        "sortBy": "relevance",
    }
    url = f"{base}?{urllib.parse.urlencode(params)}"

    ctx = ssl.create_default_context()
    data = None
    last_error = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
                data = resp.read().decode("utf-8")
            break
        except Exception as e:
            last_error = e
            print(f"arXiv API attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                import time
                time.sleep(2)
    if data is None:
        print(f"arXiv API all attempts failed: {last_error}")
        return []

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    root = ET.fromstring(data)
    papers = []
    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""

        authors = []
        for author in entry.findall("atom:author", ns):
            name_el = author.find("atom:name", ns)
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())
        authors_str = ", ".join(authors)

        summary_el = entry.find("atom:summary", ns)
        abstract = (summary_el.text or "").strip().replace("\n", " ")[:800] if summary_el is not None else ""

        # Parse published date: "2023-06-15T18:30:00Z" -> "2023-06-15"
        published_el = entry.find("atom:published", ns)
        published = ""
        year = ""
        if published_el is not None and published_el.text:
            published = published_el.text.strip()[:10]  # YYYY-MM-DD
            year = published[:4]

        link_el = entry.find("atom:id", ns)
        url = link_el.text.strip() if link_el is not None and link_el.text else ""

        # Extract arXiv ID from URL (e.g. http://arxiv.org/abs/2306.11113v2 -> 2306.11113)
        arxiv_id = ""
        if url:
            m = re.search(r'abs/([\w.-]+)', url)
            if m:
                arxiv_id = m.group(1)

        papers.append({
            "title": title,
            "authors": authors_str,
            "year": year,
            "published": published,
            "abstract": abstract,
            "venue": "arXiv",
            "url": url,
            "source": "arxiv",
            "arxiv_id": arxiv_id,
            "citations": 0,
        })
    return papers


def _enrich_citations(papers):
    """Batch-enrich papers with citation counts from OpenAlex API.

    Uses OpenAlex works search by title to find matching papers and their cited_by_count.
    Each query has an 8-second timeout; failures leave citations at 0.
    Stops after 5 consecutive failures to avoid hanging.
    """
    if not papers:
        return

    consecutive_failures = 0
    for paper in papers:
        title = paper.get("title", "")
        if not title or len(title) < 5:
            continue

        if consecutive_failures >= 5:
            break  # Give up after too many failures

        try:
            # Search OpenAlex by title
            params = urllib.parse.urlencode({
                "search": title,
                "per_page": 1,
            })
            url = f"https://api.openalex.org/works?{params}"

            ctx = ssl.create_default_context()
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            results = data.get("results", [])
            if results:
                paper["citations"] = results[0].get("cited_by_count", 0) or 0
                if not paper.get("published"):
                    oa_date = results[0].get("publication_date", "")
                    if oa_date:
                        paper["published"] = oa_date
                        paper["year"] = oa_date[:4]
            consecutive_failures = 0
        except Exception as e:
            consecutive_failures += 1
            # Leave citations at 0 on failure


def search_papers(query, limit=10):
    """Search for academic papers with RRF enrichment data.

    Fetches 30 candidates, enriches with citations, returns top `limit` papers
    with publication date and citation count for frontend RRF ranking.
    """
    query = query.strip()
    if not query:
        return []

    # Step 1: Fetch 30 candidates from arXiv
    candidates = _search_arxiv_api(query, limit=30)

    # Fallback: CrossRef if arXiv returns nothing
    if not candidates:
        candidates = _search_crossref(query, limit=30)

    if not candidates:
        return []

    # Step 2: Enrich with citation counts (skip if we already have too many failures)
    try:
        _enrich_citations(candidates)
    except Exception as e:
        print(f"Citation enrichment failed: {e}")

    return candidates
