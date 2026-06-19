"""Basic resume ↔ JD fit via pgvector retrieval (no LLM classification yet)."""

from __future__ import annotations

from app.schemas.report import JDParse
from app.tools.resume_store import index_resume, retrieve_resume_evidence

# Cosine distance thresholds (tune against golden set later).
_STRONG_MAX = 0.28
_PARTIAL_MAX = 0.42


def analyze_resume_fit(jd: JDParse, resume_text: str) -> dict:
    """Match JD requirements to resume chunks. Returns ResumeFitAnalysis shape."""
    text = (resume_text or "").strip()
    if not text:
        return {"available": False, "reason": "no resume text provided"}
    if not jd.available:
        return {"available": False, "reason": "JD parsing unavailable"}
    if not jd.requirements:
        return {"available": False, "reason": "no JD requirements extracted"}

    indexed = index_resume(text)
    if not indexed.get("indexed"):
        return {"available": False, "reason": indexed.get("reason", "resume index failed")}

    resume_key = indexed["resume_key"]
    strong_matches: list[dict] = []
    partial_matches: list[dict] = []
    missing: list[dict] = []

    for req in jd.requirements:
        hits = retrieve_resume_evidence(req.text, resume_key, limit=1)
        if not hits:
            missing.append(_claim(req, [], "No resume evidence retrieved.", "missing"))
            continue

        hit = hits[0]
        dist = hit["distance"]
        snippet = hit["content"][:240].replace("\n", " ")
        reasoning = (
            f"Closest resume chunk ({hit['section']}): \"{snippet}\" "
            f"(cosine distance {dist:.3f})."
        )

        if dist <= _STRONG_MAX:
            strong_matches.append(_claim(req, [hit["id"]], reasoning, "strong"))
        elif dist <= _PARTIAL_MAX:
            partial_matches.append(_claim(req, [hit["id"]], reasoning, "partial"))
        else:
            missing.append(_claim(req, [hit["id"]], reasoning, "weak"))

    return {
        "available": True,
        "strong_matches": strong_matches,
        "partial_matches": partial_matches,
        "missing": missing,
    }


def _claim(req, resume_ids: list[str], reasoning: str, kind: str) -> dict:
    return {
        "claim": f"[{kind}] {req.text}",
        "claim_type": "resume_fit",
        "jd_evidence_ids": [req.id],
        "resume_evidence_ids": resume_ids,
        "h1b_evidence_ids": [],
        "reasoning": reasoning,
        "inference": False,
    }
