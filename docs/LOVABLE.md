# JobLens web — Lovable (`vision-job-glow`)

**Web UI source of truth:** [github.com/nicole732470/vision-job-glow](https://github.com/nicole732470/vision-job-glow)

Built and hosted on [Lovable](https://lovable.dev). Backend stays on EC2 in the main `joblens` repo.

---

## What's already synced

| Item | Status |
|------|--------|
| GitHub repo | `nicole732470/vision-job-glow` (Lovable two-way sync) |
| API URL | `VITE_API_URL=http://3.128.164.130:8000` in repo `.env` |
| Auth + profile + analyze | Wired in `src/routes/index.tsx` |
| Extension UI | `joblens/extension/` uses same design tokens |

---

## Your workflow

1. **Design in Lovable** — chat, preview, iterate.
2. **Code auto-pushes** to `vision-job-glow` on GitHub (no manual copy).
3. **Publish** in Lovable → live `*.lovable.app` URL.
4. **Extension / backend** — change only in `joblens` repo when needed.

You do **not** need to merge Lovable code into `joblens/web/`.

---

## Environment (Lovable)

**Settings → Environment:**

```
VITE_API_URL=http://3.128.164.130:8000
```

No trailing slash. CORS on EC2 allows HTTPS Lovable → HTTP API.

---

## After Publish

1. Note your `https://….lovable.app` URL.
2. Set `WEB_APP_URL` in `joblens/extension/content.js` for the footer link.
3. Share the URL in README if you want.

---

## Extension + web consistency

- Colors / cards / verdict pills: `joblens/design/tokens.css` ↔ `vision-job-glow` inline styles.
- If Lovable redesigns heavily, refresh extension `styles.css` to match.

---

## Legacy `joblens/web/`

The Vite app under `joblens/web/` is **not** deployed for production. Use Lovable instead.
