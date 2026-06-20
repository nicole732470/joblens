# Multi-surface sync (extension + API + Lovable web)

## Architecture (scheme 1)

| Surface | Where it lives | Role |
|---------|----------------|------|
| **Backend API** | `joblens` repo → EC2 `http://3.128.164.130:8000` | Analyze, auth, profile, resume |
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

Shared palette: `design/tokens.css` (aligned with `vision-job-glow`).

Extension applies the same colors in `extension/styles.css`.

## API (EC2)

```
VITE_API_URL=http://3.128.164.130:8000
```

Endpoints: `/auth/register`, `/auth/login`, `/me/profile`, `/jobs/parse-url`, `/resume/upload`, `/analyze`

Set in Lovable: **Project → Settings → Environment** (already in `vision-job-glow/.env`).

## Redeploy EC2 (auth + parse-url + schema)

```bash
# On instance, or via SSM:
cd /opt/joblens && git pull && bash deploy/ec2-redeploy.sh
```

Applies `db/auth_schema.sql`, sets `USE_REACT_AGENT=true`, rebuilds Docker.

## After Lovable Publish

Live web: **https://vision-job-glow.lovable.app** (also set in extension footer).

## Deploy checklist

| Change | Action |
|--------|--------|
| Backend | EC2: `git pull` in `joblens` + `docker compose up -d --build` |
| Extension | `chrome://extensions` → Reload JobLens |
| Web | Lovable auto-syncs to `vision-job-glow`; **Publish** on Lovable for live URL |
