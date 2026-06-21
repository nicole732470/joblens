# Shared report UI

These files are the source for analyze-result rendering on both product surfaces:

- `report-view.js` — report HTML, metric tooltips, section layout
- `analyze-client.js` — async analyze + polling client
- `../design/report-panel.css` — report styles
- `../design/tokens.css` — shared visual tokens

After changing shared report code or styles:

```bash
./scripts/sync-shared-ui.sh
./scripts/sync-design-tokens.sh
```

Copies are written to:

| Surface | Destination |
|---|---|
| Extension | `extension/lib/`, `extension/report-panel.css`, `extension/tokens.css` |
| Lovable web | `vision-job-glow/src/lib/`, `src/styles/`, `public/` |

Do not implement report metric cards separately in React or `content.js`.
Web-only application UI, including Profile and Debug views, belongs in
`vision-job-glow` and is not synced from this folder.
