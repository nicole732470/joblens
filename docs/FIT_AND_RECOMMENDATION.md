# Fit & Recommendation Design

> How the system decides "should I apply?" — the candidate model, resume-fit
> semantics, and the multi-factor recommendation. Written **before** building
> RAG / resume chunking so the retrieval work serves the right goal.
> Living document; fill the `TODO(profile)` blanks with real preferences.

Related: DESIGN.md §7–§9, and §8.1 (Sponsorship vs. Apply separation).

---

## 1. The problem with naive resume matching

The obvious pipeline — *chunk resume → embed → match against JD → score* —
is wrong for this use case, for three reasons:

1. **The resume is a moving target.** It will keep improving, and this very
  project (an evidence-based AI agent) becomes a new portfolio line item once
   shipped. A fit score against *today's* snapshot would unfairly reject jobs
   the candidate is about to qualify for.
2. **The targets are relatively fixed.** The candidate knows which kinds of
  roles they want (and which are fallbacks). Fit should be measured against a
   durable *intent*, not re-derived from whatever the resume currently says.
3. **Applying is a multi-factor decision, not just resume fit.** Location, role
  type, company, and (eventually) network all matter. Resume similarity is one
   input among several.

**Design consequence:** introduce a durable **Candidate Profile** that sits
beside the raw resume, treat resume gaps as *actionable and time-aware*, and
make the recommendation a **transparent multi-factor signal** rather than a
single similarity score. This stays consistent with the project's core
principle — **evidence over keyword matching.**

---

## 2. Candidate Profile (durable intent, separate from the resume)

A structured config representing *who the candidate is targeting and where they
are headed* — independent of the current resume text. The candidate describes
**intent only** (which role categories, where, dealbreakers); **skills are read
from the resume**, not re-listed here.

```
candidate_profile:
  tracks:                       # want — priority 1 (most) … 5 (last resort)
    - id: ai_ml_eng
      label: "AI / ML Engineer"
      priority: 1
      example_titles: [...]
  avoid_tracks:                 # do NOT want — negative examples
    - id: pure_sales
      label: "..."
      example_titles: [...]
  locations:
    summary: "..."              # optional — one vague sentence; rough wording OK
    tier_1: [...]               # optional — most want
    tier_2: [...]               # optional — acceptable
    tier_3: [...]               # optional — avoid / no-go
    remote_ok: true|false
    relocation_ok: true|false
  trajectory: [...]             # in-progress projects; rough one-liners OK
  dealbreakers: [...]           # OPTIONAL; hard veto
  preferences: [...]            # OPTIONAL; soft nudge
  constraints:
    needs_sponsorship: true
```

