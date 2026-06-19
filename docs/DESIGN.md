# Project Design: Evidence-Based Visa-Aware Job Intelligence Agent

> Design + implementation plan for evolving the H-1B Sponsorship Checker into an
> AI job intelligence agent. Living document — update as decisions change.

## 1. Project Background

This project is an extension of my existing H-1B Sponsorship Checker Chrome
Extension.

The original project already supports:

- Processing large-scale DOL LCA/H-1B sponsorship records
- Company name normalization
- Company entity matching
- LinkedIn company lookup
- Historical sponsorship checking

Instead of treating the original extension as a standalone product, this project
will evolve it into a broader AI-powered job decision system.

The new goal is not only to answer **"Has this company sponsored before?"** but
also: **Is this job worth applying to, based on sponsorship history, job
requirements, resume fit, and evidence-backed reasoning?**

## 2. Product Goal

Build an AI job intelligence agent for international students that evaluates a
job opportunity and produces an evidence-based application recommendation.

The system should help users answer:

1. Has this company historically sponsored H-1B?
2. Is sponsorship likely for this type of role?
3. How well does my resume match this job?
4. Which requirements are strong matches, partial matches, or gaps?
5. Are there obvious risk signals?
6. Should I apply, modify my resume first, deprioritize, or skip?

**Main product principle: evidence over keyword matching.** The system should
avoid fake match scores based only on keyword overlap. Every major conclusion
should be backed by specific evidence from the job description, resume, H-1B
records, or company signals.

## 3. Core MVP Scope

### Input

For MVP, the user can provide:

- Pasted job description text
- Company name
- Job title
- Resume text or uploaded resume
- Optional job URL

The Chrome Extension can later extract the job description automatically from
LinkedIn or Greenhouse.

### Output

The system generates a structured report.

**Sponsorship Analysis**

- Matched company entity
- Historical H-1B/LCA count
- Recent sponsorship activity
- Similar sponsored job titles
- Sponsorship likelihood: High / Medium / Low / Unknown
- Evidence from structured H-1B records

**Resume Fit Analysis**

- Job requirements extracted from the JD
- Strong matches
- Partial matches
- Missing qualifications
- Resume evidence for each match
- JD evidence for each requirement

**Risk Analysis**

- Low sponsorship evidence
- No similar sponsored roles
- Very broad or vague JD
- Missing compensation
- Heavy relocation / onsite requirement
- Company research unavailable or weak

**Recommendation** — one of:

- Apply
- Apply with resume modifications
- Low priority
- Skip

The recommendation must explain why and cite evidence.

## 4. Technical Goals

This project is designed to demonstrate practical AI Engineer skills:

- RAG
- Vector search
- LangGraph
- Tool calling
- Structured LLM output
- Citation enforcement
- Evaluation
- PostgreSQL / pgvector
- FastAPI backend
- Chrome Extension integration
- Lightweight AWS deployment
- Observability and logging

MCP, Kubernetes, SQS, and full multi-platform scraping are considered future
extensions, **not** MVP requirements.

## 5. System Architecture

MVP architecture:

```
Chrome Extension / Web UI
        ↓
FastAPI Backend
        ↓
LangGraph Workflow
        ↓
Tools:
  - H1B SQL Lookup
  - Resume Evidence Retriever
  - JD Parser
  - Risk Rule Engine
        ↓
PostgreSQL + pgvector
        ↓
Report Generator
```

Deployment target:

- AWS EC2
- Docker Compose
- FastAPI
- PostgreSQL + pgvector
- Optional S3 for uploaded resumes and generated reports

Avoid for MVP:

- ECS Fargate
- Kubernetes
- SQS
- Complex multi-service deployment
- Full MCP server layer
- Large-scale web scraping system

## 6. Data Layer

### PostgreSQL

Stores structured data:

- Companies
- Company aliases
- H-1B/LCA sponsorship records
- Job analyses
- User resumes
- Report metadata
- Evaluation samples

### pgvector

Stores embeddings for semantic retrieval:

- Resume experience chunks
- Project chunks
- Skill evidence chunks
- Job requirement chunks

The H-1B data should remain **SQL-based, not vector-based**, because sponsorship
records are structured data.

### Optional S3

