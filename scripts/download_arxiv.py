#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["defusedxml"]
# ///
"""Download an arXiv paper (PDF or LaTeX source) by ID or title search.

Self-contained: uses only stdlib.

Usage:
    uv run ./scripts/download_arxiv.py --arxiv-id 2301.07041 --output-dir papers/
    uv run ./scripts/download_arxiv.py --title "Attention Is All You Need" --output-dir papers/
    uv run ./scripts/download_arxiv.py --arxiv-id 2301.07041 --format source --output-dir papers/
"""

import argparse
import os
import re
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
import defusedxml.ElementTree as ET

from url_utils import safe_urlopen, USER_AGENT

ARXIV_API = "http://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom"}


def search_by_title(title: str, max_results: int = 5) -> list[dict]:
    """Search arXiv by title and return paper metadata."""
    params = urllib.parse.urlencode({
        "search_query": f"ti:{urllib.parse.quote(title)}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    })
    url = f"{ARXIV_API}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with safe_urlopen(req, timeout=30) as resp:
        xml_data = resp.read()

    papers = []
    for entry in ET.fromstring(xml_data).findall("atom:entry", NS):
        title_el = entry.find("atom:title", NS)
        id_el = entry.find("atom:id", NS)
        if title_el is None or id_el is None:
            continue
        m = re.search(r"abs/(.+)", id_el.text)
        arxiv_id = m.group(1) if m else ""
        papers.append({
            "title": " ".join(title_el.text.strip().split()),
            "arxiv_id": arxiv_id,
        })
    return papers


def download_pdf(arxiv_id: str, output_dir: str) -> str | None:
    """Download the PDF for a given arXiv ID."""
    base_id = re.sub(r"v\d+$", "", arxiv_id)
    pdf_url = f"https://arxiv.org/pdf/{base_id}.pdf"
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{base_id.replace('/', '_')}.pdf")

    try:
        req = urllib.request.Request(pdf_url, headers={"User-Agent": USER_AGENT})
        with safe_urlopen(req, timeout=60) as resp:
            with open(out_path, "wb") as f:
                f.write(resp.read())
    except Exception as e:
        print(f"PDF download failed for {arxiv_id}: {e}", file=sys.stderr)
        return None
    return out_path


def download_source(arxiv_id: str, output_dir: str) -> str | None:
    """Download arXiv source tarball and extract .tex files."""
    base_id = re.sub(r"v\d+$", "", arxiv_id)
    source_url = f"https://arxiv.org/src/{base_id}"
    os.makedirs(output_dir, exist_ok=True)

    try:
        req = urllib.request.Request(source_url, headers={"User-Agent": USER_AGENT})
        with safe_urlopen(req, timeout=60) as resp:
            tar_data = resp.read()
    except Exception as e:
        print(f"Source download failed for {arxiv_id}: {e}", file=sys.stderr)
        return None

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp.write(tar_data)
        tmp_path = tmp.name

    safe_name = base_id.replace("/", "_")
    out_subdir = os.path.join(output_dir, safe_name)
    os.makedirs(out_subdir, exist_ok=True)

    try:
        with tarfile.open(tmp_path, "r:gz") as tar:
            tex_files = [m for m in tar.getmembers() if m.name.endswith(".tex")]
            for member in tex_files:
                f = tar.extractfile(member)
                if f is None:
                    continue
                try:
                    content = f.read().decode("utf-8")
                except UnicodeDecodeError:
                    f.seek(0)
                    content = f.read().decode("latin-1")
                safe_tex = re.sub(r"[/\\]", "_", member.name)
                with open(os.path.join(out_subdir, safe_tex), "w") as out:
                    out.write(content)
    except (tarfile.TarError, Exception) as e:
        print(f"Extraction failed for {arxiv_id}: {e}", file=sys.stderr)
        return None
    finally:
        os.unlink(tmp_path)

    if not os.listdir(out_subdir):
        print(f"No .tex files found in source for {arxiv_id}", file=sys.stderr)
        return None
    return out_subdir


def main():
    parser = argparse.ArgumentParser(description="Download an arXiv paper (PDF or source)")
    parser.add_argument("--arxiv-id", help="arXiv ID (e.g. 2301.07041 or 1706.03762)")
    parser.add_argument("--title", help="Search by title and download top result")
    parser.add_argument("--format", choices=["pdf", "source"], default="pdf", help="Download format (default: pdf)")
    parser.add_argument("--output-dir", default="wiki/raw/papers", help="Output directory (default: wiki/raw/papers/)")
    args = parser.parse_args()

    if not args.arxiv_id and not args.title:
        print("Error: specify --arxiv-id or --title", file=sys.stderr)
        sys.exit(1)

    arxiv_id = args.arxiv_id
    if not arxiv_id:
        print(f"Searching arXiv for: {args.title}", file=sys.stderr)
        results = search_by_title(args.title)
        if not results:
            print("No results found.", file=sys.stderr)
            sys.exit(1)
        for i, r in enumerate(results):
            print(f"  [{i+1}] {r['title'][:80]} ({r['arxiv_id']})", file=sys.stderr)
        arxiv_id = results[0]["arxiv_id"]
        if not arxiv_id:
            print("No arXiv ID in top result.", file=sys.stderr)
            sys.exit(1)
        print(f"Using: {arxiv_id}", file=sys.stderr)
        time.sleep(1)

    if args.format == "pdf":
        result = download_pdf(arxiv_id, args.output_dir)
    else:
        result = download_source(arxiv_id, args.output_dir)

    if result:
        print(result)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
