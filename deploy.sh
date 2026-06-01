#!/usr/bin/env bash
# Build + deploy Decades Trivia to AWS, then upload the corpus to S3.
set -euo pipefail

export AWS_PROFILE="${AWS_PROFILE:-watchtower}"
export AWS_REGION="${AWS_REGION:-us-east-2}"
STACK="${STACK:-decades-trivia}"

cd "$(dirname "$0")"

echo "==> sam build"
sam build

echo "==> sam deploy (stack: $STACK, region: $AWS_REGION)"
# Optional custom domain: set CERT_ARN + DOMAIN in the environment to enable.
# CorpusVersion changes every deploy so Lambda cold-starts and re-fetches corpus.
PARAMS="CertificateArn=${CERT_ARN:-} DomainName=${DOMAIN:-} CorpusVersion=$(date +%s)"
sam deploy \
  --stack-name "$STACK" \
  --region "$AWS_REGION" \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --no-confirm-changeset \
  --no-fail-on-empty-changeset \
  --parameter-overrides $PARAMS

BUCKET=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='CorpusBucket'].OutputValue" --output text)
URL=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)

echo "==> uploading corpus to s3://$BUCKET/corpus/"
aws s3 sync corpus/ "s3://$BUCKET/corpus/" --region "$AWS_REGION" \
  --exclude "*" --include "*.json" --include "*.f32"

TARGET=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='CustomDomainTarget'].OutputValue" --output text)

echo ""
echo "✅ Deployed. Open: $URL"
if [ -n "$TARGET" ] && [ "$TARGET" != "None" ]; then
  echo "   Custom domain: point ${DOMAIN:-your subdomain} CNAME -> $TARGET (DNS-only)"
fi
