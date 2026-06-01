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
sam deploy \
  --stack-name "$STACK" \
  --region "$AWS_REGION" \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --no-confirm-changeset \
  --no-fail-on-empty-changeset

BUCKET=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='CorpusBucket'].OutputValue" --output text)
URL=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)

echo "==> uploading corpus to s3://$BUCKET/corpus/"
aws s3 sync corpus/ "s3://$BUCKET/corpus/" --region "$AWS_REGION" \
  --exclude "*" --include "*.json" --include "*.f32"

echo ""
echo "✅ Deployed. Open: $URL"
