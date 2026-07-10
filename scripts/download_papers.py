#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Download PDFs from any search output JSONL (reads pdf_url field).

Works with output from search_papers.py, search_arxiv.py, search_semantic_scholar.py, or search_openalex.py.

Usage:
    uv run ./scripts/download_papers.py --jsonl results.jsonl --output-dir papers/
    uv run ./scripts/download_papers.py --jsonl results.jsonl --output-dir papers/ --max-downloads 10
    uv run ./scripts/download_papers.py --jsonl results.jsonl --output-dir papers/ --sort-by-citations
"""

import argparse
import json
import os
import sys
import time
import urllib.request

from url_utils import safe_urlopen, USER_AGENT


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


def make_filename(paper: dict) -> str:
    """Generate a filename from paper metadata."""
    name = paper.get("arxiv_id") or paper.get("doi") or paper.get("paperId") or paper.get("title", "unknown")[:40]
    name = name.replace("/", "_").replace("\\", "_").replace(":", "_").replace(" ", "_")
    if not name.endswith(".pdf"):
        name += ".pdf"
    return name


def main():
    parser = argparse.ArgumentParser(description="Download PDFs from search output JSONL")
    parser.add_argument("--jsonl", required=True, help="JSONL file with paper records (must have pdf_url field)")
    parser.add_argument("--output-dir", default="wiki/raw/papers", help="Output directory (default: wiki/raw/papers/)")
    parser.add_argument("--max-downloads", type=int, default=50, help="Max PDFs to download (default: 50)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between downloads (default: 1.0)")
    parser.add_argument("--sort-by-citations", action="store_true", help="Download most-cited first")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    papers = []
    with open(args.jsonl) as f:
        for line in f:
            if line.strip():
                papers.append(json.loads(line))

    if args.sort_by_citations:
        papers.sort(key=lambda p: p.get("citationCount") or 0, reverse=True)

    downloaded, skipped, failed = 0, 0, 0
    for paper in papers:
        if downloaded >= args.max_downloads:
            break
        pdf_url = paper.get("pdf_url", "")
        if not pdf_url:
            continue
        filename = make_filename(paper)
        dest = os.path.join(args.output_dir, filename)
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
