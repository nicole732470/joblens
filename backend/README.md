# Backend (Job Intelligence Platform)

FastAPI service that orchestrates the agentic job-analysis workflow. This is the
new product surface that grows on top of the existing offline H-1B/LCA work.

## Status

Skeleton only. Implemented incrementally per the phased plan:

1. Restructure into monorepo — **done**
2. Port entity resolution from `extension/lib/matcher.js` to Python tool functions
3. Postgres + pgvector via Docker Compose; load employer index
4. FastAPI skeleton (`/health`, `/analyze` returning stub data)

Later phases add: golden-set evaluation, single-LLM vertical slice, RAG
(resume + JD), LangGraph orchestration, company research, deployment.

## Planned layout

```
backend/
├── app/
│   ├── main.py              # FastAPI app + routes
│   ├── tools/               # typed tool functions (the future MCP tool layer)
│   │   ├── sponsorship.py   # search_h1b_company, resolve_company_alias (ported)
│   │   ├── resume.py        # retrieve_resume_evidence
│   │   └── ...
│   ├── agents/              # LangGraph nodes (added in a later phase)
│   ├── db/                  # Postgres + pgvector access
│   └── schemas/             # pydantic models (report, evidence-cited claims)
├── tests/
└── requirements.txt
```

## Design decisions

- **Entity resolution is ported to Python**, not called via a separate Node
  service. Keeps the backend single-stack (Python) alongside pgvector and the
  agent runtime. Source of truth for the algorithm: `extension/lib/matcher.js`
  and the normalization logic in `data-pipeline/export_employer_index.py` /
  `data-pipeline/generic_tokens.py`.
- **Tools are plain typed functions first.** MCP wrapping is deferred to a late
  phase so the protocol does not shape the core architecture.
- **Evidence-first.** Every report claim must carry evidence IDs, mirroring the
  existing matcher's evidence-over-score philosophy.
