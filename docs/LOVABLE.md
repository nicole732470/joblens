# JobLens Web (Lovable / static)

## API endpoint (no custom domain)

AWS EC2 **does** provide a hostname:

```
http://ec2-3-128-164-130.us-east-2.compute.amazonaws.com:8000
```

Same machine as elastic IP `3.128.164.130`. We use HTTP (no paid domain / HTTPS cert yet).

CORS is open (`*`) — any web origin can call `POST /analyze`.

## Option A — Repo static page (`web/`)

```bash
cd web && python3 -m http.server 5173
# Open http://localhost:5173
```

Deploy `web/` to any static host (S3, Netlify, Lovable publish, etc.).

## Option B — Lovable project

1. [lovable.dev](https://lovable.dev) → New project
2. Brand: **JobLens**, tagline: *See a company before you apply*
3. UI: company, title, JD textarea, optional resume, Analyze button
4. Fetch:

```javascript
const API = "http://3.128.164.130:8000";

async function analyze({ jd_text, company, title, resume_text }) {
  const res = await fetch(`${API}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jd_text, company, title, resume_text }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
```

5. Show `recommendation.verdict`, `resume_fit`, `sponsorship` summary
6. Publish on Lovable default URL (or later point a custom domain)

## One-time resume index (production)

Embeddings are stored in RDS; analyze reuses them after the first index:

```bash
curl -X POST http://3.128.164.130:8000/resume/index \
  -H "Content-Type: application/json" \
  -d "$(jq -n --rawfile t evals/golden_set/resume.md '{resume_text: $t, resume_key: "default"}')"
```

## H-1B lookup

Web `/analyze` uses RDS `companies` table. Full offline index remains in the Chrome extension.
