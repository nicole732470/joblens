"""Final verdict from independently validated job-fit dimensions."""

from __future__ import annotations

import hashlib
import json
import re

from app.config import settings
from app.schemas.candidate_profile import CandidateProfile
from app.schemas.report import JDParse, Recommendation, ResumeFitAnalysis
from app.tools.llm import complete_json_with_retry, llm_available
from app.tools.risk_rules import _jd_sponsorship_veto
from app.tools.track_match import resolve_job_title

_GENERIC_SUMMARIES = frozenset(
    {
        "not a strong fit",
        "low resume overlap",
        "limited resume overlap",
        "mixed fit",
        "key skills missing",
    }
)


def _polish_summary(decision: Recommendation, summary: str, reasoning: str, preflight: dict) -> str:
    s = (summary or "").strip()
    r = (reasoning or "").strip()
    if s and s.lower() not in _GENERIC_SUMMARIES and len(s) >= 12:
        return s[:120]
    # Fall back to first sentence of reasoning.
    if r:
        first = re.split(r"(?<=[.!?])\s+", r, maxsplit=1)[0].strip()
        if len(first) >= 12:
            return first[:120]
    if decision == Recommendation.SKIP:
        tm = preflight.get("semantic_track_match") or {}
        if tm.get("track_priority") and int(tm["track_priority"]) >= 4:
            label = tm.get("track_label") or "off-target track"
            return f"Off-target track ({label})"
        rf = preflight.get("resume_fit_counts") or {}
        if rf.get("missing", 0) >= 3 and rf.get("strong", 0) == 0:
            return "Resume lacks evidence for core JD requirements"
    return s[:120] if s else "See reasoning"


_DECISION_ALIASES = {
    "apply": Recommendation.APPLY,
    "near apply": Recommendation.NEAR_APPLY,
    "near_apply": Recommendation.NEAR_APPLY,
    "nearapply": Recommendation.NEAR_APPLY,
    "consider": Recommendation.CONSIDER,
    "skip": Recommendation.SKIP,
}


def _normalize_decision(raw: str | None) -> Recommendation:
    key = (raw or "").strip().lower().replace("_", " ")
    if key in _DECISION_ALIASES:
        return _DECISION_ALIASES[key]
    for enum in Recommendation:
        if enum.value.lower() == key:
            return enum
    raise ValueError(f"invalid decision from model: {raw!r}")


