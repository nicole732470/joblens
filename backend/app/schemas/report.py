"""Report schema — the authoritative shape of an /analyze result.

This is the source of truth (enforced at runtime by FastAPI). The human-readable
description lives in docs/REPORT_SCHEMA.md and must be kept in sync.

Design principle: evidence over keyword matching. Every interpretive claim
(resume fit, risk, recommendation) carries evidence IDs; see Claim + the
citation contract in app/tools/citations.py.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel


class Evidence(BaseModel):
    """An atomic, citable fact pulled from a source (H-1B record, JD, resume)."""

    id: str
    type: str
    value: Any = None
    detail: str = ""


class Claim(BaseModel):
    """An interpretive statement that MUST be backed by evidence IDs.

    `inference=True` marks a claim not directly supported by evidence (allowed
    only when explicitly flagged, per the citation contract).
    """

    claim: str
    claim_type: Literal["sponsorship", "resume_fit", "risk", "recommendation"]
    jd_evidence_ids: list[str] = []
    resume_evidence_ids: list[str] = []
    h1b_evidence_ids: list[str] = []
    reasoning: str = ""
    inference: bool = False


class SponsorshipLikelihood(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    UNKNOWN = "Unknown"


class Recommendation(str, Enum):
    APPLY = "Apply"
    NEAR_APPLY = "Near apply"
    CONSIDER = "Consider"
    SKIP = "Skip"


class CompanyRef(BaseModel):
    fein: Optional[str] = None
    name: Optional[str] = None
    naics_code: Optional[str] = None
    naics_sector: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None


class SponsorshipAnalysis(BaseModel):
    matched: bool
    query: Optional[str] = None
    reason: Optional[str] = None
    # Entity-resolution confidence (matcher.js semantics), NOT sponsorship odds.
    match_confidence: Optional[str] = None
    method: Optional[str] = None
    matched_on: Optional[str] = None
    company: Optional[CompanyRef] = None
    total_lca_count: int = 0
    h1b_count: int = 0
    certified_count: int = 0
    recent_lca_count: Optional[int] = None
    # Separate, transparent heuristic (calculate_sponsorship_likelihood); not yet
    # computed, so defaults to Unknown.
    sponsorship_likelihood: SponsorshipLikelihood = SponsorshipLikelihood.UNKNOWN
    sponsored_titles: list[dict] = []
    aliases: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    ambiguous_alternatives: list[dict] = []
    evidence: list[Evidence] = []
    evidence_ids: list[str] = []


class JDRequirement(BaseModel):
    """One extracted requirement/attribute from the job description.

    `id` (jd_req_01, …) is the citable evidence handle later analyses
    (resume fit, risk) must reference per the citation contract.
    """

    id: str
    category: Literal[
        "required_skill",
        "preferred_skill",
        "experience",
        "education",
        "responsibility",
        "location",
        "visa",
        "risk_keyword",
        "other",
    ] = "other"
    text: str
    evidence_quote: str = ""


class JDParse(BaseModel):
    """Structured view of the job description (LLM-extracted)."""

    available: bool = False
    reason: Optional[str] = None
    location: Optional[str] = None
    seniority: Optional[str] = None
    requirements: list[JDRequirement] = []
    visa_language: list[str] = []
    risk_keywords: list[str] = []
    evidence: list[Evidence] = []
    evidence_ids: list[str] = []


class ResumeFitAnalysis(BaseModel):
    available: bool = False
    reason: Optional[str] = None
    match_method: Optional[str] = None  # llm | vector
    strong_matches: list[Claim] = []
    partial_matches: list[Claim] = []
    missing: list[Claim] = []


class RecommendationResult(BaseModel):
    available: bool = False
    reason: Optional[str] = None
    decision: Optional[Recommendation] = None
    reasoning: str = ""
    evidence_ids: list[str] = []
    # Semantic track match (title ↔ profile), for eval + UI transparency.
    track_id: Optional[str] = None
    track_label: Optional[str] = None
    track_priority: Optional[int] = None
    track_similarity: Optional[float] = None
    fit_ratio: Optional[float] = None
    recommendation_method: Optional[str] = None  # llm | rules
    technical_penalty_hits: list[str] = []
    location_score: Optional[float] = None
    location_label: Optional[str] = None
    location_tier: Optional[int] = None
    summary: str = ""
    preferences_matched: int = 0
    preferences_total: int = 0
    dealbreakers_matched: int = 0
    dealbreakers_total: int = 0
    dealbreaker_hits: list[str] = []
    preference_hits: list[str] = []


class RiskAnalysis(BaseModel):
    available: bool = False
    reason: Optional[str] = None
    risks: list[Claim] = []


class CompanyAnalysis(BaseModel):
    """Employer quality vs profile preferences — separate from H-1B sponsor lookup."""

    available: bool = False
    reason: Optional[str] = None
    company_score: Optional[float] = None
    company_tier: Optional[int] = None
    company_label: str = ""
    summary: str = ""
    preference_hits: list[str] = []
    industry_label: Optional[str] = None
    dealbreakers_matched: int = 0
    dealbreaker_hits: list[str] = []
    score_breakdown: dict = {}
    linkedin_followers: Optional[int] = None
    alumni_hits: list[str] = []
    sources: list[dict] = []
    research_available: bool = False


class Report(BaseModel):
    status: Literal["partial", "complete"] = "partial"
    pending: list[str] = []
    sponsorship: SponsorshipAnalysis
    company: CompanyAnalysis = CompanyAnalysis()
    jd: JDParse = JDParse()
    resume_fit: ResumeFitAnalysis = ResumeFitAnalysis()
    risk: RiskAnalysis = RiskAnalysis()
    recommendation: RecommendationResult = RecommendationResult()
    received: dict = {}
    # Why each metric landed where it did — for UI tooltips and curl debugging.
    explain: dict = {}
