#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Search Semantic Scholar Graph API and output JSONL paper metadata.

Self-contained: uses only stdlib (urllib, json).

Usage:
    uv run ./scripts/search_semantic_scholar.py --query "long horizon reasoning" --max-results 20
    uv run ./scripts/search_semantic_scholar.py --query "LLM agent" --min-citations 10 --year-range 2020-2026
    uv run ./scripts/search_semantic_scholar.py --query "protein folding" --venue NeurIPS ICML -o results.jsonl
    uv run ./scripts/search_semantic_scholar.py --citations-of "ARXIV:2301.07041" --max-results 50
    uv run ./scripts/search_semantic_scholar.py --references-of "ARXIV:2301.07041"
    uv run ./scripts/search_semantic_scholar.py --related-to "ARXIV:2301.07041" --max-results 20
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from url_utils import safe_urlopen, USER_AGENT

S2_API = "https://api.semanticscholar.org/graph/v1"
FIELDS = "paperId,title,authors,abstract,year,venue,citationCount,referenceCount,externalIds,url,publicationDate"


def s2_request(url: str, api_key: str | None = None) -> dict:
    if not url.startswith("https://"):
        raise ValueError(f"URL scheme not allowed: {url}")
    headers = {"User-Agent": USER_AGENT}
    if api_key:
        headers["x-api-key"] = api_key
    req = urllib.request.Request(url, headers=headers)
    max_retries = 5
    for attempt in range(max_retries):
        try:
            with safe_urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = min(2 ** (attempt + 1), 60)
                print(f"Rate limited, waiting {wait}s (attempt {attempt + 1}/{max_retries})...", file=sys.stderr)
                time.sleep(wait)
                # Recreate the request object for retry (some urllib implementations
                # mark the request as used after an error)
                req = urllib.request.Request(url, headers=headers)
                continue
            raise
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(1)
                req = urllib.request.Request(url, headers=headers)
                continue
            raise
    print(
        "Warning: Semantic Scholar API rate limit exceeded after retries. "
        "Set S2_API_KEY env var for higher limits (~1 req/s).",
        file=sys.stderr,
    )
    return {}


def parse_paper(data: dict) -> dict | None:
    if not data or not data.get("title"):
        return None
    authors = [a.get("name", "") for a in (data.get("authors") or []) if a.get("name")]
    external_ids = data.get("externalIds") or {}
    arxiv_id = external_ids.get("ArXiv", "")
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else ""
    return {
        "paperId": data.get("paperId", ""),
        "arxiv_id": arxiv_id,
        "title": data["title"],
        "authors": authors,
        "abstract": " ".join((data.get("abstract") or "").split()),
        "year": data.get("year"),
        "venue": data.get("venue", ""),
        "citationCount": data.get("citationCount", 0) or 0,
        "referenceCount": data.get("referenceCount", 0) or 0,
        "publicationDate": data.get("publicationDate", ""),
        "url": data.get("url", ""),
        "pdf_url": pdf_url,
        "source": "semantic_scholar",
    }


def search_papers(
    query: str,
    max_results: int = 100,
    year_range: str | None = None,
    min_citations: int = 0,
    venue_filter: list[str] | None = None,
    api_key: str | None = None,
) -> list[dict]:
    papers, seen = [], set()
    offset = 0
    limit = min(max_results, 100)

    while offset < max_results * 3 and len(papers) < max_results:
        params = {"query": query, "offset": offset, "limit": limit, "fields": FIELDS}
        if year_range:
            params["year"] = year_range
        url = f"{S2_API}/paper/search?{urllib.parse.urlencode(params)}"
        try:
            resp = s2_request(url, api_key)
        except Exception as e:
            print(f"Warning: search failed at offset {offset}: {e}", file=sys.stderr)
            break

        data = resp.get("data", [])
        if not data:
            break

        for item in data:
            if len(papers) >= max_results:
                break
            paper = parse_paper(item)
            if not paper or paper["paperId"] in seen:
                continue
            seen.add(paper["paperId"])
            if paper["citationCount"] < min_citations:
                continue
            if venue_filter:
                v = (paper.get("venue") or "").lower()
                if not any(f.lower() in v for f in venue_filter):
                    continue
            papers.append(paper)

        total = resp.get("total", 0)
        offset += limit
        if offset >= total:
            break
        time.sleep(0.5)

    return papers


