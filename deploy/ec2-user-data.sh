#!/bin/bash
# EC2 first-boot: install Docker, clone JobLens, pull secrets, start backend.
# Requires IAM instance profile joblens-ec2 (SSM + Secrets Manager read).
set -euo pipefail
REGION="${AWS_REGION:-us-east-2}"
REPO="https://github.com/nicole732470/joblens.git"
APP_DIR="/opt/joblens"

dnf update -y
dnf install -y docker git jq postgresql15
systemctl enable --now docker

RDS_JSON=$(aws secretsmanager get-secret-value --secret-id joblens/rds --region "$REGION" --query SecretString --output text)
APP_JSON=$(aws secretsmanager get-secret-value --secret-id joblens/app --region "$REGION" --query SecretString --output text)

until RDS_HOST=$(aws rds describe-db-instances --db-instance-identifier joblens-db --region "$REGION" \
  --query 'DBInstances[0].Endpoint.Address' --output text 2>/dev/null) && [[ "$RDS_HOST" != "None" && -n "$RDS_HOST" ]]; do
  echo "Waiting for RDS endpoint..."
  sleep 30
done

RDS_USER=$(echo "$RDS_JSON" | jq -r .username)
RDS_PASS=$(echo "$RDS_JSON" | jq -r .password)
RDS_DB=$(echo "$RDS_JSON" | jq -r .database)

export PGPASSWORD="$RDS_PASS"
psql -h "$RDS_HOST" -U "$RDS_USER" -d "$RDS_DB" -c "SELECT 1" >/dev/null

rm -rf "$APP_DIR"
git clone "$REPO" "$APP_DIR"
cd "$APP_DIR"
psql -h "$RDS_HOST" -U "$RDS_USER" -d "$RDS_DB" -f deploy/rds-init.sql

cat > .env <<EOF
DATABASE_URL=postgresql://${RDS_USER}:${RDS_PASS}@${RDS_HOST}:5432/${RDS_DB}
LLM_API_KEY=$(echo "$APP_JSON" | jq -r .LLM_API_KEY)
LLM_BASE_URL=$(echo "$APP_JSON" | jq -r .LLM_BASE_URL)
LLM_MODEL=$(echo "$APP_JSON" | jq -r .LLM_MODEL)
USE_REACT_AGENT=$(echo "$APP_JSON" | jq -r .USE_REACT_AGENT)
LANGSMITH_PROJECT=$(echo "$APP_JSON" | jq -r .LANGSMITH_PROJECT)
BACKEND_BIND=127.0.0.1:8000
EOF

docker compose -f docker-compose.prod.yml up -d --build
sleep 20
curl -sf http://127.0.0.1:8000/health
