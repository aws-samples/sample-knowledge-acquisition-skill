"""
Wiki Indexer Lambda Handler

Triggered by EventBridge when any wiki-* CodeCommit repo is pushed to.
Builds static JSON artifacts (graph.json, index.json, search.json) and
writes them to S3, then invalidates the CloudFront distribution.
"""

import solution_user_agent  # noqa: F401 - registers the AWS Solutions user-agent hook; import first
import json
import os
import re
import logging
import boto3
from collections import Counter
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_BRANCH = os.environ.get("DEFAULT_BRANCH", "main")
DATA_BUCKET = os.environ["DATA_BUCKET"]
DISTRIBUTION_ID = os.environ["DISTRIBUTION_ID"]
AWS_REGION = os.environ.get("AWS_REGION", "eu-west-2")

codecommit = boto3.client("codecommit", region_name=AWS_REGION)
s3 = boto3.client("s3", region_name=AWS_REGION)
cloudfront = boto3.client("cloudfront", region_name=AWS_REGION)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def get_all_files(repo_name: str, branch: str, folder_path: str = "/") -> list[dict]:
    """Recursively read all .md files from the repo using GetFolder + GetFile."""
    files = []

    try:
        response = codecommit.get_folder(
            repositoryName=repo_name,
            commitSpecifier=branch,
            folderPath=folder_path,
        )
    except Exception as e:
        logger.error(f"Error getting folder '{folder_path}': {e}")
        return files

    # Process files in this folder
    for file_info in response.get("files", []):
        abs_path = file_info["absolutePath"]
        if abs_path.endswith(".md"):
            try:
                file_response = codecommit.get_file(
                    repositoryName=repo_name,
                    commitSpecifier=branch,
                    filePath=abs_path,
                )
                content = file_response["fileContent"].decode("utf-8")
                files.append({"path": abs_path, "content": content})
            except UnicodeDecodeError:
                logger.warning(f"Skipping binary/non-UTF8 file: {abs_path}")
            except Exception as e:
                logger.error(f"Error reading file '{abs_path}': {e}")

    # Recurse into subfolders
    for subfolder in response.get("subFolders", []):
        sub_path = subfolder["absolutePath"]
        files.extend(get_all_files(repo_name, branch, sub_path))

    return files


def path_to_slug(file_path: str) -> str:
    """Convert file path to slug: 'concepts/foo-bar.md' → 'foo-bar'."""
    filename = os.path.basename(file_path)
    slug, _ = os.path.splitext(filename)
    return slug


def extract_title(content: str) -> str:
    """Extract the first line starting with '# '."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def extract_front_matter_tags(content: str) -> list[str]:
    """Parse YAML front-matter between --- delimiters and extract 'tags' key."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return []

    front_matter = match.group(1)
    # Simple YAML parsing for tags — handles:
    #   tags: [a, b, c]
    #   tags:\n  - a\n  - b
    for line in front_matter.splitlines():
        stripped = line.strip()
        if stripped.startswith("tags:"):
            # Inline list: tags: [a, b, c]
            inline = stripped[5:].strip()
            if inline.startswith("["):
                items = inline.strip("[]").split(",")
                return [t.strip().strip("'\"") for t in items if t.strip()]
            # Single value on same line
            if inline and not inline.startswith("-"):
                return [inline.strip("'\"")]
            # Multi-line list follows
            tags = []
            idx = front_matter.splitlines().index(line) + 1
            lines = front_matter.splitlines()
            while idx < len(lines):
                tag_line = lines[idx].strip()
                if tag_line.startswith("- "):
                    tags.append(tag_line[2:].strip().strip("'\""))
                    idx += 1
                else:
                    break
            return tags

    return []


def extract_headings(content: str) -> list[str]:
    """Extract lines starting with ## or ###."""
    headings = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") or stripped.startswith("### "):
            # Remove the leading # symbols
            heading_text = re.sub(r"^#{2,3}\s+", "", stripped)
            headings.append(heading_text)
    return headings


def strip_markdown(content: str) -> str:
    """Remove markdown syntax: front-matter, #, *, [], (), ```, ---."""
    # Remove front-matter
    text = re.sub(r"^---\s*\n.*?\n---\s*\n", "", content, flags=re.DOTALL)
    # Remove code blocks
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    # Remove inline code
    text = re.sub(r"`[^`]*`", "", text)
    # Remove headings markers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove wikilinks but keep text
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    # Remove markdown links [text](url) → text
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # Remove images ![alt](url)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    # Remove bold/italic markers
    text = re.sub(r"[*_]{1,3}", "", text)
    # Remove horizontal rules
    text = re.sub(r"^-{3,}\s*$", "", text, flags=re.MULTILINE)
    # Remove blockquotes
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    # Remove list markers
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    # Collapse whitespace
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def find_wikilinks(content: str) -> list[str]:
    """Find all [[wikilinks]] in content."""
    return re.findall(r"\[\[([^\]]+)\]\]", content)


def extract_group(file_path: str) -> str:
    """Extract top-level folder as group (concepts, entities, comparisons, queries, errors)."""
    parts = file_path.split("/")
    if len(parts) > 1:
        return parts[0]
    return "root"


# ---------------------------------------------------------------------------
# Artifact builders
# ---------------------------------------------------------------------------


