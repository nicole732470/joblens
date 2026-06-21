# Coding-agent handoff

Read this first, then follow links instead of reconstructing architecture from
old commits.

## System

- Main repo: `nicole732470/joblens`
- Web repo: `nicole732470/vision-job-glow` (sibling directory)
- Web: https://job-lens-main.lovable.app
- API: https://3-128-164-130.sslip.io
- EC2: `i-0bdee6f611283586f`, `/opt/joblens`

## Non-negotiable product rules

1. Dimensions are independent; one signal must not silently mutate another.
2. H-1B history is informational and separate from Company fit and verdict.
3. Role AI reads full JD. Fallback also uses title + responsibilities + requirements.
4. Unmatched P4 is not an automatic Skip; explicit avoid tracks may veto.
5. Company fit uses external/structured evidence, never JD marketing copy.
6. Logged-in Profile/Resume data is DB-authoritative; YAML is guest/eval data.
7. Web and extension share the API and report renderer; do not force identical LLM prose.
8. Preserve unrelated dirty worktree changes and stage files intentionally.

Authoritative scoring: [SCORING_STANDARD.md](SCORING_STANDARD.md).

## Key paths

| Area | Path |
|---|---|
| API/routes | `backend/app/main.py` |
| Workflow | `backend/app/graph/` |
| Independent decisions | `backend/app/tools/independent_decisions.py` |
| Final verdict | `backend/app/tools/recommendation*.py` |
| Candidate profile | `backend/app/schemas/candidate_profile.py` |
| Report schema | `backend/app/schemas/report.py` |
| Extension capture | `extension/content.js` |
| Shared renderer/client | `shared/` and `design/` |
| Web app | `../vision-job-glow/src/routes/index.tsx` |
| Golden set | `evals/golden_set/` |

## Verify

```bash
PYTHONPATH=backend pytest -q backend/tests
cd ../vision-job-glow && npm run build
```

## Debug

Use the test-account Web Debug view. Inspect actual inputs → raw structured
output → validated output → fallback → final override. Compare separate runs by
their input/profile/prompt fingerprints, not by run ID.

## Deploy

```bash
cd /opt/joblens && git pull && bash deploy/ec2-redeploy.sh
```

Web changes require Lovable Publish after pushing. Shared report changes require
running both sync scripts and committing both repos.
