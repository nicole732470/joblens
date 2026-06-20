#!/usr/bin/env bash
# Copy shared report UI to extension + Lovable web. Run after editing shared/report-view.js or design/report-panel.css.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GLOW="${GLOW_DIR:-$ROOT/../vision-job-glow}"

mkdir -p "$ROOT/extension/lib"
cp "$ROOT/shared/report-view.js" "$ROOT/extension/lib/report-view.js"
cp "$ROOT/design/report-panel.css" "$ROOT/extension/report-panel.css"
echo "→ extension/lib/report-view.js"
echo "→ extension/report-panel.css"

if [[ -d "$GLOW/src" ]]; then
  mkdir -p "$GLOW/src/lib" "$GLOW/public"
  cp "$ROOT/shared/report-view.js" "$GLOW/src/lib/report-view.js"
  cp "$ROOT/design/report-panel.css" "$GLOW/public/joblens-report-panel.css"
  echo "→ vision-job-glow/src/lib/report-view.js"
  echo "→ vision-job-glow/public/joblens-report-panel.css"
else
  echo "skip vision-job-glow (set GLOW_DIR or clone repo next to joblens)"
fi
