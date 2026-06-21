# Report schema

The runtime source of truth is
`backend/app/schemas/report.py`. This document explains the public contract; it
does not duplicate every optional field.

## Top level

```json
{
  "status": "complete",
  "pending": [],
  "sponsorship": {},
  "company": {},
  "jd": {},
  "resume_fit": {},
  "risk": {},
  "recommendation": {},
  "received": {},
  "explain": {}
}
```

| Section | Purpose |
|---|---|
| `sponsorship` | DOL/LCA employer identity and filing history |
| `company` | personalized Company fit from external/structured evidence |
| `jd` | parsed requirements, location, visa language, risks |
| `resume_fit` | per-requirement Strong/Partial/Weak/Gap evidence |
| `risk` | deterministic risk claims |
| `recommendation` | independent dimension outputs and final verdict |
| `received` | normalized request metadata and input sizes |
| `explain` | compact UI/debug explanations and timing |

`partial` means required artifacts are unavailable; `pending` names them.

## Evidence and claims

`Evidence` is an atomic source fact:

```json
{"id":"jd_req_03","type":"required_skill","value":"RAG","detail":"…"}
```

`Claim` is an interpretation with source handles:

```json
{
  "claim": "[partial] Build production RAG systems",
  "claim_type": "resume_fit",
  "jd_evidence_ids": ["jd_req_03"],
  "resume_evidence_ids": ["resume_chunk_07"],
  "h1b_evidence_ids": [],
  "reasoning": "Related retrieval work exists but production scale is unclear.",
  "inference": false
}
```

Rules:

- non-Gap Resume claims should cite retrieved Resume evidence
- H-1B evidence must not be used to justify Role, Resume, Location, Company, or verdict
- Company sources carry URLs/timestamps and are separate from JD evidence
- unsupported facts should be unavailable, not assigned a neutral score

## Sponsorship

Important fields:

- `matched`, `query`, `reason`
- `match_confidence`, `method`, `matched_on`
- `company` legal entity/FEIN/NAICS/location
- `total_lca_count`, `h1b_count`, `certified_count`
- `sponsored_titles`, `aliases`, `ambiguous_alternatives`
- `evidence`, `evidence_ids`

`match_confidence` means identity confidence, not the probability that this job
will sponsor. `sponsorship_likelihood` remains `Unknown` until a separate
transparent model is implemented.

## Resume fit

- `match_method`: `llm` or `vector`
- `strong_matches`
- `partial_matches`
- `missing` — contains both Weak claims (with Resume evidence) and pure Gaps
- `debug` — test-account-only structured records

The aggregate ratio is exposed on `recommendation.fit_ratio`.

## Company

- `available`, `reason`
- `company_score`, `company_tier`, `company_label`
- `score_breakdown.dimensions`, effective weight, method, confidence
- `sources`, `research_available`

Raw model output in `score_breakdown` is removed for non-debug responses.

## Recommendation

- `decision`, `summary`, `reasoning`
- `track_id`, `track_label`, `track_priority`, `track_similarity`
- `location_tier`, `location_label`
- `preference_hits`, `dealbreaker_hits`
- `fit_ratio`, `recommendation_method`
- `technical_penalty_hits`, `evidence_ids`
- `debug_decisions` — test-account-only decision records

Allowed decisions: `Apply`, `Near apply`, `Consider`, `Skip`.

## Debug records

For the configured debug account, every independent decision includes:

- model and prompt version
- method
- input preview
- evidence
- raw structured output
- validated output
- validation error/fallback reason
- final rule override

Other accounts receive empty Debug fields. Trace endpoints also require the
debug account.

## Compatibility

Clients should tolerate unknown fields and missing optional sections. The API
may add explanation/debug metadata without changing primary report fields.