def build_graph(files_data: list[dict], commit_id: str) -> dict:
    """Build graph.json with nodes, edges, and metadata."""
    nodes = []
    edges = []
    connection_count = Counter()

    # Build slug → file data mapping
    slug_set = set()
    for fd in files_data:
        slug_set.add(fd["slug"])

    for fd in files_data:
        slug = fd["slug"]
        wikilinks = fd["wikilinks"]

        nodes.append({
            "id": slug,
            "label": fd["title"] or slug,
            "group": fd["group"],
            "size": len(wikilinks),
        })

        for target in wikilinks:
            # Normalise wikilink target to slug format
            target_slug = target.lower().replace(" ", "-")
            if target_slug in slug_set:
                edges.append({"source": slug, "target": target_slug})
                connection_count[slug] += 1
                connection_count[target_slug] += 1

    # Calculate orphans (nodes with no connections)
    connected_nodes = set()
    for edge in edges:
        connected_nodes.add(edge["source"])
        connected_nodes.add(edge["target"])
    orphans = [n["id"] for n in nodes if n["id"] not in connected_nodes]

    # Most connected node
    most_connected = connection_count.most_common(1)[0][0] if connection_count else ""

    metadata = {
        "totalNodes": len(nodes),
        "totalEdges": len(edges),
        "orphans": len(orphans),
        "mostConnected": most_connected,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "commitId": commit_id,
    }

    return {"nodes": nodes, "edges": edges, "metadata": metadata}


def build_index(files_data: list[dict]) -> dict:
    """Build index.json mapping slug → file_path."""
    return {fd["slug"]: fd["path"] for fd in files_data}


def build_search(files_data: list[dict]) -> dict:
    """Build search.json with document entries for client-side search."""
    documents = []
    for fd in files_data:
        documents.append({
            "id": fd["slug"],
            "title": fd["title"],
            "group": fd["group"],
            "tags": fd["tags"],
            "headings": fd["headings"],
            "body": fd["body"][:500],
        })

    return {
        "documents": documents,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# S3 and CloudFront operations
# ---------------------------------------------------------------------------


def write_to_s3(wiki_name: str, filename: str, data: dict) -> None:
    """Write a JSON artifact to S3."""
    key = f"data/{wiki_name}/{filename}"
    s3.put_object(
        Bucket=DATA_BUCKET,
        Key=key,
        Body=json.dumps(data, ensure_ascii=False, indent=None),
        ContentType="application/json",
        CacheControl="public, max-age=60",
    )
    logger.info(f"Wrote s3://{DATA_BUCKET}/{key}")


def invalidate_cloudfront(wiki_name: str) -> None:
    """Invalidate CloudFront cache for the wiki's data path."""
    cloudfront.create_invalidation(
        DistributionId=DISTRIBUTION_ID,
        InvalidationBatch={
            "Paths": {
                "Quantity": 1,
                "Items": [f"/data/{wiki_name}/*"],
            },
            "CallerReference": f"{wiki_name}-{datetime.now(timezone.utc).isoformat()}",
        },
    )
    logger.info(f"CloudFront invalidation created for /data/{wiki_name}/*")


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------


def handler(event, context):
    """Main Lambda handler triggered by EventBridge on CodeCommit push."""
    logger.info(f"Event received: {json.dumps(event)}")

    # 1. Extract repo name and branch from event
    detail = event.get("detail", {})
    repo_name = detail.get("repositoryName", "")
    reference_name = detail.get("referenceName", "")
    commit_id = detail.get("commitId", "")

    if not repo_name:
        logger.error("No repositoryName in event detail")
        return {"statusCode": 400, "body": "Missing repositoryName"}

    # 2. Derive wiki name
    wiki_name = repo_name.removeprefix("wiki-")

    # 3. Only process the default branch
    if reference_name != DEFAULT_BRANCH:
        logger.info(
            f"Skipping branch '{reference_name}' (only processing '{DEFAULT_BRANCH}')"
        )
        return {"statusCode": 200, "body": f"Skipped branch {reference_name}"}

    logger.info(f"Processing wiki '{wiki_name}' from repo '{repo_name}' at commit {commit_id}")

    # 4. Recursively read all .md files
    raw_files = get_all_files(repo_name, DEFAULT_BRANCH)
    logger.info(f"Found {len(raw_files)} markdown files")

    if not raw_files:
        logger.warning("No markdown files found — skipping artifact generation")
        return {"statusCode": 200, "body": "No markdown files found"}

    # 5. Process each file
    files_data = []
    for file_info in raw_files:
        path = file_info["path"]
        content = file_info["content"]

        slug = path_to_slug(path)
        title = extract_title(content)
        group = extract_group(path)
        tags = extract_front_matter_tags(content)
        headings = extract_headings(content)
        body = strip_markdown(content)
        wikilinks = find_wikilinks(content)

        files_data.append({
            "path": path,
            "slug": slug,
            "title": title,
            "group": group,
            "tags": tags,
            "headings": headings,
            "body": body,
            "wikilinks": wikilinks,
        })

    logger.info(f"Processed {len(files_data)} files")

    # 6. Build artifacts
    graph = build_graph(files_data, commit_id)
    index = build_index(files_data)
    search = build_search(files_data)

    # 7. Write to S3
    write_to_s3(wiki_name, "graph.json", graph)
    write_to_s3(wiki_name, "index.json", index)
    write_to_s3(wiki_name, "search.json", search)

    # 8. Invalidate CloudFront
    invalidate_cloudfront(wiki_name)

    summary = {
        "wiki_name": wiki_name,
        "files_processed": len(files_data),
        "nodes": graph["metadata"]["totalNodes"],
        "edges": graph["metadata"]["totalEdges"],
        "orphans": graph["metadata"]["orphans"],
    }
    logger.info(f"Indexing complete: {json.dumps(summary)}")

    return {"statusCode": 200, "body": json.dumps(summary)}