Stores:

- Uploaded resume files
- Raw JD text
- Generated reports
- Evaluation artifacts

## 7. Tool Functions

Initial tools should be simple typed Python functions, **not MCP servers**.

### `search_h1b_company(company_name)`

Find matched company entities and sponsorship history. Returns:

- matched company
- alias confidence
- total LCA count
- recent LCA count
- sponsored titles
- sponsored locations
- evidence IDs

### `calculate_sponsorship_likelihood(company, job_title)`

Transparent heuristic model based on:

- recent sponsorship count
- total sponsorship count
- similarity between current job title and historically sponsored titles
- trend over recent years
- location relevance if available

Returns: High / Medium / Low / Unknown, explanation, evidence IDs.

### `parse_job_description(jd_text)`

Uses structured LLM output to extract: company, job title, location, required
skills, preferred skills, experience level, responsibilities, visa-related
language, risk keywords.

### `retrieve_resume_evidence(requirement)`

Uses pgvector to retrieve resume/project chunks relevant to a JD requirement.
Returns: evidence chunk ID, source section, matched text, similarity score.

### `analyze_resume_fit(requirements, resume_evidence)`

Classifies each requirement as Strong match / Partial match / Weak-missing. Each
classification must include: JD evidence ID, resume evidence ID (if applicable),
explanation. **Gaps are time-aware** (editable / near-term / fundamental) rather
than a static fail — see FIT_AND_RECOMMENDATION.md §3.

### `run_risk_rules(parsed_jd, sponsorship_result, company_signals)`

Deterministic rule-based risk checks. Examples: no sponsorship history, no
similar sponsored roles, broad JD with unclear responsibilities, unpaid or
missing compensation, suspiciously vague company description, relocation
requirement.

### `generate_recommendation(all_results)`

Generates final recommendation using structured inputs. Must cite evidence IDs.
**Excludes H-1B database signals** (see §8.1): it consumes JD requirements
(incl. JD-stated visa language), resume fit, and risk rules — but never the
H-1B/LCA match as a reason to apply or not.

## 8. Citation Enforcement

Every important claim must include evidence IDs. Example output format:

```json
{
  "claim": "The role is a partial match for RAG experience.",
  "claim_type": "resume_fit",
  "evidence": {
    "jd_evidence_ids": ["jd_req_03"],
    "resume_evidence_ids": ["resume_proj_02"]
  },
  "reasoning": "The JD asks for RAG pipelines. The resume includes LLM retrieval logic, but does not yet show a full vector database-based RAG system."
}
```

Validation rules:

- Reject claims with missing evidence IDs.
- Reject evidence IDs not present in retrieved context.
- Flag claims where the explanation introduces facts not found in evidence.
- Allow unsupported claims only if explicitly marked as inference or unknown.

This is a core engineering feature, not just prompt wording.

### 8.1 Separation of Concerns: Sponsorship Signal vs. Apply Recommendation

The **"should I apply?"** decision and the **"does this company sponsor?"**
signal are deliberately kept independent. They are two different questions and
must not contaminate each other.

- **H-1B / LCA database matching does NOT feed the recommendation.** Whether a
  company appears in our historical sponsorship data is shown to the user as a
  **standalone informational signal only**. It is never an input to
  `generate_recommendation`. Rationale: the entity match can be wrong, and
  sponsorship behavior is volatile (sponsoring last year does not guarantee this
  year, and vice versa). We refuse to let a noisy/historical signal raise or
  lower an apply decision.
