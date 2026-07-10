#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Find GitHub repos linked to research papers.

Searches GitHub for repositories that reference arXiv paper IDs or keywords,
targeting repos that implement or reproduce research papers.

The original Papers With Code API was deprecated (redirects to HuggingFace).
This script now uses GitHub search via `gh api` as the primary discovery method.

Usage:
    uv run ./scripts/search_paperswithcode.py --arxiv-id 2301.12345 --output repos.jsonl
    uv run ./scripts/search_paperswithcode.py --query "multi-agent" --output repos.jsonl
    uv run ./scripts/search_paperswithcode.py --arxiv-ids-file papers.txt --output repos.jsonl
    uv run ./scripts/search_paperswithcode.py --arxiv-ids 2301.12345 2305.67890 --output repos.jsonl
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

RESULTS_PER_PAGE = 30


def check_gh_installed():
    if not shutil.which("gh"):
        print("[error] gh CLI not found. Install it: https://cli.github.com/", file=sys.stderr)
        sys.exit(1)


def check_gh_auth():
    """Verify gh CLI is authenticated. Exit with clear instructions if not."""
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            print("[error] GitHub CLI is not authenticated.", file=sys.stderr)
            print("", file=sys.stderr)
            print("  Fix: run `gh auth login` and follow the prompts.", file=sys.stderr)
            print("  Or:  export GH_TOKEN=ghp_... with a valid personal access token.", file=sys.stderr)
            print("", file=sys.stderr)
            print(f"  Details: {result.stderr.strip()}", file=sys.stderr)
            sys.exit(1)
    except FileNotFoundError:
        print("[error] gh CLI not found. Install it: https://cli.github.com/", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        pass  # Non-critical, let the actual API call fail with a better error


def gh_api(endpoint: str, params: dict | None = None) -> dict | None:
    """Call gh api and return parsed JSON, or None on failure."""
    if params:
        from urllib.parse import urlencode
        endpoint = f"{endpoint}?{urlencode(params)}"
    cmd = ["gh", "api", endpoint]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"[error] gh api: {e}", file=sys.stderr)
        return None

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "rate limit" in stderr.lower() or "403" in stderr:
            print(f"[warn] rate limited: {stderr[:120]}", file=sys.stderr)
        elif "422" not in stderr:  # 422 = no results, not an error
            print(f"[warn] gh api error: {stderr[:120]}", file=sys.stderr)
        return None

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def search_repos_for_paper(query: str, max_results: int = 30) -> list[dict]:
    """Search GitHub repos matching a query string."""
    total_pages = min(3, (max_results + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE)
    items = []

    for page in range(1, total_pages + 1):
        params = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": str(min(RESULTS_PER_PAGE, max_results - len(items))),
            "page": str(page),
        }
        data = gh_api("/search/repositories", params)
        if not data:
            break

        page_items = data.get("items", [])
        if not page_items:
            break
        items.extend(page_items)

        if len(items) >= max_results:
            break
        if page < total_pages:
            time.sleep(2)  # respect rate limit

    return items[:max_results]


def map_repo(item: dict, arxiv_id: str = "", paper_title: str = "") -> dict:
    """Map a GitHub API repo item to repo_db schema."""
    owner_obj = item.get("owner") or {}
    license_obj = item.get("license") or {}

    return {
        "repo_id": item.get("full_name", ""),
        "url": item.get("html_url", ""),
        "name": item.get("name", ""),
        "owner": owner_obj.get("login", ""),
        "description": item.get("description") or "",
        "stars": item.get("stargazers_count", 0),
        "forks": item.get("forks_count", 0),
        "language": item.get("language") or "",
        "license": license_obj.get("spdx_id") or "",
        "topics": item.get("topics", []),
        "created_at": item.get("created_at", ""),
        "updated_at": item.get("updated_at", ""),
        "pushed_at": item.get("pushed_at", ""),
        "open_issues": item.get("open_issues_count", 0),
        "default_branch": item.get("default_branch", "main"),
        "archived": item.get("archived", False),
        "source": "paperswithcode",
        "paper_ids": [arxiv_id] if arxiv_id else [],
        "paper_titles": [paper_title] if paper_title else [],
        "is_official": False,
        "languages_pct": {},
        "readme_excerpt": "",
        "relevance_score": 0.0,
        "quality_score": 0.0,
        "activity_score": 0.0,
        "composite_score": 0.0,
        "tags": [],
        "analyzed": False,
        "local_path": None,
    }


