"""Location tier, preferences, and dealbreaker signals from JD + profile."""

from __future__ import annotations

import math
import re

from app.schemas.candidate_profile import CandidateProfile
from app.schemas.report import JDParse
from app.tools.embeddings import embed_texts

# Embedding cosine minimum for preference / dealbreaker (not exact substring).
_SEMANTIC_PHRASE_MIN = 0.36

_LOOSE_SKIP = frozenset(
    {
        "backed",
        "startup",
        "company",
        "stack",
        "industry",
        "the",
        "and",
        "non",
        "pre",
        "ipo",
        "with",
        "from",
        "your",
        "for",
    }
)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _jd_scan_blob(jd: JDParse, jd_text: str) -> str:
    parts: list[str] = []
    if jd.available:
        if jd.location:
            parts.append(jd.location)
        for req in jd.requirements:
            parts.append(req.text)
            if req.evidence_quote:
                parts.append(req.evidence_quote)
        parts.extend(jd.visa_language or [])
        parts.extend(jd.risk_keywords or [])
    if jd_text:
        parts.append(jd_text[:3000])
    return " ".join(parts)


_WORK_ENV_RE = re.compile(
    r"work environment\s*:\s*(.+?)(?:\n|$)",
    re.I,
)


def _primary_location_blob(
    jd: JDParse,
    jd_text: str,
    job_title: str | None = None,
    job_location: str | None = None,
) -> str:
    """Text that describes where *this* job is based — not HQ mentions elsewhere in the JD."""
    parts: list[str] = []
    if job_location and job_location.strip():
        parts.append(job_location.strip())
    if job_title:
        parts.append(job_title.strip())
    raw = jd_text or ""

    m = _WORK_ENV_RE.search(raw)
    if m:
        parts.append(m.group(1).strip())

    if jd.available and jd.location:
        parts.append(jd.location)
    for req in jd.requirements:
        if req.category == "location":
            parts.append(req.text)
            if req.evidence_quote:
                parts.append(req.evidence_quote)

    place = _extract_place(raw.lower(), jd)
    if place:
        parts.append(place)

    if not parts and raw:
        parts.append(raw[:600])

    return " ".join(parts)


def _full_job_blob(jd: JDParse, jd_text: str, job_title: str | None) -> str:
    parts: list[str] = []
    if job_title:
        parts.append(f"Job title: {job_title}")
    parts.append(_jd_scan_blob(jd, jd_text))
    blob = " ".join(parts)
    return blob[:4500] if len(blob) > 4500 else blob