def generate_recommendation_llm(
    jd: JDParse,
    resume_fit: ResumeFitAnalysis,
    profile: CandidateProfile,
    job_title: str | None,
    jd_text: str | None = None,
    *,
    resume_text: str | None = None,
    job_location: str | None = None,
) -> dict:
    """Run independent dimensions in parallel, then synthesize only the verdict."""
    if not llm_available():
        raise RuntimeError("LLM not configured")

    title = resolve_job_title(job_title, jd_text)
    raw_jd = (jd_text or "").strip()
    resume = (resume_text or "").strip()

    if not raw_jd and jd.available:
        raw_jd = "\n".join(r.text for r in jd.requirements)

    from app.tools.recommendation import _collect_evidence_ids, _signal_fields

    if not jd.available:
        return {"available": False, "reason": "JD parsing unavailable"}

    if not resume:
        return {"available": False, "reason": "no resume text for LLM recommendation"}

    from app.tools.independent_decisions import run_independent_decisions

    records = run_independent_decisions(title, raw_jd, jd, profile, job_location)
    track_fields = dict(records["role"]["validated_output"])
    location_fields = dict(records["location"]["validated_output"])
    profile_fields = dict(records["preferences_dealbreakers"]["validated_output"])
    signal_fields = {**location_fields, **profile_fields}

    fit_ratio = None
    if resume_fit.available:
        from app.tools.recommendation import _fit_counts

        _s, _p, _w, _g, ratio = _fit_counts(resume_fit)
        fit_ratio = round(ratio, 3)

    profile_json = json.dumps(profile.model_dump(), sort_keys=True, ensure_ascii=False)
    debug = {
        "profile_version": hashlib.sha256(profile_json.encode()).hexdigest()[:12],
        "model": settings.llm_model,
        "decisions": records,
    }

    # Clear cases are rules-only. Only ambiguous cases call the verdict LLM.
    veto, _veto_ids, _veto_quote = _jd_sponsorship_veto(jd)
    has_sponsorship_veto = profile.constraints.needs_sponsorship and veto
    hard_dealbreakers = signal_fields.get("dealbreaker_hits") or []
    role_priority = track_fields.get("track_priority")
    role_status = track_fields.get("role_status")
    raw_final = None
    override_reason = None
    if has_sponsorship_veto or hard_dealbreakers:
        decision = Recommendation.SKIP
        reasoning = "A deterministic hard constraint vetoed this job."
        summary = (
            "Job explicitly excludes required visa sponsorship"
            if has_sponsorship_veto
            else f"Dealbreaker: {hard_dealbreakers[0]}"
        )
        method = "rules"
        override_reason = "sponsorship veto" if has_sponsorship_veto else "dealbreaker veto"
    elif role_priority in (1, 2) and fit_ratio is not None and fit_ratio > 0.50:
        decision = Recommendation.APPLY
        reasoning = "Configured P1/P2 role and resume fit exceeds the 50% Apply guardrail."
        summary = f"P{role_priority} target role · resume fit {fit_ratio:.0%}"
        method = "rules"
        override_reason = "P1/P2 + resume > 50%"
    elif role_status == "avoid":
        decision = Recommendation.SKIP
        reasoning = "The role matches a track the user explicitly placed in avoid_tracks."
        summary = f"Explicit avoid track: {track_fields.get('track_label') or 'user-excluded role'}"
        method = "rules"
        override_reason = "explicit avoid track"
    else:
        method = "llm"
        final_input = {
            "fixed_dimensions": {
                "role": track_fields,
                "resume_fit": fit_ratio,
                "location": location_fields,
                "profile_signals": profile_fields,
            },
            "resume_evidence": [
                {"claim": c.claim, "reasoning": c.reasoning}
                for c in [*resume_fit.strong_matches, *resume_fit.partial_matches, *resume_fit.missing]
            ][:20],
        }
        try:
            raw_final = complete_json_with_retry(
                """Choose only the final verdict from already-fixed independent dimensions.
Do not reclassify Role, Resume, Location, preferences, or dealbreakers. An unmatched P4 Role
means the user's examples did not cover it; it is a low-priority signal, NOT an automatic Skip.
Consider resume evidence, location, preferences, company and risks together. Name the concrete
reason for the verdict; never use only 'outside configured tracks' or another generic phrase.
Return JSON only:
{"decision":"Apply|Near apply|Consider|Skip","reasoning":"2-3 evidence-based sentences",
"summary":"one concrete line under 100 characters"}.""",
                json.dumps(final_input, ensure_ascii=False),
                max_attempts=1,
                max_tokens=650,
            )
            decision = _normalize_decision(raw_final.get("decision"))
            reasoning = str(raw_final.get("reasoning") or "").strip()
            summary = _polish_summary(
                decision,
                str(raw_final.get("summary") or ""),
                reasoning,
                {"semantic_track_match": track_fields},
            )
        except Exception as exc:  # noqa: BLE001
            method = "rules_fallback"
            override_reason = f"final LLM failed: {type(exc).__name__}"
            if role_priority in (1, 2) and (fit_ratio or 0) >= 0.22:
                decision = Recommendation.NEAR_APPLY
            elif role_priority == 3 and (fit_ratio or 0) >= 0.28:
                decision = Recommendation.CONSIDER
            else:
                decision = Recommendation.SKIP
            reasoning = "Deterministic boundary fallback after final-verdict LLM failure."
            summary = f"P{role_priority or 4} role · resume fit {(fit_ratio or 0):.0%}"

    debug["final_verdict"] = {
        "dimension": "final_verdict",
        "model": settings.llm_model if method == "llm" else None,
        "prompt_version": "final-verdict-v1",
        "method": method,
        "raw_output": raw_final,
        "validated_output": {"decision": decision.value, "reasoning": reasoning, "summary": summary},
        "rule_override": override_reason,
    }

    evidence_ids = _collect_evidence_ids(resume_fit, jd) if resume_fit.available else []
    if profile.constraints.needs_sponsorship:
        veto, jd_ids, _quote = _jd_sponsorship_veto(jd)
        if veto:
            evidence_ids = list(dict.fromkeys([*jd_ids, *evidence_ids]))

    return {
        "available": True,
        "decision": decision,
        "reasoning": reasoning,
        "summary": summary,
        "evidence_ids": evidence_ids,
        "fit_ratio": fit_ratio,
        "recommendation_method": method,
        "debug_decisions": debug,
        **signal_fields,
        **track_fields,
    }