def process_arxiv_id(arxiv_id: str) -> list[dict]:
    """Search GitHub for repos referencing an arXiv ID."""
    clean_id = arxiv_id.strip()
    if not clean_id:
        return []

    print(f"  arXiv:{clean_id} ...", file=sys.stderr)

    # Search in README content where arXiv IDs are typically cited
    items = search_repos_for_paper(f"{clean_id} in:readme", max_results=20)
    records = [map_repo(item, arxiv_id=clean_id) for item in items]
    print(f"    found {len(records)} repos", file=sys.stderr)
    return records


def process_query(query: str, max_results: int = 50) -> list[dict]:
    """Search GitHub for repos matching a keyword query (paper implementations)."""
    print(f"[info] searching GitHub for paper implementations: {query}", file=sys.stderr)
    items = search_repos_for_paper(query, max_results=max_results)
    records = [map_repo(item) for item in items]
    print(f"[info] found {len(records)} repos", file=sys.stderr)
    return records


def deduplicate_repos(records: list[dict]) -> list[dict]:
    """Deduplicate repos by repo_id, merging paper references."""
    seen: dict[str, dict] = {}
    for record in records:
        rid = record["repo_id"]
        if rid in seen:
            existing = seen[rid]
            for pid in record.get("paper_ids", []):
                if pid and pid not in existing["paper_ids"]:
                    existing["paper_ids"].append(pid)
            for pt in record.get("paper_titles", []):
                if pt and pt not in existing["paper_titles"]:
                    existing["paper_titles"].append(pt)
            if record.get("stars", 0) > existing.get("stars", 0):
                existing["stars"] = record["stars"]
        else:
            seen[rid] = record
    return list(seen.values())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find GitHub repos linked to research papers (via GitHub search)."
    )
    parser.add_argument("--arxiv-id", default=None, help="Single arXiv ID to look up")
    parser.add_argument("--arxiv-ids", nargs="+", default=None, help="Multiple arXiv IDs")
    parser.add_argument("--arxiv-ids-file", default=None, help="File with one arXiv ID per line")
    parser.add_argument("--query", default=None, help="Search papers by keyword")
    parser.add_argument("--output", required=True, help="Output JSONL file path")
    args = parser.parse_args()

    if not any([args.arxiv_id, args.arxiv_ids, args.arxiv_ids_file, args.query]):
        parser.error("At least one of --arxiv-id, --arxiv-ids, --arxiv-ids-file, or --query is required")

    check_gh_installed()
    check_gh_auth()

    all_arxiv_ids: list[str] = []
    if args.arxiv_id:
        all_arxiv_ids.append(args.arxiv_id)
    if args.arxiv_ids:
        all_arxiv_ids.extend(args.arxiv_ids)
    if args.arxiv_ids_file:
        ids_file = Path(args.arxiv_ids_file)
        if not ids_file.exists():
            print(f"[error] file not found: {ids_file}", file=sys.stderr)
            sys.exit(1)
        for line in ids_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                all_arxiv_ids.append(line)

    all_records: list[dict] = []

    if all_arxiv_ids:
        print(f"[info] searching {len(all_arxiv_ids)} arXiv IDs on GitHub ...", file=sys.stderr)
        for arxiv_id in all_arxiv_ids:
            records = process_arxiv_id(arxiv_id)
            all_records.extend(records)
            time.sleep(2)

    if args.query:
        records = process_query(args.query)
        all_records.extend(records)

    deduped = deduplicate_repos(all_records)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for record in deduped:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\n[info] results summary:", file=sys.stderr)
    print(f"  repos found: {len(deduped)}", file=sys.stderr)
    total_paper_links = sum(len(r.get("paper_ids", [])) for r in deduped)
    print(f"  linked to papers: {total_paper_links}", file=sys.stderr)
    print(f"[info] written to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
