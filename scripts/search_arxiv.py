#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["defusedxml"]
# ///
"""Search arXiv papers via the Atom API and output JSONL metadata.

Self-contained: uses only stdlib (urllib, xml.etree).

Usage:
    uv run ./scripts/search_arxiv.py --query "long context reasoning" --max-results 20
    uv run ./scripts/search_arxiv.py --query "LLM agent" --categories cs.AI cs.CL --sort-by lastUpdatedDate
    uv run ./scripts/search_arxiv.py --query "diffusion models" --start-date 2024-06-01 --output results.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from xml.etree.ElementTree import Element

from url_utils import safe_urlopen, USER_AGENT
import defusedxml.ElementTree as ET

ARXIV_API = "http://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def build_query(keywords: str, categories: list[str] | None = None) -> str:
    parts = [f"all:{keywords}"]
    if categories:
        cat_query = " OR ".join(f"cat:{c}" for c in categories)
        parts.append(f"({cat_query})")
    return " AND ".join(parts)


def fetch_page(query: str, start: int, max_results: int, sort_by: str) -> bytes:
    params = {
        "search_query": query,
        "start": start,
        "max_results": max_results,
        "sortBy": sort_by,
        "sortOrder": "descending",
    }
    url = f"{ARXIV_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with safe_urlopen(req, timeout=30) as resp:
        return resp.read()


def parse_entry(entry: Element) -> dict:
    def text(tag: str, ns: str = "atom") -> str:
        el = entry.find(f"{ns}:{tag}", NS)
        return el.text.strip() if el is not None and el.text else ""

    entry_id = text("id")
    arxiv_id = entry_id.split("/abs/")[-1] if "/abs/" in entry_id else entry_id

    authors = [
        a.find("atom:name", NS).text.strip()
        for a in entry.findall("atom:author", NS)
        if a.find("atom:name", NS) is not None
    ]

    categories = []
    for cat_el in entry.findall("arxiv:primary_category", NS):
        if t := cat_el.get("term"):
            categories.append(t)
    for cat_el in entry.findall("atom:category", NS):
        if (t := cat_el.get("term")) and t not in categories:
            categories.append(t)

    pdf_url = ""
    for link_el in entry.findall("atom:link", NS):
        if link_el.get("title") == "pdf":
            pdf_url = link_el.get("href", "")
            break
    if not pdf_url and arxiv_id:
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"

    published = text("published")
    return {
        "arxiv_id": arxiv_id,
        "title": " ".join(text("title").split()),
        "authors": authors,
        "abstract": " ".join(text("summary").split()),
        "published": published,
        "year": int(published[:4]) if len(published) >= 4 else None,
        "categories": categories,
        "pdf_url": pdf_url,
        "comment": text("comment", "arxiv"),
    }


def search(
    keywords: str,
    categories: list[str] | None = None,
    max_results: int = 50,
    sort_by: str = "relevance",
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    query = build_query(keywords, categories)
    page_size = min(max_results, 100)
    papers, seen = [], set()

    for start in range(0, max_results, page_size):
        try:
            xml_data = fetch_page(query, start, min(page_size, max_results - start), sort_by)
        except Exception as e:
            print(f"Warning: fetch failed at offset {start}: {e}", file=sys.stderr)
            break

        entries = ET.fromstring(xml_data).findall("atom:entry", NS)
        if not entries:
            break

        for entry in entries:
            paper = parse_entry(entry)
            if not paper["title"] or paper["arxiv_id"] in seen:
                continue
            pub = paper["published"][:10]
            if start_date and pub < start_date:
                continue
            if end_date and pub > end_date:
                continue
            seen.add(paper["arxiv_id"])
            papers.append(paper)

        if start + page_size < max_results:
            time.sleep(3)  # respect arXiv rate limit

    return papers


def main():
    parser = argparse.ArgumentParser(description="Search arXiv and output JSONL")
    parser.add_argument("--query", required=True, help="Search keywords")
    parser.add_argument("--max-results", type=int, default=50)
    parser.add_argument("--categories", nargs="*", help="e.g. cs.AI cs.CL q-bio.BM")
    parser.add_argument("--sort-by", choices=["relevance", "lastUpdatedDate", "submittedDate"], default="relevance")
    parser.add_argument("--start-date", help="YYYY-MM-DD")
    parser.add_argument("--end-date", help="YYYY-MM-DD")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    args = parser.parse_args()

    papers = search(
        keywords=args.query,
        categories=args.categories,
        max_results=args.max_results,
        sort_by=args.sort_by,
        start_date=args.start_date,
        end_date=args.end_date,
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
