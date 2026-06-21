#!/usr/bin/env bash
# Copy design tokens to extension + Lovable web.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/design/tokens.css"
GLOW="${GLOW_DIR:-$ROOT/../vision-job-glow}"

cp "$SRC" "$ROOT/extension/tokens.css"
echo "-> extension/tokens.css"

if [[ -d "$GLOW/public" ]]; then
  cp "$SRC" "$GLOW/public/joblens-tokens.css"
  echo "-> vision-job-glow/public/joblens-tokens.css"
else
  echo "skip vision-job-glow (set GLOW_DIR or clone repo next to joblens)"
fi
