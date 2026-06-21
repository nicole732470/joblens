# JobLens scoring standard

Status: product contract
Owner: JobLens
Last updated: 2026-06-20

This document is the source of truth for JobLens scoring. Code, prompts, UI
labels, golden-set expectations, and tooltips must follow this contract.

## 1. Principles

1. The four core dimensions are independent:
   - Role fit
   - Resume fit
   - Location fit
   - Company fit
2. Preferences and dealbreakers are independent profile signals. They do not
   silently change any of the four core dimension scores.
3. H-1B history is a separate evidence section. It does not change Role,
   Resume, Location, or Company scores.
4. AI classification is primary. A dimension-specific fallback runs only when
   the AI call fails or returns invalid output.
5. Every AI result must include evidence and a short reason. A score without
   evidence is unavailable, not guessed.
6. All user-facing tiers use the same scale:
   - P1: strongest target
   - P2: good target
   - P3: acceptable / lower-priority target
   - P4: extremely low / outside the user's stated target range
7. Users configure only P1, P2, and P3 targets. P4 is system-assigned for an
   unmatched role, location, or company.

## 2. Role fit

### Inputs

- Job title
- Role responsibilities and requirements from the JD
- `candidate_profile.tracks`
- `candidate_profile.avoid_tracks`

Each configured track has an id, label, priority (P1-P3), and example titles.

### Primary method: AI classification

The model receives all configured tracks plus the job title and role content.
It must return:

```json
{
  "track_id": "ai_eng or null",
  "tier": 1,
  "confidence": 0.0,
  "reason": "short explanation",
  "evidence": ["job-title or JD excerpts"]
}
```

Rules:

- Select exactly one configured track only when the role substantively belongs
  to it.
- The output tier normally equals that track's configured P1-P3 priority.
- A title keyword alone cannot override contradictory role responsibilities.
- Any avoid-track match is P4.
- If no configured track fits, return `track_id=null`, P4.
- `technical_penalties` may reduce a matched track by one tier, capped at P4,
  but must not reclassify it into a different track.

### Fallback: embeddings

- Compare title + role-content embedding with every track descriptor.
- Choose the closest configured track only above a calibrated minimum.
- Compare avoid tracks independently.
- Below the positive threshold, or when avoid wins, assign P4.
- Embedding fallback must be labeled `method=embedding` in the report.

## 3. Resume fit

### Inputs

- Structured JD requirements
- Resume chunks

### Primary method: AI requirement classification

For each requirement, RAG retrieves relevant resume evidence. AI assigns one
of four mutually exclusive levels:

| Level | Meaning | Weight |
|---|---|---:|
| Strong | Resume clearly demonstrates the requirement | 1.00 |
| Partial | Related evidence exists but is incomplete/indirect | 0.50 |
| Weak | Only weakly related evidence exists | 0.25 |
| Gap | No meaningful resume evidence | 0.00 |

The displayed Resume score is:

```text
100 × sum(requirement weight) / number of scored requirements
```

Every classification must cite the JD requirement and, except for Gap, at
least one resume chunk.

### Fallback: vector similarity

Cosine similarity is `1 - cosine_distance`.

- Strong: similarity >= 0.80 (distance <= 0.20)
- Partial: 0.60-0.79
- Weak: 0.40-0.59
- Gap: < 0.40 or no evidence

These thresholds must be calibrated with `expected_fit_band` in the golden set.

## 4. Location fit

### Inputs

- Structured job location
- Remote/hybrid/onsite policy
- User P1/P2/P3 location preferences

### Primary method: AI geographic classification

AI determines:

- Whether the role is fully remote, hybrid, or onsite
- City, state, region, and country relationships
- Whether an unlisted place belongs to a configured metro/state preference
- Whether a location is rural when the user's rule refers to rural areas

Rules:

- Explicitly 100%/fully remote + `remote_ok=true` -> P1.
- Hybrid or partially remote -> score the required physical location normally.
- Match a configured location tier -> that P1/P2/P3 tier.
- Outside every configured tier -> P4.
- Outside the permitted country or an explicit avoid/rural rule -> P4.
- Uncertain geography must return unavailable or use fallback; AI must not
  invent a city/state relationship.

### Fallback: deterministic geography, then embeddings

1. Use a maintained city/state/metro/country mapping.
2. Apply exact configured tier matches.
3. Use embeddings only for semantic descriptions such as “major Illinois
   metro” or “rural area”.
4. No match -> P4.

## 5. Company fit

Company fit must use company evidence. The JD may identify the employer, but JD
marketing language and job requirements are not company-background evidence.

### Required company evidence

Use, in priority order:

