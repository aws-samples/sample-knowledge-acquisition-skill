#!/usr/bin/env bash
# sync-wiki.sh — Push local wiki changes to AWS CodeCommit
#
# Usage:
#   ./sync-wiki.sh [WIKI_DIR] [--message "commit message"]
#
# Prerequisites:
#   - git-remote-codecommit installed: pip install git-remote-codecommit
#   - AWS CLI configured with credentials
#   - Wiki directory must be a git repo with 'codecommit' remote
#
# If the wiki isn't yet initialized as a git repo, this script will:
#   1. Init the repo
#   2. Add the CodeCommit remote
#   3. Push all content

set -euo pipefail

REGION="${WIKI_REGION:-${AWS_REGION:-${AWS_DEFAULT_REGION:-}}}"
if [ -z "$REGION" ]; then
  REGION=$(aws configure get region 2>/dev/null || true)
fi
if [ -z "$REGION" ]; then
  echo "❌ Cannot determine AWS region. Set WIKI_REGION, AWS_REGION, or AWS_DEFAULT_REGION."
  exit 1
fi
DEFAULT_MSG="[$(whoami)] Sync wiki content"

# Parse arguments
WIKI_DIR="${1:-${WIKI_DIR:-wiki}}"
shift 2>/dev/null || true
COMMIT_MSG="$DEFAULT_MSG"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --message|-m) COMMIT_MSG="$2"; shift 2 ;;
    *) shift ;;
  esac
done

# Resolve absolute path
WIKI_DIR="$(cd "$WIKI_DIR" && pwd)"
WIKI_NAME="$(basename "$WIKI_DIR")"
REPO_NAME="wiki-${WIKI_NAME}"

echo "📂 Wiki: $WIKI_DIR"
echo "📡 Repo: $REPO_NAME ($REGION)"
echo ""

cd "$WIKI_DIR"

# --- Initialize git if needed ---
if [ ! -d .git ]; then
  echo "🔧 Initializing git repository..."
  git init
  git checkout -b main
  git config user.name "$(whoami)"
  git config user.email "$(whoami)@wiki.internal"
fi

# --- Add CodeCommit remote if missing ---
if ! git remote get-url codecommit &>/dev/null; then
  echo "🔗 Adding CodeCommit remote..."
  git remote add codecommit "codecommit::${REGION}://${REPO_NAME}"
fi

# --- Check for changes ---
git add -A
if git diff --cached --quiet; then
  echo "✅ No changes to sync."
  exit 0
fi

# --- Commit and push ---
CHANGED_FILES=$(git diff --cached --stat | tail -1)
echo "📝 Changes: $CHANGED_FILES"
git commit -m "$COMMIT_MSG"

echo "🚀 Pushing to CodeCommit..."
if ! git push codecommit main 2>&1; then
  echo "⚠️  Push failed, attempting rebase..."
  git pull --rebase codecommit main
  git push codecommit main
fi

echo ""
echo "✅ Wiki synced successfully!"
echo "   Commit: $(git rev-parse --short HEAD)"
echo "   The wiki-indexer Lambda will rebuild graph/search data within ~30s."
