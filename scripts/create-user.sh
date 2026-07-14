#!/usr/bin/env bash
# create-user.sh — Create a Cognito user for the wiki webapp
#
# Usage:
#   ./create-user.sh USERNAME [--email EMAIL] [--password PASSWORD]
#
# Prerequisites:
#   - AWS CLI configured with credentials
#   - CDK stack deployed
#
# Defaults:
#   EMAIL: USERNAME@wiki.internal
#   PASSWORD: auto-generated (printed to stdout)

set -euo pipefail

REGION="${WIKI_REGION:-${AWS_REGION:-${AWS_DEFAULT_REGION:-}}}"
if [ -z "$REGION" ]; then
  REGION=$(aws configure get region 2>/dev/null || true)
fi
if [ -z "$REGION" ]; then
  echo "❌ Cannot determine AWS region. Set WIKI_REGION, AWS_REGION, or AWS_DEFAULT_REGION."
  exit 1
fi
STACK_NAME="${WIKI_STACK_NAME:-WikiPlatformStack}"

# --- Parse arguments ---
USERNAME="${1:-}"
if [ -z "$USERNAME" ]; then
  echo "Usage: $0 USERNAME [--email EMAIL] [--password PASSWORD]"
  exit 1
fi
shift

EMAIL="${USERNAME}@wiki.internal"
PASSWORD=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --email|-e) EMAIL="$2"; shift 2 ;;
    --password|-p) PASSWORD="$2"; shift 2 ;;
    *) shift ;;
  esac
done

# Generate password if not provided
if [ -z "$PASSWORD" ]; then
  PASSWORD="Wiki$(openssl rand -base64 12 | tr -dc 'A-Za-z0-9')!"
fi

# --- Get User Pool ID from stack ---
USER_POOL_ID="${WIKI_USER_POOL_ID:-}"
if [ -z "$USER_POOL_ID" ]; then
  USER_POOL_ID=$(aws cloudformation describe-stacks --region "$REGION" \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='CognitoUserPoolId'].OutputValue" \
    --output text 2>/dev/null)
fi

if [ -z "$USER_POOL_ID" ]; then
  echo "❌ Could not determine Cognito User Pool ID. Is the stack deployed?"
  exit 1
fi

echo "👤 Creating user: $USERNAME"
echo "   Email:     $EMAIL"
echo "   Pool:      $USER_POOL_ID"
echo ""

# --- Create the user ---
aws cognito-idp admin-create-user --region "$REGION" \
  --user-pool-id "$USER_POOL_ID" \
  --username "$USERNAME" \
  --user-attributes Name=email,Value="$EMAIL" Name=email_verified,Value=true \
  --temporary-password "TempPass123!" \
  --message-action SUPPRESS \
  --output text --query "User.Username"

# --- Set permanent password ---
aws cognito-idp admin-set-user-password --region "$REGION" \
  --user-pool-id "$USER_POOL_ID" \
  --username "$USERNAME" \
  --password "$PASSWORD" \
  --permanent

echo ""
echo "✅ User created successfully!"
echo ""
echo "   Username: $USERNAME"
echo "   Password: $PASSWORD"
echo ""
echo "   Login at: $(aws cloudformation describe-stacks --region "$REGION" \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='WebAppURL'].OutputValue" \
  --output text 2>/dev/null || echo 'https://<your-cloudfront-domain>')"
