#!/usr/bin/env bash
# Redeploy JobLens backend on EC2 (run on instance or via SSM).
set -euo pipefail

REGION="${AWS_REGION:-us-east-2}"
APP_DIR="${APP_DIR:-/opt/joblens}"

cd "$APP_DIR"
git fetch origin main
git reset --hard origin/main

RDS_JSON=$(aws secretsmanager get-secret-value --secret-id joblens/rds --region "$REGION" --query SecretString --output text)
APP_JSON=$(aws secretsmanager get-secret-value --secret-id joblens/app --region "$REGION" --query SecretString --output text)

RDS_HOST=$(echo "$RDS_JSON" | jq -r '.host // empty')
if [[ -z "$RDS_HOST" || "$RDS_HOST" == "null" ]]; then
  RDS_HOST=$(aws rds describe-db-instances --db-instance-identifier joblens-db --region "$REGION" \
    --query 'DBInstances[0].Endpoint.Address' --output text)
fi
RDS_USER=$(echo "$RDS_JSON" | jq -r .username)
RDS_PASS=$(echo "$RDS_JSON" | jq -r .password)
RDS_DB=$(echo "$RDS_JSON" | jq -r .database)

export PGPASSWORD="$RDS_PASS"
psql -h "$RDS_HOST" -U "$RDS_USER" -d "$RDS_DB" -f deploy/rds-init.sql
psql -h "$RDS_HOST" -U "$RDS_USER" -d "$RDS_DB" -f db/auth_schema.sql

JWT_SECRET=$(echo "$APP_JSON" | jq -r '.JWT_SECRET // empty')
if [[ -z "$JWT_SECRET" || "$JWT_SECRET" == "null" ]]; then
  JWT_SECRET=$(openssl rand -hex 32)
  APP_JSON=$(echo "$APP_JSON" | jq --arg j "$JWT_SECRET" '.JWT_SECRET = $j | .USE_REACT_AGENT = "true"')
  aws secretsmanager put-secret-value --secret-id joblens/app --region "$REGION" --secret-string "$APP_JSON"
else
  APP_JSON=$(echo "$APP_JSON" | jq '.USE_REACT_AGENT = "true"')
  aws secretsmanager put-secret-value --secret-id joblens/app --region "$REGION" --secret-string "$APP_JSON"
fi

cat > .env <<EOF
DATABASE_URL=postgresql://${RDS_USER}:${RDS_PASS}@${RDS_HOST}:5432/${RDS_DB}
LLM_API_KEY=$(echo "$APP_JSON" | jq -r .LLM_API_KEY)
LLM_BASE_URL=$(echo "$APP_JSON" | jq -r .LLM_BASE_URL)
LLM_MODEL=$(echo "$APP_JSON" | jq -r .LLM_MODEL)
USE_REACT_AGENT=true
JWT_SECRET=${JWT_SECRET}
LANGCHAIN_API_KEY=$(echo "$APP_JSON" | jq -r '.LANGCHAIN_API_KEY // .LANGSMITH_API_KEY // empty')
LANGSMITH_PROJECT=$(echo "$APP_JSON" | jq -r .LANGSMITH_PROJECT)
BACKEND_BIND=0.0.0.0:8000
EOF

docker-compose -f docker-compose.prod.yml up -d --build

sleep 12
curl -sf http://127.0.0.1:8000/health | jq .
curl -sf http://127.0.0.1:8000/openapi.json | jq -r '.paths | keys[]' | sort
