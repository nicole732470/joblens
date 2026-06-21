"""Personalized Company fit from external/structured company evidence only."""

from __future__ import annotations

import math
from typing import Any

from app.config import settings
from app.schemas.candidate_profile import CandidateProfile
from app.schemas.report import JDParse, SponsorshipAnalysis
from app.tools.company_research import research_company
from app.tools.embeddings import embed_texts
from app.tools.llm import complete_json_with_retry, llm_available

_DIMENSIONS = ("industry", "stage_funding", "scale_traction", "network")


def _applicable_preferences(profile: CandidateProfile) -> dict[str, list[str]]:
    prefs = profile.company_preferences
    return {
        "industry": [*prefs.industries, *[f"avoid: {v}" for v in prefs.avoid]],
        "stage_funding": [*prefs.stages, *prefs.funding_signals],
        "scale_traction": list(prefs.sizes),
        "network": [*prefs.network_signals, *profile.alumni_schools],
    }


def _structured_sources(
    sponsorship: SponsorshipAnalysis,
    linkedin_followers: int | None,
    alumni_hints: list[str] | None,
) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    company = sponsorship.company
    if company:
        bits = [
            f"Legal name: {company.name}" if company.name else "",
            f"NAICS: {company.naics_code} {company.naics_sector or ''}" if company.naics_code else "",
            f"Headquarters: {company.city}, {company.state}" if company.city and company.state else "",
        ]
        content = ". ".join(bit for bit in bits if bit)
        if content:
            sources.append({"title": "DOL employer record", "url": "dol://h1b", "content": content})
    if linkedin_followers is not None:
        sources.append(
            {
                "title": "LinkedIn company metadata",
                "url": "linkedin://visible-company-page",
                "content": f"LinkedIn followers: {linkedin_followers:,}",
            }
        )
    hints = [str(v).strip() for v in (alumni_hints or []) if str(v).strip()]
    if hints:
        sources.append(
            {
                "title": "LinkedIn network metadata",
                "url": "linkedin://visible-network-hints",
                "content": " | ".join(hints)[:2500],
            }
        )
    return sources


def _cosine(a: list[float], b: list[float]) -> float:
    denom = math.sqrt(sum(v * v for v in a)) * math.sqrt(sum(v * v for v in b))
    return sum(x * y for x, y in zip(a, b)) / denom if denom else 0.0


def _embedding_scores(
    applicable: dict[str, list[str]], sources: list[dict[str, str]]
) -> tuple[dict[str, float], dict[str, str]]:
    evidence = "\n".join(source["content"] for source in sources)
    dimensions = [name for name in _DIMENSIONS if applicable[name]]
    vectors = embed_texts([evidence, *["; ".join(applicable[name]) for name in dimensions]])
    scores: dict[str, float] = {}
    reasons: dict[str, str] = {}
    for index, name in enumerate(dimensions, start=1):
        similarity = _cosine(vectors[0], vectors[index])
        scores[name] = max(0.0, min(1.0, (similarity - 0.20) / 0.60))
        reasons[name] = f"embedding similarity {similarity:.2f}"
    return scores, reasons


def _llm_scores(
    company_name: str,
    applicable: dict[str, list[str]],
    sources: list[dict[str, str]],
) -> tuple[dict[str, float], dict[str, str], list[str], dict]:
    requested = {name: values for name, values in applicable.items() if values}
    indexed_sources = [
        {"index": i, "title": row["title"], "url": row["url"], "content": row["content"]}
        for i, row in enumerate(sources)
    ]
    result = complete_json_with_retry(
        """You score employer evidence against one user's explicit company preferences.
Score only requested dimensions from 0 to 1. A different user must receive different
scores when preferences differ. Do not infer facts from a job description. For every
score cite one or more supplied source indexes. Return JSON:
{"dimensions":{"industry":{"score":0.0,"reason":"...","source_indexes":[0]}},
 "avoid_hits":[]}. Omit unsupported dimensions; do not use a neutral default.""",
        f"Company: {company_name}\nUser preferences: {requested}\nEvidence: {indexed_sources}",
        max_tokens=1300,
    )
    scores: dict[str, float] = {}
    reasons: dict[str, str] = {}
    for name, row in (result.get("dimensions") or {}).items():
        if name not in requested or not isinstance(row, dict):
            continue
        indexes = row.get("source_indexes") or []
        if not any(isinstance(i, int) and 0 <= i < len(sources) for i in indexes):
            continue
        try:
            score = float(row.get("score"))
        except (TypeError, ValueError):
            continue
        scores[name] = max(0.0, min(1.0, score))
        reasons[name] = str(row.get("reason") or "evidence-backed AI score")[:300]
    avoid_hits = [str(v).strip() for v in (result.get("avoid_hits") or []) if str(v).strip()]
    return scores, reasons, avoid_hits, result


