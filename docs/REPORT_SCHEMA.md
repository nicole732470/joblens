# Report Schema & Citation Contract

The shape of an `/analyze` result. **Source of truth: `backend/app/schemas/report.py`**
(enforced at runtime by FastAPI). This file is the human-readable companion —
keep both in sync.

Guiding principle: **evidence over keyword matching.** Every interpretive claim
must cite evidence that actually exists in the retrieved context.

---

## Top-level: `Report`

| Field | Type | Meaning |
|-------|------|---------|
| `status` | `"partial"` \| `"complete"` | `partial` until all sections are built |
| `pending` | `string[]` | Sections not yet implemented (e.g. `resume_fit`) |
| `sponsorship` | `SponsorshipAnalysis` | H-1B sponsorship analysis (built) |
| `resume_fit` | `ResumeFitAnalysis` | Resume ↔ JD matching (pending) |
| `risk` | `RiskAnalysis` | Deterministic risk signals (pending) |
| `recommendation` | `RecommendationResult` | Final call + reasoning (pending) |
| `received` | `object` | Echo of the inputs the server parsed |

---

## `SponsorshipAnalysis`

Filled by `search_h1b_company` (the faithful `matcher.js` port).

| Field | Type | Meaning |
|-------|------|---------|
| `matched` | `bool` | Whether an employer entity was resolved |
| `query` | `string?` | The company name that was searched |
| `reason` | `string?` | Why no match (only when `matched=false`) |
| `match_confidence` | `"high"\|"medium"\|"low"` \| null | **Entity-resolution** confidence — how sure we are this is the right legal employer. **NOT** sponsorship probability. |
| `method` | `string?` | `core_exact` / `core_subset` / `key_overlap` / `token_overlap` |
| `matched_on` | `string?` | Which tokens/keys drove the match |
| `company` | `CompanyRef?` | FEIN, legal name, NAICS sector, city/state |
| `total_lca_count` | `int` | Total H-1B LCA filings on record |
| `h1b_count` / `certified_count` | `int` | Volume signals |
| `recent_lca_count` | `int?` | Year-by-year recency — `null` until raw LCA records are imported |
| `sponsorship_likelihood` | `High\|Medium\|Low\|Unknown` | Separate transparent heuristic (`calculate_sponsorship_likelihood`). `Unknown` until built. |
| `sponsored_titles` | `{title, count}[]` | Most-filed roles |
| `aliases` | `string[]` | Alternate legal names under this FEIN |
| `warnings` / `notes` | `string[]` | Caveats carried over from the resolver |
| `ambiguous_alternatives` | `object[]` | Other plausible employers (name, fein, lca_count, confidence) |
| `evidence` | `Evidence[]` | Citable facts (see below) |
| `evidence_ids` | `string[]` | IDs of the above, for citation |

> **Two different "confidences":** `match_confidence` is about *which company*
> this is. `sponsorship_likelihood` is about *whether this role is likely to be
> sponsored*. They are intentionally separate.

---

## `Evidence`

An atomic, citable fact.

| Field | Type | Example |
|-------|------|---------|
| `id` | `string` | `h1b:91-1144442:lca_count` |
| `type` | `string` | `sponsorship_volume`, `entity_match`, `sponsored_title` |
| `value` | `any` | `12132` |
| `detail` | `string` | `"12132 H-1B LCA filings on record"` |

Evidence IDs are stable, prefixed handles (`h1b:…`, later `jd:…`, `resume:…`)
so any claim can point back to exactly what supports it.

---

## `Claim` (used by resume_fit / risk / recommendation)

Every interpretive statement is a `Claim`:

```json
{
  "claim": "The role is a partial match for RAG experience.",
  "claim_type": "resume_fit",
  "jd_evidence_ids": ["jd_req_03"],
  "resume_evidence_ids": ["resume_proj_02"],
  "h1b_evidence_ids": [],
  "reasoning": "The JD asks for RAG pipelines; the resume shows LLM retrieval but not a full vector-DB RAG system.",
  "inference": false
}
```

---

## Citation Contract

Enforced by `validate_claims()` in `backend/app/tools/citations.py`:

1. **A non-inference claim must cite at least one evidence ID.**
2. **Every cited evidence ID must exist** in the retrieved context for that
   analysis. (No inventing citations.)
3. Claims not grounded in evidence are allowed **only** if explicitly marked
   `inference: true`.

Violations are returned as a list of issues (`no_evidence`,
`unknown_evidence_id`). Once the LLM generation stage exists (Week 3), violating
claims are rejected and regenerated rather than shown. This is a code-level
guarantee, not just a prompt instruction.

---

## Status

| Section | State |
|---------|-------|
| `sponsorship` | Implemented (real data, evidence IDs) |
| `sponsorship_likelihood` | Pending (`calculate_sponsorship_likelihood`) |
| `resume_fit` | Pending (RAG + claims) |
| `risk` | Pending (rule engine) |
| `recommendation` | Pending |
