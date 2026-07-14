#!/usr/bin/env bash
# deploy-webapp.sh — Build and deploy the wiki webapp to S3/CloudFront
#
# Usage:
#   ./deploy-webapp.sh [--skip-build] [--skip-invalidation]
#
# Prerequisites:
#   - AWS CLI configured with appropriate credentials
#   - Node.js 18+ and npm installed
#   - CDK stack deployed (run `cdk deploy WikiPlatformStack` first)
#
# Environment variables (auto-detected from CloudFormation outputs if not set):
#   WIKI_S3_BUCKET    — S3 bucket for the React build
#   WIKI_CF_DIST_ID   — CloudFront distribution ID
#   WIKI_API_ENDPOINT — API Gateway endpoint URL
#   WIKI_USER_POOL_ID — Cognito User Pool ID
#   WIKI_CLIENT_ID    — Cognito App Client ID
#   WIKI_REGION       — AWS region (derived from AWS_REGION / AWS_DEFAULT_REGION if not set)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
WEBAPP_DIR="$SKILL_DIR/webapp"
STACK_NAME="${WIKI_STACK_NAME:-WikiPlatformStack}"
REGION="${WIKI_REGION:-${AWS_REGION:-${AWS_DEFAULT_REGION:-}}}"
if [ -z "$REGION" ]; then
  REGION=$(aws configure get region 2>/dev/null || true)
fi
if [ -z "$REGION" ]; then
  echo "❌ Cannot determine AWS region. Set WIKI_REGION, AWS_REGION, or AWS_DEFAULT_REGION."
  exit 1
fi

SKIP_BUILD=false
SKIP_INVALIDATION=false
for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=true ;;
    --skip-invalidation) SKIP_INVALIDATION=true ;;
  esac
done

# --- Auto-detect from CloudFormation outputs ---
echo "📡 Fetching stack outputs from $STACK_NAME..."
get_output() {
  aws cloudformation describe-stacks --region "$REGION" \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" \
    --output text 2>/dev/null || echo ""
}

S3_BUCKET="${WIKI_S3_BUCKET:-$(get_output ReactUIBucketName)}"
CF_DIST_ID="${WIKI_CF_DIST_ID:-$(get_output CloudFrontDistributionId)}"
API_ENDPOINT="${WIKI_API_ENDPOINT:-$(get_output ApiEndpoint)}"
USER_POOL_ID="${WIKI_USER_POOL_ID:-$(get_output CognitoUserPoolId)}"
CLIENT_ID="${WIKI_CLIENT_ID:-$(get_output CognitoClientId)}"

if [ -z "$S3_BUCKET" ]; then
  echo "❌ Could not determine S3 bucket. Is the stack deployed?"
  exit 1
fi

echo "  Bucket:       $S3_BUCKET"
echo "  Distribution: $CF_DIST_ID"
echo "  API:          $API_ENDPOINT"
echo "  Region:       $REGION"
echo ""

# --- Build ---
if [ "$SKIP_BUILD" = false ]; then
  echo "🔨 Building webapp..."
  cd "$WEBAPP_DIR"
  VITE_API_ENDPOINT="$API_ENDPOINT" \
  VITE_USER_POOL_ID="$USER_POOL_ID" \
  VITE_CLIENT_ID="$CLIENT_ID" \
  VITE_REGION="$REGION" \
  npm run build
  echo ""
fi

# --- Deploy to S3 ---
echo "🚀 Deploying to s3://$S3_BUCKET/..."
aws s3 sync "$WEBAPP_DIR/dist/" "s3://$S3_BUCKET/" \
  --region "$REGION" \
  --delete \
  --cache-control "public, max-age=31536000, immutable" \
  --exclude "index.html"

aws s3 cp "$WEBAPP_DIR/dist/index.html" "s3://$S3_BUCKET/index.html" \
  --region "$REGION" \
  --cache-control "no-cache, no-store, must-revalidate"

echo "  ✅ Upload complete"

# --- Invalidate CloudFront ---
if [ "$SKIP_INVALIDATION" = false ] && [ -n "$CF_DIST_ID" ]; then
  echo "🌐 Invalidating CloudFront distribution $CF_DIST_ID..."
  aws cloudfront create-invalidation \
    --distribution-id "$CF_DIST_ID" \
    --paths "/*" \
    --query "Invalidation.Id" --output text
  echo "  ✅ Invalidation submitted"
fi

echo ""
echo "🎉 Webapp deployed! URL: $(get_output WebAppURL)"