def _tier(score: float) -> int:
    if score >= 0.75:
        return 1
    if score >= 0.50:
        return 2
    if score >= 0.25:
        return 3
    return 4


def score_company(
    company_name: str | None,
    jd: JDParse,
    jd_text: str,
    profile: CandidateProfile,
    sponsorship: SponsorshipAnalysis,
    *,
    linkedin_followers: int | None = None,
    alumni_hints: list[str] | None = None,
) -> dict[str, Any]:
    """Score evidence against the current profile; JD arguments are identity-only legacy inputs."""
    del jd, jd_text
    name = (company_name or (sponsorship.company.name if sponsorship.company else None) or "").strip()
    if not name:
        return {"available": False, "reason": "no company name"}

    applicable = _applicable_preferences(profile)
    active = [name for name in _DIMENSIONS if applicable[name]]
    if not active:
        return {"available": False, "reason": "no company preferences configured"}

    research = research_company(name)
    sources = _structured_sources(sponsorship, linkedin_followers, alumni_hints)
    sources.extend(research.get("sources") or [])
    if not sources:
        return {"available": False, "reason": research.get("reason") or "no reliable company evidence"}

    method = "llm"
    try:
        if not llm_available():
            raise RuntimeError("LLM unavailable")
        scores, reasons, proposed_avoids, raw_output = _llm_scores(name, applicable, sources)
    except Exception:  # noqa: BLE001
        method = "embedding"
        try:
            scores, reasons = _embedding_scores(applicable, sources)
            proposed_avoids = []
            raw_output = None
        except Exception as exc:  # noqa: BLE001
            return {
                "available": False,
                "reason": f"company scoring unavailable: {type(exc).__name__}",
                "sources": sources,
            }

    scores = {key: value for key, value in scores.items() if key in active}
    if not scores:
        return {"available": False, "reason": "no applicable dimension supported by evidence", "sources": sources}

    configured_avoids = [value.strip() for value in profile.company_preferences.avoid if value.strip()]
    avoid_hits = [hit for hit in proposed_avoids if hit in configured_avoids]
    combined = sum(scores.values()) / len(scores)
    tier = 4 if avoid_hits else _tier(combined)
    confidence = "low" if len(scores) == 1 else "standard"
    return {
        "available": True,
        "company_score": round(combined, 3),
        "company_tier": tier,
        "company_label": f"P{tier} · personalized company fit",
        "summary": avoid_hits[0] if avoid_hits else f"{len(scores)}/{len(active)} applicable dimensions scored",
        "preference_hits": [],
        "industry_label": reasons.get("industry"),
        "dealbreakers_matched": 0,
        "dealbreaker_hits": [],
        "score_breakdown": {
            "dimensions": {key: round(value, 3) for key, value in scores.items()},
            "reasons": reasons,
            "applicable": active,
            "effective_weight": round(1 / len(scores), 3),
            "method": method,
            "confidence": confidence,
            "avoid_hits": avoid_hits,
            "prompt_version": "company-fit-v1",
            "model": settings.llm_model if method == "llm" else None,
            "raw_output": raw_output,
        },
        "linkedin_followers": linkedin_followers,
        "alumni_hits": [],
        "sources": sources,
        "research_available": bool(research.get("available")),
    }
