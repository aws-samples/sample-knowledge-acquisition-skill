#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Local paper database — tracks downloaded papers, avoids re-downloads, enables local queries.

Maintains a JSONL index of papers with metadata and local file paths.

Usage:
    uv run ./scripts/paper_db.py add --jsonl results.jsonl --db papers.db.jsonl
    uv run ./scripts/paper_db.py list --db papers.db.jsonl
    uv run ./scripts/paper_db.py search --db papers.db.jsonl --query "attention"
    uv run ./scripts/paper_db.py has --db papers.db.jsonl --arxiv-id 2301.07041
"""

import argparse
import json
import os
import re
import sys


def load_db(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    papers = []
    with open(path) as f:
        for line in f:
            if line.strip():
                papers.append(json.loads(line))
    return papers


def save_db(papers: list[dict], path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        for p in papers:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")


def dedup_key(paper: dict) -> str:
    return paper.get("arxiv_id") or paper.get("doi") or paper.get("paperId") or paper.get("title", "")


def cmd_add(args):
    db = load_db(args.db)
    existing_keys = {dedup_key(p) for p in db}

    new_papers = []
    with open(args.jsonl) as f:
        for line in f:
            if not line.strip():
                continue
            paper = json.loads(line)
            key = dedup_key(paper)
            if key and key not in existing_keys:
                existing_keys.add(key)
                new_papers.append(paper)

    db.extend(new_papers)
    save_db(db, args.db)
    print(f"Added {len(new_papers)} new papers (total: {len(db)})", file=sys.stderr)


def cmd_list(args):
    db = load_db(args.db)
    for p in db:
        aid = p.get("arxiv_id", "")
        title = p.get("title", "")[:80]
        year = str(p.get("year") or "—")
        cites = str(p.get("citationCount") or "?")
        print(f"{aid or '—':20s} {year:4s} [{cites:>4s}] {title}")
    print(f"\nTotal: {len(db)} papers", file=sys.stderr)


def cmd_search(args):
    db = load_db(args.db)
    query_lower = args.query.lower()
    matches = []
    for p in db:
        text = f"{p.get('title', '')} {p.get('abstract', '')} {' '.join(p.get('authors', []))}".lower()
        if query_lower in text:
            matches.append(p)
    for p in matches:
        sys.stdout.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"Found {len(matches)} matches", file=sys.stderr)


def cmd_has(args):
    db = load_db(args.db)
    for p in db:
        if p.get("arxiv_id") == args.arxiv_id:
            print("true")
            return
    print("false")


def main():
    parser = argparse.ArgumentParser(description="Local paper database")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Add papers from JSONL to the database")
    p_add.add_argument("--jsonl", required=True, help="JSONL file to import")
    p_add.add_argument("--db", default="wiki/raw/papers.db.jsonl", help="Database file (default: papers.db.jsonl)")

    p_list = sub.add_parser("list", help="List all papers in the database")
    p_list.add_argument("--db", default="wiki/raw/papers.db.jsonl")

    p_search = sub.add_parser("search", help="Search papers in the database")
    p_search.add_argument("--query", required=True, help="Search text")
    p_search.add_argument("--db", default="wiki/raw/papers.db.jsonl")

    p_has = sub.add_parser("has", help="Check if a paper exists in the database")
    p_has.add_argument("--arxiv-id", required=True)
    p_has.add_argument("--db", default="wiki/raw/papers.db.jsonl")

    args = parser.parse_args()
    if args.command == "add":
        cmd_add(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "has":
        cmd_has(args)


if __name__ == "__main__":
    main()