Fill this in at **`evals/golden_set/candidate_profile.yaml`** (skeleton already
created; blanks are the candidate's to decide).

**`example_titles` are anchors, not a whitelist.** Track matching is semantic
(LLM + embeddings), so a job titled "ML Engineer II" or "Applied Scientist"
still matches the `ai_ml_eng` track even if not typed verbatim. The resume text
remains the source of **evidence** for capabilities; the profile supplies
**intent and trajectory** so matching isn't a pure snapshot.

---

## 3. Resume as a moving target → time-aware gap classification

When a JD requirement is not currently satisfied by the resume, don't just call
it "missing." Classify *how closeable* the gap is:


| Class         | Meaning                                                                       | Recommended user action              |
| ------------- | ----------------------------------------------------------------------------- | ------------------------------------ |
| `surfaced`    | Resume already supports it (strong/partial)                                   | none — cite it                       |
| `editable`    | Capability likely exists but isn't shown well                                 | tweak resume wording/bullets         |
| `near_term`   | Not yet, but reachable via a planned `trajectory` item (e.g. this AI project) | apply soon / after the project lands |
| `fundamental` | Outside the candidate's field/trajectory                                      | genuine gap; weigh against track     |


This turns "you're missing X" into actionable guidance and prevents the system
from harshly rejecting jobs the candidate is on track to qualify for. Each
classification must still carry evidence IDs (JD requirement + resume/trajectory
reference) per the citation contract.

---

## 4. Multi-factor recommendation (transparent, per-track)

The apply decision is a **weighted combination of evidence-backed factors**, not
a black-box number. Each factor produces a sub-signal *plus* its evidence.


| Factor                     | Source                                   | Notes                                                 |
| -------------------------- | ---------------------------------------- | ----------------------------------------------------- |
| **Role-type fit**          | JD title/role vs. profile `tracks`       | which track(s) does this job serve?                   |
| **Resume/requirement fit** | resume evidence vs. JD requirements (§3) | uses gap classification                               |
| **Location fit**           | JD location vs. profile `locations`      | can be a hard veto (`no_go`)                          |
| **Company fit**            | company research/signals                 | quality of the company — **NOT** the H-1B DB (see §6) |
| **JD visa policy**         | JD parser `visa` / `visa_language`       | veto factor (see §6)                                  |
| **Network / alumni**       | *future, manual/opt-in only*             | see §7 — no auto-scraping                             |


Two important properties:

- **Per-track output.** A single job can be *"Apply"* for the `data_analyst`
fallback track but *"Low priority"* for the `ai_ml_eng` primary track. The
report should say which track(s) it's recommending for, not give one global
verdict divorced from intent.
- **Transparent weights.** Weights are explicit and tunable, and every factor's
contribution is explainable with evidence. No fake composite "match %" based
on keyword overlap.

`TODO(weights)`: default factor weights to be tuned against the golden set.
Start simple (equal-ish weights), validate, then adjust.

---

## 5. Hard vetoes vs. soft weights

Some signals should **cap** the recommendation regardless of how strong other
factors are; others only nudge a graded score.

- **Hard vetoes (cap to Skip / Low priority):**
  - JD explicitly states no sponsorship **and** `constraints.needs_sponsorship`.
  - Location in `locations.no_go` with no remote/relocation option.
- **Soft weights (graded):** role-type fit, resume fit, company fit, network.

---

## 6. Consistency with the Sponsorship/Apply separation (DESIGN §8.1)

This is easy to get wrong, so restating explicitly:

- The **H-1B / LCA database match is NOT a recommendation factor.** It is shown
to the user as a standalone informational signal only. "Company fit" in §4
means company *quality/research*, **not** whether the company is in our
sponsorship database.
- The **only sponsorship-related input to the recommendation is JD-stated visa
language** (e.g. "we do not sponsor"), via the JD parser — handled as a veto
in §5.
- Therefore a `claim_type="recommendation"` claim must never cite
`h1b_evidence_ids` (citation contract rule 4 in REPORT_SCHEMA.md).

---

## 7. Network / alumni signal (future, brainstorm — not MVP)

Idea: surface "do I have a way in?" (e.g. alumni or known contacts at the
company) as a positive factor.

**Hard constraint: no automated scraping or lookup of people/connections.**
That raises privacy and platform-ToS issues and is out of scope. If pursued
later, it must be **manual / opt-in** — e.g. the user tags "I know someone
here," or imports their own contacts deliberately. Recorded as a future
extension only; not part of the matching MVP.

---

## 8. Open questions (to resolve before/while building)

- [ ] Define real `tracks` (primary + fallbacks) with role keywords & must-haves.
- [ ] Define `locations` preferences and any `no_go`.
- [ ] List `trajectory` items (planned projects that count toward `near_term`).
- [ ] Decide default factor weights (§4) and validate on the golden set.
- [ ] Where does the profile live? (e.g. `evals/golden_set/candidate_profile.yaml`
  ```
  for eval, plus a per-request override from the extension later.)
  ```
- [ ] How is `trajectory` represented as citable evidence (so `near_term` gaps
  ```
  can cite it)?
  ```

---

## 9. How this changes the build order

Before RAG/chunking, lock the above. Then:

1. Add the **Candidate Profile** schema + a filled profile for eval.
2. Resume chunking + pgvector retrieval (DESIGN §7 `retrieve_resume_evidence`)
  — retrieval now serves **gap classification (§3)**, not a raw score.
3. `analyze_resume_fit` emits Claims with the gap classes from §3.
4. `generate_recommendation` implements the **multi-factor, per-track** logic
  (§4–§6) with transparent weights and citation rule 4.