1. Official company website
2. Reliable structured company data
3. LinkedIn company metadata visible to the user
4. H-1B/DOL company identity and NAICS data
5. Reputable funding/company databases when configured

Company research should be cached with source URLs and timestamps. If no
reliable evidence is available, Company is unavailable rather than inferred
from the JD.

### User profile fields

All accounts can configure company preferences:

```yaml
company_preferences:
  industries: []
  stages: []
  sizes: []
  funding_signals: []
  network_signals: []
  avoid: []
```

The Web Profile editor must expose these fields.

### Four normalized sub-scores

Each sub-score is independently normalized to 0-1 before aggregation:

| Sub-score | Evidence | Normalization |
|---|---|---|
| Industry fit | Official description, NAICS, products | AI rubric 0-1 |
| Stage/funding fit | Funding, ownership, public/private stage | AI rubric 0-1 |
| Scale/traction fit | Employees, customers, followers, market evidence | log/range normalization to 0-1 |
| Network fit | Alumni and user-configured network signals | matched applicable signals / applicable signals |

```text
company_score = 0.25 × industry
              + 0.25 × stage_funding
              + 0.25 × scale_traction
              + 0.25 × network
```

The four 25% weights apply only when all four dimensions are applicable to the
current user's profile. A dimension is applicable only when that user has
configured a preference for it. Unconfigured dimensions are `not_applicable`,
not neutral and not zero; their weight is redistributed equally among the
applicable dimensions. For example, a user who configures only industry and
stage/funding is scored 50% + 50%. Company evidence is researched once, but
the fit scores are always calculated against the currently authenticated
user's own `company_preferences`.

Tier mapping:

- P1: score >= 0.75
- P2: score >= 0.50 and < 0.75
- P3: score >= 0.25 and < 0.50
- P4: score < 0.25

Missing sub-scores are not treated as zero. Average only applicable sub-scores
supported by evidence. If an applicable dimension lacks evidence, omit it and
lower confidence; if none is supported, Company is unavailable. A result based
on only one supported dimension must be labeled low confidence.

### Fallback

- Use cached company evidence and embeddings against the configured company
  preferences.
- Do not fall back to scanning the JD for company quality.
- No reliable company evidence -> unavailable.

## 6. Preferences and dealbreakers

Preferences and dealbreakers are lists of matched concepts, not core numeric
scores.

### Primary method: AI classification

For every configured item, AI returns:

```json
{
  "item": "unpaid internship",
  "matched": true,
  "confidence": 0.96,
  "reason": "short explanation",
  "evidence": ["source excerpt"]
}
```

- Evaluate each item independently.
- Use only the relevant source: job conditions for job dealbreakers, company
  evidence for company preferences, location evidence for location rules.
- Example: `unpaid internship` may affect the dealbreaker list and final
  verdict, but never Company score.
- A preference hit is displayed as a hit; it is not added to another dimension.

### Fallback: embeddings

- Compare each configured item to the relevant evidence only.
- Require a calibrated similarity threshold and preserve the evidence excerpt.
- Below threshold -> not matched.
- Never use “any one token matches” as a positive result.

## 7. Final recommendation

The final verdict remains AI-generated from the independent dimensions and
their evidence. The model may explain tradeoffs but may not rewrite dimension
scores.

### Deterministic guardrails

Apply guardrails in this order:

1. An explicit applicable hard dealbreaker, including explicit no-sponsorship
   language when sponsorship is required, may force Skip.
2. Otherwise, Role P1/P2 and Resume score > 50% forces Apply.
3. Role P4 cannot produce Apply.
4. Company unavailable is neutral, not a penalty.
5. H-1B historical records do not change the verdict unless the JD itself
   explicitly states a visa restriction.

The AI then decides among Apply, Near apply, Consider, and Skip for cases not
fully determined by these guardrails.

## 8. Golden-set labels

Each label is optional. Blank or `unknown` is skipped.

- `expected_track_id`: expected configured track
- `expected_priority`: expected Role P1-P4 after penalties
- `expected_fit_band`: rough Resume band (`high`, `medium`, `low`)
- `expected_location_tier`: expected Location P1-P4
- `expected_company_tier`: expected Company P1-P4 or unavailable
- `expected_decision`: final verdict
- `expected_sponsors`: independent H-1B entity lookup result

Track and priority are intentionally separate: track labels the role family;
priority validates the final tier after an allowed penalty.

## 9. Prohibited coupling

- Unpaid/paid status must not alter Company.
- H-1B history must not alter Company, Role, Resume, or Location.
- Resume fit must not change which track the role belongs to.
- Company quality must not change Role fit.
- Preference counts must not be silently added to Company or Resume.
- The final LLM must not override any upstream dimension score.
