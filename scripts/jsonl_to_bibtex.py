#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Convert search output JSONL to BibTeX format.

Works with output from any search script (search_papers.py, search_arxiv.py, etc.).

Usage:
    uv run ./scripts/jsonl_to_bibtex.py --jsonl results.jsonl --output refs.bib
    uv run ./scripts/jsonl_to_bibtex.py --jsonl results.jsonl
"""

import argparse
import json
import os
import re
import sys

COMMON_WORDS = {
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or",
    "is", "are", "was", "were", "be", "been", "with", "from", "by", "as",
}


def make_key(paper: dict) -> str:
    authors = paper.get("authors", [])
    family = ""
    if authors:
        name = authors[0] if isinstance(authors[0], str) else authors[0].get("name", "")
        parts = name.split()
        family = re.sub(r"[^a-zA-Z]", "", parts[-1]).lower() if parts else ""
    year = str(paper.get("year") or "")
    title = paper.get("title", "")
    words = [w.lower() for w in re.findall(r"[A-Za-z]+", title) if w.lower() not in COMMON_WORDS]
    title_word = words[0] if words else ""
    return family + year + title_word or "unknown"


def paper_to_bibtex(paper: dict, key: str) -> str:
    authors = paper.get("authors", [])
    if authors and isinstance(authors[0], dict):
        author_str = " and ".join(a.get("name", "") for a in authors)
    else:
        author_str = " and ".join(authors)

    venue = paper.get("venue", "")
    entry_type = "inproceedings" if venue else "article"

    lines = [f"@{entry_type}{{{key},"]
    lines.append(f"  author = {{{author_str}}},")
    lines.append(f"  title = {{{paper.get('title', '')}}},")
    if venue:
        lines.append(f"  booktitle = {{{venue}}},")
    if paper.get("year"):
        lines.append(f"  year = {{{paper['year']}}},")
    if paper.get("doi"):
        lines.append(f"  doi = {{{paper['doi']}}},")
    arxiv_id = paper.get("arxiv_id", "")
    if arxiv_id:
        lines.append(f"  eprint = {{{arxiv_id}}},")
        lines.append(f"  archiveprefix = {{arXiv}},")
    lines.append("}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Convert search JSONL to BibTeX")
    parser.add_argument("--jsonl", required=True, help="Input JSONL file")
    parser.add_argument("--output", "-o", help="Output .bib file (default: stdout)")
    args = parser.parse_args()

    papers = []
    with open(args.jsonl) as f:
        for line in f:
            if line.strip():
                papers.append(json.loads(line))

    used_keys = set()
    entries = []
    for paper in papers:
        key = make_key(paper)
        orig = key
        i = 0
        while key in used_keys:
            i += 1
            key = orig + chr(ord("a") + i - 1)
        used_keys.add(key)
        entries.append(paper_to_bibtex(paper, key))

    text = "\n\n".join(entries) + "\n" if entries else ""
    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as f:
            f.write(text)
        print(f"Wrote {len(entries)} BibTeX entries to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
