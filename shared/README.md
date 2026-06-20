# Shared UI (extension + web)

Single source of truth for **report rendering** — same `/analyze` JSON must look the same everywhere.

| File | Purpose |
|------|---------|
| `shared/report-view.js` | HTML builders: metrics grid, verdict, H-1B block, `renderReportResults()` |
| `design/report-panel.css` | Shared styles (`.lca-*` classes) |
| `design/tokens.css` | Colors, fonts, radii |

## Sync to surfaces

```bash
./scripts/sync-design-tokens.sh   # tokens → extension + Lovable
./scripts/sync-shared-ui.sh       # report-view.js + report-panel.css → extension + Lovable
```

After editing `shared/` or `design/report-panel.css`, **always run both scripts** (or copy manually) before testing the extension.

## How each surface uses it

| Surface | JS | CSS |
|---------|----|-----|
| **Extension** | `extension/lib/report-view.js` (copy), loaded before `content.js` | `@import "report-panel.css"` in `styles.css` |
| **Web (joblens/web)** | `import from "../../shared/report-view.js"` | `@import "../design/report-panel.css"` |
| **Lovable (vision-job-glow)** | copy to `src/lib/report-view.js` | `/joblens-report-panel.css` in public |

Web React wrapper (`web/src/ReportPanel.jsx`) is ~15 lines: calls `renderReportResults()` + `wireMetricTips()`.

Extension keeps LinkedIn-only chrome (drag handle, JD scrape) in `content.js`; all analyze result HTML comes from `JobLensReportView`.
