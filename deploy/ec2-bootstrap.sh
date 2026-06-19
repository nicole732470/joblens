#!/usr/bin/env bash
# One-time EC2 setup (Amazon Linux 2023 / Ubuntu). Run as ec2-user or ubuntu.
set -euo pipefail

if command -v dnf &>/dev/null; then
  sudo dnf update -y
  sudo dnf install -y docker git
  sudo systemctl enable --now docker
  sudo usermod -aG docker "$USER"
elif command -v apt-get &>/dev/null; then
  sudo apt-get update -y
  sudo apt-get install -y docker.io docker-compose-v2 git
  sudo systemctl enable --now docker
  sudo usermod -aG docker "$USER"
else
  echo "Unsupported OS — install Docker and Git manually." >&2
  exit 1
fi

echo "Log out and back in so docker group applies, then:"
echo "  git clone https://github.com/nicole732470/joblens.git && cd joblens"
echo "  cp .env.example .env   # edit DATABASE_URL, LLM_API_KEY"
echo "  docker compose -f docker-compose.prod.yml up -d --build"
echo "  curl http://127.0.0.1:8000/health"
