#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Download PDFs for papers found via Semantic Scholar.

Reads a JSONL file (as produced by search_semantic_scholar.py) and downloads
PDFs using the pdf_url field (typically arXiv links).

Self-contained: uses only stdlib.

Usage:
    uv run ./scripts/download_semantic_scholar.py --jsonl results.jsonl --output-dir papers/
    uv run ./scripts/download_semantic_scholar.py --jsonl results.jsonl --output-dir papers/ --max-downloads 10
    uv run ./scripts/download_semantic_scholar.py --paper-id "ARXIV:2301.07041" --output-dir papers/
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


def get_pdf_url(paper_id: str, api_key: str | None = None) -> tuple[str, str]:
    """Fetch paper metadata from S2 and return (pdf_url, filename)."""
    headers = {"User-Agent": USER_AGENT}
    if api_key:
        headers["x-api-key"] = api_key
    url = f"{S2_API}/paper/{urllib.parse.quote(paper_id, safe='')}"
    params = urllib.parse.urlencode({"fields": "externalIds,title"})
    full_url = f"{url}?{params}"
    req = urllib.request.Request(full_url, headers=headers)
    with safe_urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    arxiv_id = (data.get("externalIds") or {}).get("ArXiv", "")
    if arxiv_id:
        return f"https://arxiv.org/pdf/{arxiv_id}", f"{arxiv_id.replace('/', '_')}.pdf"
    return "", ""


def validate_pdf(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            header = f.read(5)
            if header != b"%PDF-":
                return False
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 1024))
            return b"%%EOF" in f.read()
    except Exception:
        return False


def download_pdf(url: str, dest: str, timeout: int = 60) -> bool:
    if not url.startswith("https://"):
        print(f"  Error: URL scheme not allowed: {url}", file=sys.stderr)
        return False
    part_path = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with safe_urlopen(req, timeout=timeout) as resp:
            with open(part_path, "wb") as f:
                while chunk := resp.read(8192):
                    f.write(chunk)
        if not validate_pdf(part_path):
            os.remove(part_path)
            return False
        os.rename(part_path, dest)
        return True
    except Exception as e:
        print(f"  Error: {e}", file=sys.stderr)
        if os.path.exists(part_path):
            os.remove(part_path)
        return False


def main():
    parser = argparse.ArgumentParser(description="Download PDFs for Semantic Scholar results")
    parser.add_argument("--jsonl", help="JSONL file with paper records (from search_semantic_scholar.py)")
    parser.add_argument("--paper-id", help="Single paper ID to download (e.g. ARXIV:2301.07041)")
    parser.add_argument("--output-dir", default="wiki/raw/papers", help="Output directory (default: wiki/raw/papers/)")
    parser.add_argument("--max-downloads", type=int, default=50)
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between downloads")
    parser.add_argument("--api-key", default=os.environ.get("S2_API_KEY"))
    args = parser.parse_args()

    if not args.jsonl and not args.paper_id:
        print("Error: specify --jsonl or --paper-id", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    if args.paper_id:
        pdf_url, filename = get_pdf_url(args.paper_id, args.api_key)
        if not pdf_url:
            print(f"No PDF URL found for {args.paper_id}", file=sys.stderr)
            sys.exit(1)
        dest = os.path.join(args.output_dir, filename)
        print(f"Downloading {pdf_url}...", file=sys.stderr)
        if download_pdf(pdf_url, dest):
            print(dest)
        else:
            sys.exit(1)
        return

    # Batch download from JSONL
    papers = []
    with open(args.jsonl) as f:
        for line in f:
            if line.strip():
                papers.append(json.loads(line))

    downloaded, skipped, failed = 0, 0, 0
    for paper in papers:
        if downloaded >= args.max_downloads:
            break
        pdf_url = paper.get("pdf_url", "")
        if not pdf_url:
            continue
        arxiv_id = paper.get("arxiv_id", "")
        paper_id = paper.get("paperId", "")
        name = (arxiv_id or paper_id).replace("/", "_")
        dest = os.path.join(args.output_dir, f"{name}.pdf")
        if os.path.exists(dest):
            skipped += 1
            continue
        title = paper.get("title", "")[:60]
        print(f"[{downloaded+1}/{args.max_downloads}] {title}...", file=sys.stderr)
        if download_pdf(pdf_url, dest):
            downloaded += 1
        else:
            failed += 1
        time.sleep(args.delay)

    print(f"Done: {downloaded} downloaded, {skipped} skipped, {failed} failed", file=sys.stderr)


if __name__ == "__main__":
    main()
