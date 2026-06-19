"""Resume ↔ JD fit: RAG retrieval + LLM classification (vector distance fallback)."""

from __future__ import annotations

from app.config import settings
from app.schemas.report import JDParse
from app.tools.llm import llm_available
from app.tools.resume_fit_llm import classify_requirements_llm
from app.tools.resume_store import index_resume, retrieve_resume_evidence

# Cosine distance thresholds when LLM unavailable or fails (lower = stricter).
_STRONG_MAX = 0.34
_PARTIAL_MAX = 0.52
_RETRIEVE_LIMIT = 3


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
    mode = (settings.resume_fit_method or "auto").lower()

    if mode in ("auto", "llm") and llm_available():
        try:
            return _analyze_with_llm(jd, resume_key)
        except Exception as e:  # noqa: BLE001
            if mode == "llm":
                return {"available": False, "reason": f"LLM resume fit failed: {e}"}
            # auto → fall through to vector

    return _analyze_with_vector(jd, resume_key)


def _analyze_with_llm(jd: JDParse, resume_key: str) -> dict:
    classified = classify_requirements_llm(jd, resume_key)
    strong_matches: list[dict] = []
    partial_matches: list[dict] = []
    missing: list[dict] = []

    for req in jd.requirements:
        meta = classified.get(req.id)
        if not meta:
            missing.append(_claim(req, [], "Not classified.", "missing"))
            continue

        level = meta["level"]
        reasoning = meta.get("reasoning") or ""
        candidates = meta.get("candidates") or []
        resume_id = meta.get("resume_evidence_id")
        resume_ids: list[str] = []
        if resume_id and any(c["id"] == resume_id for c in candidates):
            resume_ids = [str(resume_id)]
        elif candidates and level != "missing":
            resume_ids = [candidates[0]["id"]]

        if level == "strong":
            strong_matches.append(_claim(req, resume_ids, reasoning, "strong"))
        elif level == "partial":
            partial_matches.append(_claim(req, resume_ids, reasoning, "partial"))
        else:
            kind = "weak" if candidates else "missing"
            missing.append(_claim(req, resume_ids, reasoning or "No resume evidence.", kind))

    return {
        "available": True,
        "match_method": "llm",
        "strong_matches": strong_matches,
        "partial_matches": partial_matches,
        "missing": missing,
    }


def _analyze_with_vector(jd: JDParse, resume_key: str) -> dict:
    strong_matches: list[dict] = []
    partial_matches: list[dict] = []
    missing: list[dict] = []

    for req in jd.requirements:
        query = req.text
        if req.evidence_quote:
            query = f"{req.text}. {req.evidence_quote}"
        hits = retrieve_resume_evidence(query, resume_key, limit=1)
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
        "match_method": "vector",
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
