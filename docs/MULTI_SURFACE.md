# Multi-surface workflow

JobLens has one API and two clients. “Parity” means equivalent normalized
inputs produce stable dimension results—not that independent LLM prose must be
identical.

## Ownership

| Concern | Source of truth |
|---|---|
| Analyze/scoring | `joblens/backend` |
| Report HTML | `joblens/shared/report-view.js` |
| Report CSS/tokens | `joblens/design/` |
| LinkedIn capture/panel shell | `joblens/extension` |
| Web pages/Profile/Debug | `vision-job-glow` |

## Sync shared assets

```bash
./scripts/sync-shared-ui.sh
./scripts/sync-design-tokens.sh
```

Review and commit changes in both repositories. Sync scripts copy shared code;
they do not publish Lovable or reload Chrome.

## Cross-surface stability

When Web and extension differ, compare:

- company, title, location
- JD length and relevant evidence
- Profile version
- prompt/scoring versions
- per-dimension method and fallback

Do not compare `run_id`; every request gets a new one. Do not force cached final
verdicts across materially different JD inputs.

Recommended eval invariant for the same job:

- Role and Location tier should match
- Resume and Company should remain in the same band
- verdict should not cross Apply ↔ Skip without a material evidence difference
- summary wording may vary

## Authentication bridge

The web owns login and Profile editing. `sync-auth.js` transfers the JWT to the
extension; LinkedIn credentials are never used as JobLens credentials.

## Publish checklist

| Change | Steps |
|---|---|
| Backend | test → push `joblens` → EC2 redeploy → health check |
| Extension | test → push → reload in `chrome://extensions` |
| Shared UI | sync → build Web → push both repos → Lovable Publish → reload extension |
| Web-only | build → push `vision-job-glow` → Lovable Publish |

The Lovable Git repository can update before the published site does. Verify
the live asset after publishing instead of assuming a successful push is live.
