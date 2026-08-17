"""Wiki Admin Lambda handler — creates and deletes wikis dynamically."""

import solution_user_agent  # noqa: F401 - registers the AWS Solutions user-agent hook; import first
import json
import os
import re
from datetime import datetime, timezone

import boto3

# Environment
DEFAULT_BRANCH = os.environ.get("DEFAULT_BRANCH", "main")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
DATA_BUCKET = os.environ.get("DATA_BUCKET", "")
REGION = os.environ.get("AWS_REGION", "us-east-1")

# Clients
codecommit = boto3.client("codecommit", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)

# Validation
SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9\-]{1,49}$")


def response(status_code: int, body: dict) -> dict:
    """Build API Gateway HTTP API response."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def validate_name(name: str) -> str | None:
    """Return error message if name is invalid, else None."""
    if not name:
        return "name is required"
    if not SLUG_PATTERN.match(name):
        return (
            "name must be lowercase, start with a letter, contain only "
            "letters/digits/hyphens, and be 2-50 characters"
        )
    return None


def create_wiki(event: dict) -> dict:
    """Handle POST /api/wikis — create a new wiki."""
    # Parse body
    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return response(400, {"error": "Invalid JSON body"})

    name = body.get("name", "").strip()
    description = body.get("description", "").strip()
    owner = body.get("owner", "").strip()

    # Validate required fields
    if not owner:
        return response(400, {"error": "owner is required"})
    if not description:
        return response(400, {"error": "description is required"})

    name_error = validate_name(name)
    if name_error:
        return response(400, {"error": name_error})

    repo_name = f"wiki-{name}"
    now = datetime.now(timezone.utc).isoformat()

    # 1. Create CodeCommit repository
    try:
        codecommit.create_repository(
            repositoryName=repo_name,
            repositoryDescription=description,
            tags={
                "wiki": "true",
                "wiki:name": name,
                "wiki:owner": owner,
            },
        )
    except codecommit.exceptions.RepositoryNameExistsException:
        return response(409, {"error": f"Wiki '{name}' already exists"})

    # 2. Seed with initial commit
    schema_md = (
        "# Wiki Schema\n\n"
        "## Conventions\n\n"
        "- One topic per file, named as a slug (e.g. `my-topic.md`)\n"
        "- Use `[[link]]` syntax for internal cross-references\n"
        "- Keep files under 10 KB for optimal retrieval\n"
        "- Tag files with YAML frontmatter: `tags`, `created`, `updated`\n"
    )

    index_md = (
        "# Index\n\n"
        "<!-- Auto-generated index of wiki pages -->\n"
    )

    log_md = (
        "# Change Log\n\n"
        f"- **{now}** — Wiki `{name}` created by `{owner}`\n"
    )

    try:
        codecommit.create_commit(
            repositoryName=repo_name,
            branchName=DEFAULT_BRANCH,
            putFiles=[
                {
                    "filePath": "SCHEMA.md",
                    "fileContent": schema_md.encode("utf-8"),
                },
                {
                    "filePath": "index.md",
                    "fileContent": index_md.encode("utf-8"),
                },
                {
                    "filePath": "log.md",
                    "fileContent": log_md.encode("utf-8"),
                },
            ],
            commitMessage=f"Initial commit — wiki '{name}' created",
            name="wiki-admin",
            email="wiki-admin@lambda.local",
        )
    except Exception as e:
        # Repo was created but seeding failed — best-effort cleanup info
        return response(500, {"error": f"Repo created but seed commit failed: {str(e)}"})

    # 3. Write SSM parameter
    clone_url_http = (
        f"https://git-codecommit.{REGION}.amazonaws.com/v1/repos/{repo_name}"
    )

    wiki_metadata = {
        "name": name,
        "description": description,
        "repositoryName": repo_name,
        "cloneUrlHttp": clone_url_http,
        "snsTopicArn": SNS_TOPIC_ARN,
        "owner": owner,
        "createdAt": now,
    }

    ssm.put_parameter(
        Name=f"/wikis/{name}",
        Description=f"Wiki metadata for {name}",
        Value=json.dumps(wiki_metadata),
        Type="String",
        Overwrite=False,
    )

    return response(201, wiki_metadata)


def delete_wiki(event: dict) -> dict:
    """Handle DELETE /api/wikis?wiki={name} — archive a wiki."""
    params = event.get("queryStringParameters") or {}
    name = params.get("wiki", "").strip()

    if not name:
        return response(400, {"error": "query parameter 'wiki' is required"})

    repo_name = f"wiki-{name}"

    # 1. Delete SSM parameter
    try:
        ssm.delete_parameter(Name=f"/wikis/{name}")
    except ssm.exceptions.ParameterNotFound:
        return response(404, {"error": f"Wiki '{name}' not found"})

    # 2. Delete S3 objects under data/{name}/
    if DATA_BUCKET:
        prefix = f"data/{name}/"
        try:
            paginator = s3.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=DATA_BUCKET, Prefix=prefix)

            for page in pages:
                objects = page.get("Contents", [])
                if objects:
                    delete_keys = [{"Key": obj["Key"]} for obj in objects]
                    s3.delete_objects(
                        Bucket=DATA_BUCKET,
                        Delete={"Objects": delete_keys, "Quiet": True},
                    )
        except Exception:
            # Best-effort S3 cleanup — don't fail the whole delete
            pass

    # 3. Tag repo as archived (don't delete it)
    try:
        repo_arn = (
            f"arn:aws:codecommit:{REGION}:"
            f"{boto3.client('sts').get_caller_identity()['Account']}:{repo_name}"
        )
        codecommit.tag_resource(
            resourceArn=repo_arn,
            tags={"wiki:archived": "true"},
        )
    except Exception:
        # Best-effort tagging — repo may not exist if manually deleted
        pass

    return response(200, {"deleted": name})


def handler(event: dict, context) -> dict:
    """Lambda entry point for API Gateway HTTP API."""
    try:
        method = event["requestContext"]["http"]["method"]

        if method == "POST":
            return create_wiki(event)
        elif method == "DELETE":
            return delete_wiki(event)
        else:
            return response(405, {"error": f"Method {method} not allowed"})

    except KeyError as e:
        return response(400, {"error": f"Malformed event: missing {str(e)}"})
    except Exception as e:
        return response(500, {"error": f"Internal error: {str(e)}"})
