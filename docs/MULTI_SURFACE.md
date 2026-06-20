# Multi-surface sync (extension + API + Lovable web)

## Architecture (scheme 1)

| Surface | Where it lives | Role |
|---------|----------------|------|
| **Backend API** | `joblens` repo → EC2 `https://3-128-164-130.sslip.io` | Analyze, auth, profile, resume |
| **Chrome extension** | `joblens/extension/` | LinkedIn panel (UI matches Lovable tokens) |
| **Web app** | **[`vision-job-glow`](https://github.com/nicole732470/vision-job-glow)** (Lovable) | Primary web UI — design source of truth |

```
LinkedIn ──extension──► EC2 API ◄── Lovable web (vision-job-glow)
                              ▲
                         joblens repo
                    (backend + extension)
```

- **Do not** maintain two competing web UIs. Lovable owns the website; `joblens/web/` is legacy / reference only.
- Lovable syncs to its **own** GitHub repo automatically when connected.
- Extension + backend stay in **`nicole732470/joblens`**.

## Design tokens

**Source of truth:** `design/tokens.css`

After editing tokens, sync to extension + Lovable web:

```bash
./scripts/sync-design-tokens.sh
```

Copies to `extension/tokens.css` and `../vision-job-glow/public/joblens-tokens.css`.

Extension `@import "tokens.css"` in `styles.css`. Web loads tokens via `index.css`. Lovable loads `/joblens-tokens.css`.

## Shared report UI (analyze results)

**Problem we fixed:** extension and web used to duplicate render logic (`content.js` vs `ReportPanel.jsx`), so the same job could show different metrics or copy.

**Source of truth:**

| Asset | Path |
|-------|------|
| Report HTML builders | `shared/report-view.js` |
| Report styles | `design/report-panel.css` |

```bash
./scripts/sync-shared-ui.sh
```

Copies JS/CSS to `extension/lib/` and (if cloned) `vision-job-glow`. See `shared/README.md`.

**Rule:** Any change to verdict text, metric cells, H-1B block, or tooltips → edit `shared/report-view.js` only, then sync. Do not re-implement in React or extension.

Web `ReportPanel.jsx` is a thin wrapper (`renderReportResults` + `dangerouslySetInnerHTML`). Extension `content.js` calls the same `JobLensReportView` global for fit analysis.

## API (EC2)

```
# Production HTTPS (used by Lovable /api proxy — hardcoded default in vision-job-glow)
https://3-128-164-130.sslip.io

# HTTP debug (extension still uses this until updated)
http://3.128.164.130:8000
```

Endpoints: `/auth/register`, `/auth/login`, `/me/profile`, `/resume/upload`, `/analyze`, `/analyze/async`, `/jobs/parse-url`

No Lovable Environment panel — API URL is set in code (`vision-job-glow/src/routes/api/$.tsx`).

## Redeploy EC2 (auth + parse-url + schema)

```bash
# On instance, or via SSM:
cd /opt/joblens && git pull && bash deploy/ec2-redeploy.sh
```

Applies `db/auth_schema.sql` and rebuilds Docker.

## After Lovable Publish

Live web: **https://job-lens-main.lovable.app**

## Deploy checklist

| Change | Action |
|--------|--------|
| Backend | EC2: `git pull` in `joblens` + `docker compose up -d --build` |
| Extension | `chrome://extensions` → Reload JobLens |
| Web | Lovable auto-syncs to `vision-job-glow`; **Publish** on Lovable for live URL |
