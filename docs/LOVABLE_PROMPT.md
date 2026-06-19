# Lovable prompt archive

**Active web UI:** [vision-job-glow](https://github.com/nicole732470/vision-job-glow) — edit in Lovable, not via prompts to recreate from scratch.

Use prompts only for **incremental** changes inside your existing Lovable project, e.g.:

```
Keep current JobLens design. Add [feature]. Do not change VITE_API_URL or auth API paths.
API: http://3.128.164.130:8000 — /auth/register, /auth/login, /me/profile, /jobs/parse-url, /resume/upload, /analyze
```

For extension UI parity after a big Lovable redesign:

```
Our Chrome extension should match the vision-job-glow JobLens panel: same verdict pill colors, card borders (#ece9e1), charcoal primary buttons (#37352f), 14px radius cards.
```
