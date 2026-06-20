#!/usr/bin/env bash
# Merge missing joblens/app secret fields (run locally with admin AWS creds).
# Never prints secret values. Optional env: LANGCHAIN_API_KEY or LANGSMITH_API_KEY.
set -euo pipefail

REGION="${AWS_REGION:-us-east-2}"
SECRET_ID="${SECRET_ID:-joblens/app}"

CURRENT=$(aws secretsmanager get-secret-value --secret-id "$SECRET_ID" --region "$REGION" --query SecretString --output text)
UPDATED="$CURRENT"
CHANGED=0

add_field() {
  local key="$1" value="$2"
  if [[ -z "$value" || "$value" == "null" ]]; then
    return
  fi
  UPDATED=$(echo "$UPDATED" | jq --arg k "$key" --arg v "$value" '. + {($k): $v}')
  CHANGED=1
  echo "set $key"
}

if [[ -z "$(echo "$CURRENT" | jq -r '.JWT_SECRET // empty')" ]]; then
  add_field JWT_SECRET "$(openssl rand -hex 32)"
fi

if [[ -z "$(echo "$UPDATED" | jq -r '.LANGSMITH_PROJECT // empty')" ]]; then
  add_field LANGSMITH_PROJECT "joblens-analyze"
fi

LS_KEY="${LANGCHAIN_API_KEY:-${LANGSMITH_API_KEY:-}}"
if [[ -n "$LS_KEY" ]]; then
  add_field LANGCHAIN_API_KEY "$LS_KEY"
elif [[ -z "$(echo "$UPDATED" | jq -r '.LANGCHAIN_API_KEY // .LANGSMITH_API_KEY // empty')" ]]; then
  echo "skip LANGCHAIN_API_KEY (pass LANGCHAIN_API_KEY=... to enable LangSmith)"
fi

if [[ "$CHANGED" -eq 0 ]]; then
  echo "joblens/app already complete — no changes"
  exit 0
fi

aws secretsmanager put-secret-value \
  --secret-id "$SECRET_ID" \
  --region "$REGION" \
  --secret-string "$UPDATED" >/dev/null

echo "updated $SECRET_ID ($(echo "$UPDATED" | jq -r 'keys | join(", ")'))"