def get_citations(paper_id: str, max_results: int = 50, api_key: str | None = None) -> list[dict]:
    url = f"{S2_API}/paper/{urllib.parse.quote(paper_id, safe='')}/citations?fields={FIELDS}&limit={min(max_results, 1000)}"
    resp = s2_request(url, api_key)
    results = []
    for item in resp.get("data", []):
        paper = parse_paper(item.get("citingPaper", {}))
        if paper:
            results.append(paper)
    return results[:max_results]


def get_references(paper_id: str, max_results: int = 50, api_key: str | None = None) -> list[dict]:
    url = f"{S2_API}/paper/{urllib.parse.quote(paper_id, safe='')}/references?fields={FIELDS}&limit={min(max_results, 1000)}"
    resp = s2_request(url, api_key)
    results = []
    for item in resp.get("data", []):
        paper = parse_paper(item.get("citedPaper", {}))
        if paper:
            results.append(paper)
    return results[:max_results]


def get_recommendations(paper_id: str, max_results: int = 50, api_key: str | None = None) -> list[dict]:
    """Get paper recommendations using S2 recommendations API."""
    url = f"https://api.semanticscholar.org/recommendations/v1/papers/forpaper/{urllib.parse.quote(paper_id, safe='')}"
    params = f"?fields={FIELDS}&limit={min(max_results, 500)}"
    resp = s2_request(url + params, api_key)
    results = []
    for item in resp.get("recommendedPapers", []):
        paper = parse_paper(item)
        if paper:
            results.append(paper)
    return results[:max_results]


def main():
    parser = argparse.ArgumentParser(description="Search Semantic Scholar and output JSONL")
    parser.add_argument("--query", help="Search keywords")
    parser.add_argument("--max-results", type=int, default=50)
    parser.add_argument("--min-citations", type=int, default=0)
    parser.add_argument("--year-range", help="e.g. 2020-2026")
    parser.add_argument("--venue", nargs="*", help="Venue filter (e.g. NeurIPS ICML)")
    parser.add_argument("--citations-of", help="Get papers citing this paper ID (e.g. ARXIV:2301.07041)")
    parser.add_argument("--references-of", help="Get papers referenced by this paper ID")
    parser.add_argument("--related-to", help="Get recommended papers similar to this paper ID")
    parser.add_argument("--api-key", default=os.environ.get("S2_API_KEY"), help="S2 API key (or set S2_API_KEY env var)")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    args = parser.parse_args()

    if not args.query and not args.citations_of and not args.references_of and not args.related_to:
        print("Error: specify --query, --citations-of, --references-of, or --related-to", file=sys.stderr)
        sys.exit(1)

    if args.citations_of:
        papers = get_citations(args.citations_of, args.max_results, args.api_key)
    elif args.references_of:
        papers = get_references(args.references_of, args.max_results, args.api_key)
    elif args.related_to:
        papers = get_recommendations(args.related_to, args.max_results, args.api_key)
    else:
        papers = search_papers(
            query=args.query,
            max_results=args.max_results,
            year_range=args.year_range,
            min_citations=args.min_citations,
            venue_filter=args.venue,
            api_key=args.api_key,
        )

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    out = open(args.output, "w") if args.output else sys.stdout
    try:
        for paper in papers:
            out.write(json.dumps(paper, ensure_ascii=False) + "\n")
    finally:
        if args.output:
            out.close()

    print(f"Found {len(papers)} papers", file=sys.stderr)


if __name__ == "__main__":
    main()