- **JD-stated visa language DOES feed the recommendation.** If the job
  description itself explicitly states a policy (e.g. "we do not provide
  sponsorship"), that is a current, authoritative fact about *this* role and
  must lower — potentially veto — the recommendation. This comes from the JD
  parser (`category="visa"` requirement / `visa_language`), not from the H-1B
  database.

Concretely, this becomes a citation-contract rule (see REPORT_SCHEMA.md): a
`claim_type="recommendation"` Claim may cite `jd_evidence_ids` and
`resume_evidence_ids`, but **must never cite `h1b_evidence_ids`.** The
`SponsorshipAnalysis` section stays a peer field on the `Report`, surfaced to the
user but excluded from the recommendation's evidence.

> The full apply-decision model — candidate profile, time-aware resume gaps, and
> the multi-factor per-track recommendation — lives in
> **FIT_AND_RECOMMENDATION.md**.

## 9. LangGraph Workflow

Initial graph should stay small:

```
Input
 ↓
Job Parser
 ↓
Company Resolver + H1B Lookup
 ↓
Resume Evidence Retrieval
 ↓
Resume Fit Analysis
 ↓
Risk Rules
 ↓
Recommendation + Report
```

Each node should have: typed input, typed output, error handling, fallback
behavior.

Example fallback: if company research fails, the system still produces a report
but marks company due diligence as unavailable.

## 10. Evaluation Plan

Evaluation is part of MVP.

Create a golden set of 30–50 real job descriptions. Each sample should include
manual labels:

- expected sponsorship likelihood
- expected recommendation
- key strong matches
- key missing qualifications
- whether recommendation is acceptable
- whether citations are valid

Evaluation metrics:

**Sponsorship**

- company match accuracy
- likelihood classification accuracy
- similar-title retrieval quality

**Resume Fit**

- requirement extraction quality
- evidence retrieval relevance
- strong / partial / missing classification accuracy

**Citation**

- percentage of claims with valid evidence
- unsupported claim rate
- hallucinated fact rate

**Recommendation**

- agreement with manual label
- explanation quality
- conservative vs over-optimistic bias

Start with a simple Python evaluation script. Add LangSmith / DeepEval later
only if useful.

## 11. Implementation Plan

### Week 1: Backend + Data Foundation

- Set up FastAPI
- Set up PostgreSQL + pgvector with Docker Compose
- Import existing H-1B sponsorship data
- Wrap existing company matching logic into typed Python functions
- Create basic `/analyze` endpoint

### Week 2: Golden Dataset + Evaluation Harness

- Collect 30–50 real job descriptions
- Manually label expected outcomes
- Build simple evaluation script
- Define report JSON schema
- Define citation contract

### Week 3: First End-to-End MVP Without LangGraph

- Input pasted JD + resume
- Parse JD with structured output
- Run H-1B lookup
- Run basic resume matching
- Generate structured report
- Validate citations
- Run against golden set

### Week 4: RAG / pgvector Resume Matching

- Chunk resume and project experience
- Generate embeddings
- Store in pgvector
- Retrieve relevant resume evidence per JD requirement
- Improve strong / partial / missing classification
- Evaluate retrieval quality

### Week 5: LangGraph Refactor

- Convert pipeline into LangGraph nodes
- Add state management
- Add tool calling
- Add failure handling
- Add progress logging

### Week 6: Risk Rules + Limited Company Signals

- Add deterministic risk rules
- Add limited company due diligence only if stable
- Avoid broad crawling
- Add caching for company signals

### Week 7: Chrome Extension Integration + Deployment

- Add "Analyze This Job" button to existing extension
- Send extracted JD/company/title to backend
- Deploy on EC2 with Docker Compose
- Optional S3 storage for reports and resumes

### Week 8: Polish + Portfolio Package

- Improve evaluation results
- Add README
- Add architecture diagram
- Add demo video
- Add ADR explaining design tradeoffs
- Add examples of successful and failed analyses

## 12. Future Extensions

Future, not MVP:

- MCP wrapper around mature tool functions
- Handshake / Indeed / Workday support
- Greenhouse parser
- SQS or background workers
- ECS / Fargate
- Kubernetes
- More advanced company due diligence
- Multi-user authentication
- User history and personalization
- RAGAS / DeepEval / LangSmith evaluation pipeline
- Multimodal resume or screenshot parsing

## 13. Success Criteria

A successful MVP should allow a user to paste a job description and resume, then
receive a reliable report answering:

1. Does this company sponsor?
2. Is sponsorship likely for this role?
3. What requirements does the job have?
4. Which parts of my resume support each requirement?
5. What are my gaps?
6. What risks should I consider?
7. Should I apply?

The system should be judged by: evidence quality, citation validity,
recommendation usefulness, evaluation results, and reliability of the
end-to-end workflow.

The goal is **not** to build the biggest possible AI system. The goal is to
build a credible, evaluated, evidence-based AI agent that solves a real
job-search decision problem.
