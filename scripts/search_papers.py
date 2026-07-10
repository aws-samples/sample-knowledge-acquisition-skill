#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["defusedxml"]
# ///
"""Unified paper search across multiple backends (arXiv, Semantic Scholar, OpenAlex).

Fans out to multiple sources, deduplicates by arXiv ID or DOI, and outputs merged JSONL.

Usage:
    uv run ./scripts/search_papers.py --query "mixture of experts" --sources arxiv,s2,openalex -o results.jsonl
    uv run ./scripts/search_papers.py --query "LLM reasoning" --sources arxiv,s2 --max-results 30
    uv run ./scripts/search_papers.py --query "diffusion" --sources openalex --min-citations 20 -o results.jsonl
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from url_utils import safe_urlopen, USER_AGENT

# --- arXiv ---
ARXIV_API = "http://export.arxiv.org/api/query"
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

# --- Semantic Scholar ---
S2_API = "https://api.semanticscholar.org/graph/v1"
S2_FIELDS = "paperId,title,authors,abstract,year,venue,citationCount,externalIds,url,publicationDate"

# --- OpenAlex ---
OPENALEX_API = "https://api.openalex.org"


def _http_get(url: str, headers: dict | None = None) -> bytes:
    if not url.startswith(("https://", "http://")):
        raise ValueError(f"URL scheme not allowed: {url}")
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with safe_urlopen(req, timeout=30) as resp:
        return resp.read()


def search_arxiv(query: str, max_results: int) -> list[dict]:
    import defusedxml.ElementTree as ET
    params = urllib.parse.urlencode({
        "search_query": f"all:{query}", "start": 0,
        "max_results": min(max_results, 100), "sortBy": "relevance",
    })
    xml_data = _http_get(f"{ARXIV_API}?{params}")
    papers = []
    for entry in ET.fromstring(xml_data).findall("atom:entry", ARXIV_NS):
        id_el = entry.find("atom:id", ARXIV_NS)
        title_el = entry.find("atom:title", ARXIV_NS)
        if title_el is None or id_el is None:
            continue
        arxiv_id = id_el.text.split("/abs/")[-1] if "/abs/" in id_el.text else ""
        authors = [a.find("atom:name", ARXIV_NS).text.strip()
                   for a in entry.findall("atom:author", ARXIV_NS)
                   if a.find("atom:name", ARXIV_NS) is not None]
        abstract_el = entry.find("atom:summary", ARXIV_NS)
        pub_el = entry.find("atom:published", ARXIV_NS)
        papers.append({
            "arxiv_id": arxiv_id,
            "title": " ".join(title_el.text.strip().split()),
            "authors": authors,
            "abstract": " ".join((abstract_el.text or "").split()) if abstract_el is not None else "",
            "year": int(pub_el.text[:4]) if pub_el is not None and pub_el.text else None,
            "citationCount": None,
            "venue": "",
            "doi": "",
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else "",
            "source": "arxiv",
        })
    return papers


def search_s2(query: str, max_results: int, api_key: str | None = None) -> list[dict]:
    params = urllib.parse.urlencode({"query": query, "limit": min(max_results, 100), "fields": S2_FIELDS})
    url = f"{S2_API}/paper/search?{params}"
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key
    try:
        data = json.loads(_http_get(url, headers))
    except Exception:
        return []
    papers = []
    for item in data.get("data", []):
        if not item.get("title"):
            continue
        ext = item.get("externalIds") or {}
        arxiv_id = ext.get("ArXiv", "")
        doi = ext.get("DOI", "")
        authors = [a.get("name", "") for a in (item.get("authors") or []) if a.get("name")]
        papers.append({
            "arxiv_id": arxiv_id,
            "title": item["title"],
            "authors": authors,
            "abstract": " ".join((item.get("abstract") or "").split()),
            "year": item.get("year"),
            "citationCount": item.get("citationCount", 0),
            "venue": item.get("venue", ""),
            "doi": doi,
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else "",
            "source": "semantic_scholar",
        })
    return papers


def search_openalex(query: str, max_results: int) -> list[dict]:
    params = urllib.parse.urlencode({"search": query, "per_page": min(max_results, 50), "sort": "cited_by_count:desc"})
    url = f"{OPENALEX_API}/works?{params}"
    try:
        data = json.loads(_http_get(url))
    except Exception:
        return []
    papers = []
    for work in data.get("results", []):
        if not work.get("title"):
            continue
        authors = [a.get("author", {}).get("display_name", "") for a in work.get("authorships", [])
                   if a.get("author", {}).get("display_name")]
        arxiv_id = ""
        for loc in work.get("locations", []):
            lp = loc.get("landing_page_url", "") or ""
            if "arxiv.org" in lp:
                arxiv_id = lp.rstrip("/").split("/")[-1]
                break
        doi = (work.get("doi") or "").removeprefix("https://doi.org/")
        pdf_url = (work.get("open_access") or {}).get("oa_url", "") or ""
        if not pdf_url and arxiv_id:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
        papers.append({
            "arxiv_id": arxiv_id,
            "title": work["title"],
            "authors": authors,
            "abstract": "",
            "year": work.get("publication_year"),
            "citationCount": work.get("cited_by_count", 0),
            "venue": ((work.get("primary_location") or {}).get("source") or {}).get("display_name", ""),
            "doi": doi,
            "pdf_url": pdf_url,
            "source": "openalex",
        })
    return papers


def deduplicate(papers: list[dict]) -> list[dict]:
    """Deduplicate by arxiv_id or doi, preferring entries with more metadata."""
    seen_arxiv, seen_doi = {}, {}
    result = []
    for p in papers:
        aid = p.get("arxiv_id", "")
        doi = p.get("doi", "")
        if aid and aid in seen_arxiv:
            # merge citation count if missing
            existing = seen_arxiv[aid]
            if p.get("citationCount") and not existing.get("citationCount"):
                existing["citationCount"] = p["citationCount"]
            continue
        if doi and doi in seen_doi:
            continue
        if aid:
            seen_arxiv[aid] = p
        if doi:
            seen_doi[doi] = p
        result.append(p)
    return result


def main():
    parser = argparse.ArgumentParser(description="Unified paper search across multiple backends")
    parser.add_argument("--query", required=True, help="Search keywords")
    parser.add_argument("--sources", default="arxiv,s2,openalex", help="Comma-separated: arxiv,s2,openalex (default: all)")
    parser.add_argument("--max-results", type=int, default=30, help="Max results per source (default: 30)")
    parser.add_argument("--min-citations", type=int, default=0, help="Filter: minimum citations")
    parser.add_argument("--api-key", help="Semantic Scholar API key (or S2_API_KEY env var)")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    args = parser.parse_args()

    import os
    api_key = args.api_key or os.environ.get("S2_API_KEY")
    sources = [s.strip() for s in args.sources.split(",")]
    all_papers = []

    for src in sources:
        print(f"Searching {src}...", file=sys.stderr)
        try:
            if src == "arxiv":
                all_papers.extend(search_arxiv(args.query, args.max_results))
            elif src == "s2":
                all_papers.extend(search_s2(args.query, args.max_results, api_key))
            elif src == "openalex":
                all_papers.extend(search_openalex(args.query, args.max_results))
            else:
                print(f"Unknown source: {src}", file=sys.stderr)
        except Exception as e:
            print(f"Warning: {src} search failed: {e}", file=sys.stderr)
        time.sleep(1)

    papers = deduplicate(all_papers)
    if args.min_citations > 0:
        papers = [p for p in papers if (p.get("citationCount") or 0) >= args.min_citations]

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    out = open(args.output, "w") if args.output else sys.stdout
    try:
        for p in papers:
            out.write(json.dumps(p, ensure_ascii=False) + "\n")
    finally:
        if args.output:
            out.close()

    print(f"Found {len(papers)} papers (deduplicated from {len(all_papers)})", file=sys.stderr)


if __name__ == "__main__":
    main()
