# Multi-surface sync (extension + web + Lovable)

**Source of truth:** this GitHub repo (`nicole732470/joblens`).

| Surface | Path | Connects to |
|---------|------|-------------|
| Chrome extension | `extension/` | EC2 `POST /analyze` |
| Web app | `web/` | Same API + auth endpoints |
| Lovable | Optional UI host | Same API — does **not** auto-sync code unless GitHub linked |

Lovable edits stay on Lovable unless you enable GitHub sync. **We develop in this repo**; push → reload extension / redeploy web / Lovable re-import.

## Design

Shared tokens: `design/tokens.css` (Notion-inspired).

## API (EC2)

```
VITE_API_URL=http://3.128.164.130:8000
```

Endpoints: `/auth/register`, `/auth/login`, `/me/profile`, `/jobs/parse-url`, `/resume/upload`, `/analyze`
