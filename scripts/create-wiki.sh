#!/usr/bin/env bash
# create-wiki.sh — Register a local wiki directory on the AWS platform
#
# Usage:
#   ./create-wiki.sh WIKI_DIR [--description "..."] [--owner ALIAS]
#
# This script:
#   1. Creates a CodeCommit repository for the wiki
#   2. Registers the wiki in SSM Parameter Store for discovery
#   3. Initializes the local directory as a git repo
#   4. Pushes all content to CodeCommit
#
# Prerequisites:
#   - AWS CLI configured with credentials
#   - git-remote-codecommit installed: pip install git-remote-codecommit
#   - CDK stack deployed

set -euo pipefail

REGION="${WIKI_REGION:-${AWS_REGION:-${AWS_DEFAULT_REGION:-}}}"
if [ -z "$REGION" ]; then
  REGION=$(aws configure get region 2>/dev/null || true)
fi
if [ -z "$REGION" ]; then
  echo "❌ Cannot determine AWS region. Set WIKI_REGION, AWS_REGION, or AWS_DEFAULT_REGION."
  exit 1
fi

# --- Parse arguments ---
WIKI_DIR="${1:-}"
if [ -z "$WIKI_DIR" ]; then
  echo "Usage: $0 WIKI_DIR [--description \"...\"] [--owner ALIAS]"
  exit 1
fi
shift

WIKI_DIR="$(cd "$WIKI_DIR" && pwd)"
WIKI_NAME="$(basename "$WIKI_DIR")"
REPO_NAME="wiki-${WIKI_NAME}"
DESCRIPTION="Knowledge base: $WIKI_NAME"
OWNER="$(whoami)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --description|-d) DESCRIPTION="$2"; shift 2 ;;
    --owner|-o) OWNER="$2"; shift 2 ;;
    *) shift ;;
  esac
done

echo "📚 Creating wiki on platform"
echo "   Name:        $WIKI_NAME"
echo "   Repository:  $REPO_NAME"
echo "   Region:      $REGION"
echo "   Owner:       $OWNER"
echo "   Description: $DESCRIPTION"
echo ""

# --- Create CodeCommit repository ---
echo "📦 Creating CodeCommit repository..."
if aws codecommit get-repository --repository-name "$REPO_NAME" --region "$REGION" &>/dev/null; then
  echo "   Repository already exists, skipping creation."
else
  aws codecommit create-repository \
    --repository-name "$REPO_NAME" \
    --repository-description "$DESCRIPTION" \
    --region "$REGION" \
    --query "repositoryMetadata.cloneUrlHttp" --output text
  echo "   ✅ Repository created"
fi

# --- Register in SSM ---
echo "📡 Registering in SSM Parameter Store..."
CLONE_URL="https://git-codecommit.${REGION}.amazonaws.com/v1/repos/${REPO_NAME}"
CREATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

aws ssm put-parameter --region "$REGION" \
  --name "/wikis/${WIKI_NAME}" \
  --type String \
  --value "{\"name\":\"${WIKI_NAME}\",\"description\":\"${DESCRIPTION}\",\"repositoryName\":\"${REPO_NAME}\",\"cloneUrlHttp\":\"${CLONE_URL}\",\"owner\":\"${OWNER}\",\"createdAt\":\"${CREATED_AT}\"}" \
  --overwrite --output text >/dev/null
echo "   ✅ Registered at /wikis/${WIKI_NAME}"

# --- Initialize git and push ---
echo "🔗 Initializing git and pushing content..."
cd "$WIKI_DIR"

if [ ! -d .git ]; then
  git init
  git checkout -b main
  git config user.name "$OWNER"
  git config user.email "${OWNER}@wiki.internal"
fi

git remote remove codecommit 2>/dev/null || true
git remote add codecommit "codecommit::${REGION}://${REPO_NAME}"

git add -A
git commit -m "[${OWNER}] Initial wiki push" --allow-empty 2>/dev/null || true
git push codecommit main 2>&1 | tail -5

echo ""
echo "✅ Wiki created and pushed!"
echo ""
echo "   Web:     Will be visible at the platform webapp after indexing (~30s)"
echo "   Clone:   git clone codecommit::${REGION}://${REPO_NAME}"
echo "   Sync:    $0/../sync-wiki.sh ${WIKI_DIR}"