def _anchor_tokens(phrase: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", phrase.lower())
    return [t for t in tokens if t not in _LOOSE_SKIP and (len(t) >= 3 or t in ("yc",))]


def _token_in_blob(token: str, blob_lower: str) -> bool:
    return bool(re.search(rf"\b{re.escape(token)}\b", blob_lower))


_PAID_COMP_RE = re.compile(
    r"\$[\d,.]+|"
    r"\bhourly rate\b|\bpay transparency\b|\bcompensation description\b|"
    r"\b\d+[\d,.]*\s*(?:usd|dollars)?\s*/?\s*(?:hour|hr|year|yr|annually)\b",
    re.I,
)


def _has_paid_compensation(blob_lower: str) -> bool:
    return bool(_PAID_COMP_RE.search(blob_lower))


def _dealbreaker_phrase_hit(phrase: str, blob_lower: str) -> bool:
    """Strict dealbreaker match — avoids «intern»/«company» substring false positives."""
    p = (phrase or "").strip().lower()
    if not p or not blob_lower:
        return False

    if p == "unpaid internship":
        if _has_paid_compensation(blob_lower):
            return False
        if "unpaid internship" in blob_lower or "unpaid intern" in blob_lower:
            return True
        return _token_in_blob("unpaid", blob_lower) and bool(
            re.search(r"\bintern(?:ship)?\b", blob_lower)
        )

    if p == "no one in the company studied in a prestigious university":
        return (
            _token_in_blob("prestigious", blob_lower)
            and _token_in_blob("university", blob_lower)
            and bool(
                re.search(
                    r"\b(studied|alumni|graduated|degree from|attended)\b",
                    blob_lower,
                )
            )
        )

    if p in blob_lower:
        return True

    anchors = _anchor_tokens(phrase)
    if len(anchors) >= 2:
        return all(_token_in_blob(a, blob_lower) for a in anchors)
    if len(anchors) == 1:
        return _token_in_blob(anchors[0], blob_lower)
    return False


def _dealbreaker_hits(phrases: list[str], job_blob: str) -> tuple[int, list[str]]:
    """Dealbreakers use strict literal rules only — no embedding (too many false positives)."""
    if not phrases or not job_blob.strip():
        return 0, []
    blob_lower = job_blob.lower()
    hits = [p for p in phrases if _dealbreaker_phrase_hit(p, blob_lower)]
    return len(hits), hits


def _loose_phrase_hit(phrase: str, blob_lower: str) -> bool:
    p = (phrase or "").strip().lower()
    if not p:
        return False
    if p in blob_lower:
        return True
    if "y combinator" in p and ("y combinator" in blob_lower or " yc " in blob_lower or "yc-backed" in blob_lower):
        return True
    anchors = _anchor_tokens(phrase)
    return bool(anchors) and any(a in blob_lower for a in anchors)


def _semantic_phrase_hits(phrases: list[str], job_blob: str) -> tuple[int, list[str]]:
    if not phrases:
        return 0, []
    blob_lower = job_blob.lower()
    hits: list[str] = []
    for phrase in phrases:
        if _loose_phrase_hit(phrase, blob_lower):
            hits.append(phrase)

    remaining = [p for p in phrases if p not in hits]
    if not remaining or not job_blob.strip():
        return len(hits), hits

    try:
        texts = [job_blob[:3500]] + remaining
        vectors = embed_texts(texts)
        job_vec = vectors[0]
        for i, phrase in enumerate(remaining):
            if _cosine_similarity(job_vec, vectors[1 + i]) >= _SEMANTIC_PHRASE_MIN:
                hits.append(phrase)
    except Exception:
        pass

    return len(hits), hits


def _place_in_text(place: str, text: str) -> bool:
    p = (place or "").strip().lower()
    return bool(p and p in text)


_CITY_TO_REGION: dict[str, str] = {
    "san francisco": "california",
    "san francisco bay area": "california",
    "sf bay area": "california",
    "bay area": "california",
    "palo alto": "california",
    "san jose": "california",
    "los angeles": "california",
    "mountain view": "california",
    "new york city": "new york",
    "nyc": "new york",
    "manhattan": "new york",
    "brooklyn": "new york",
    "austin": "texas",
    "dallas": "texas",
    "houston": "texas",
    "chicago": "chicago",
}


def _match_tier_places(places: list[str], text: str) -> str | None:
    for place in places:
        if _place_in_text(place, text):
            return place
    for city, region in _CITY_TO_REGION.items():
        if city not in text:
            continue
        for place in places:
            pl = place.lower()
            if pl == region or region in pl or pl in region:
                return place
    return None


_ONSITE_RE = re.compile(
    r"\b("
    r"full[- ]time in office|in[- ]office|on[- ]site|on site|\bonsite\b|"
    r"in person|in-person|office based|office-based|must be located"
    r")\b",
    re.I,
)
_REMOTE_POLICY_RE = re.compile(
    r"\b("
    r"fully remote|remote[- ]first|remote[- ]friendly|"
    r"work from home|\bwfh\b|work remotely|telecommut|"
    r"remote work(?:\s*eligible|\s*option|\s*available)?|"
    r"hybrid(?:\s*remote|\s*work)?"
    r")\b",
    re.I,
)
_REMOTE_NEG_RE = re.compile(
    r"\b(not|no)\s+(a\s+)?remote\b|\bnon[- ]remote\b|\bisn['']t remote\b|\bcannot work remote\b",
    re.I,
)
_REMOTE_TECH_RE = re.compile(
    r"\bremote (?:monitoring|access|desktop|support|debugging|login|session|server|control|diagnostics)\b",
    re.I,
)
_PLACE_RE = re.compile(r"\b([A-Za-z][A-Za-z .'-]{1,40}),\s*([A-Za-z]{2})\b")
_RURAL_KW = ("rural", "small town", "agricultural", "farm community")


def _extract_place(text: str, jd: JDParse) -> str | None:
    if jd.available and jd.location:
        loc = jd.location.strip()
        if loc and loc.lower() not in ("remote", "unknown", "n/a"):
            return loc
    m = _PLACE_RE.search(text)
    if m:
        return f"{m.group(1).strip()}, {m.group(2)}"
    return None


def _tier3_semantic_hit(profile: CandidateProfile, text: str) -> bool:
    blob = text.lower()
    for phrase in profile.locations.tier_3:
        if _loose_phrase_hit(phrase, blob):
            return True
    return any(k in blob for k in _RURAL_KW)


def _is_onsite_job(text: str) -> bool:
    return bool(_ONSITE_RE.search(text))


def _mentions_remote_policy(text: str) -> bool:
    if _REMOTE_NEG_RE.search(text):
        return False
    if _is_onsite_job(text) and not re.search(r"\bhybrid\b", text, re.I):
        return False
    if _REMOTE_POLICY_RE.search(text):
        return True
    if _REMOTE_TECH_RE.search(text):
        return False
    if re.search(r"\bremote\b", text, re.I):
        return not _is_onsite_job(text)
    if "distributed team" in text or "distributed workforce" in text:
        return True
    return False


def score_location(
    jd: JDParse,
    jd_text: str,
    profile: CandidateProfile,
    job_title: str | None = None,
    job_location: str | None = None,
) -> dict:
    """Return location_score, location_label, location_tier (P1–P3) for UI."""
    # LinkedIn location line (under title) — trust before JD HQ noise.
    if job_location and job_location.strip():
        loc_line = job_location.strip().lower()
        for tier_num, places, score in (
            (1, profile.locations.tier_1, 1.0),
            (2, profile.locations.tier_2, 0.75),
            (3, profile.locations.tier_3, 0.25),
        ):
            hit = _match_tier_places(places, loc_line)
            if hit:
                return {
                    "location_score": score,
                    "location_label": f"P{tier_num} · {hit}",
                    "location_tier": tier_num,
                }

    full_raw = _jd_scan_blob(jd, jd_text)
    primary_raw = _primary_location_blob(jd, jd_text, job_title, job_location)
    place = _extract_place(primary_raw, jd) or _extract_place(full_raw, jd)
    full = full_raw.lower()
    primary = primary_raw.lower()

    if not full.strip() and not primary.strip():
        return {"location_score": None, "location_label": "—", "location_tier": None}

    tier_text = primary if primary.strip() else full
    policy_text = primary if primary.strip() else full
    # Match tiers on job-location text AND extracted place (e.g. "Chicago, IL" → P1).
    loc_blob = f"{tier_text} {place or ''}".lower().strip()

    for tier_num, places, score in (
        (1, profile.locations.tier_1, 1.0),
        (2, profile.locations.tier_2, 0.75),
        (3, profile.locations.tier_3, 0.25),
    ):
        title_blob = (job_title or "").lower()
        hit = (
            _match_tier_places(places, loc_blob)
            or _match_tier_places(places, tier_text)
            or _match_tier_places(places, full)
            or (title_blob and _match_tier_places(places, title_blob))
        )
        if hit:
            return {
                "location_score": score,
                "location_label": f"P{tier_num} · {hit}",
                "location_tier": tier_num,
            }

    if profile.locations.remote_ok and _mentions_remote_policy(policy_text):
        return {"location_score": 0.75, "location_label": "P2 · Remote", "location_tier": 2}

    if _tier3_semantic_hit(profile, tier_text):
        suffix = place or "rural / avoid area"
        return {"location_score": 0.25, "location_label": f"P3 · {suffix}", "location_tier": 3}

    if _is_onsite_job(policy_text) or place:
        suffix = place or "onsite"
        return {"location_score": 0.35, "location_label": f"P3 · {suffix}", "location_tier": 3}

    return {"location_score": 0.5, "location_label": "P3 · unspecified", "location_tier": 3}


def evaluate_profile_signals(
    jd: JDParse,
    jd_text: str,
    profile: CandidateProfile,
    job_title: str | None = None,
    job_location: str | None = None,
) -> dict:
    job_blob = _full_job_blob(jd, jd_text, job_title)
    loc = score_location(jd, jd_text, profile, job_title, job_location)
    pref_n, pref_hits = _semantic_phrase_hits(profile.preferences, job_blob)
    deal_n, deal_hits = _dealbreaker_hits(profile.dealbreakers, job_blob)
    return {
        **loc,
        "preferences_matched": pref_n,
        "preferences_total": len(profile.preferences),
        "preference_hits": pref_hits[:5],
        "dealbreakers_matched": deal_n,
        "dealbreakers_total": len(profile.dealbreakers),
        "dealbreaker_hits": deal_hits[:5],
    }
