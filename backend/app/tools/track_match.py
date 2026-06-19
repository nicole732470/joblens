"""Semantic job-title ↔ profile track matching via embeddings (not keyword lists)."""

from __future__ import annotations

import math
import re

from app.schemas.candidate_profile import AvoidTrack, CandidateProfile, Track
from app.schemas.report import JDParse
from app.tools.embeddings import embed_texts


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _normalize_title(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _strip_parens(s: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", s).strip()


def _title_matches_example(job_title: str, example: str) -> bool:
    """Phrase-level match — engineer/engineering + intern suffix tolerant."""
    j = _normalize_title(_strip_parens(job_title))
    e = _normalize_title(example)
    if not j or not e:
        return False
    if j == e:
        return True
    if re.search(rf"\b{re.escape(e)}\b", j):
        return True
    if len(j) >= 10 and re.search(rf"\b{re.escape(j)}\b", e):
        return True

    def _fold(s: str) -> str:
        s = re.sub(r"\bengineering\b", "engineer", s)
        s = re.sub(r"\s+intern(ship)?\b", "", s).strip()
        return re.sub(r"\s+", " ", s)

    jf, ef = _fold(j), _fold(e)
    if jf == ef:
        return True
    if re.search(rf"\b{re.escape(ef)}\b", jf):
        return True
    if len(jf) >= 8 and re.search(rf"\b{re.escape(jf)}\b", ef):
        return True
    return False


# Title keywords → track id (checked before embedding so JD hardware text cannot override).
_TITLE_KEYWORD_RULES: list[tuple[str, str]] = [
    (r"\bsolutions?\s+engineer(?:ing)?\b", "pm_eng"),
    (r"\bsolution\s+architect\b", "pm_eng"),
    (r"\bcustomer success\b", "customer_success"),
    (r"\bcsm\b", "customer_success"),
    (r"\bapplied research engineer\b", "research_eng"),
    (r"\bresearch engineer\b", "research_eng"),
    (r"\b(data|business)\s+analyst\b", "business_analyst"),
    (r"\banalyst\b", "business_analyst"),
    (r"\bconsultant\b", "business_analyst"),
]


def _keyword_track_from_title(title: str, profile: CandidateProfile) -> Track | None:
    candidates = [title, _strip_parens(title)]
    for raw in candidates:
        t = (raw or "").lower()
        if not t:
            continue
        for pattern, track_id in _TITLE_KEYWORD_RULES:
            if re.search(pattern, t, re.I):
                for tr in profile.tracks:
                    if tr.id == track_id:
                        return tr
    return None


def _similarity_to_track(title: str, track: Track) -> float:
    try:
        vectors = embed_texts([title, _track_descriptor(track)])
        return round(_cosine_similarity(vectors[0], vectors[1]), 3)
    except Exception:
        return 0.0


def _exact_track_match(title: str, profile: CandidateProfile) -> tuple[Track | None, float]:
    """Literal match against track labels (exact) and example_titles (phrase-level)."""
    best: Track | None = None
    best_priority = 999
    t_norm = _normalize_title(_strip_parens(title))

    for tr in profile.tracks:
        label_norm = _normalize_title(tr.label)
        if label_norm and t_norm == label_norm:
            if tr.priority < best_priority:
                best = tr
                best_priority = tr.priority
        for ex in tr.example_titles or []:
            if _title_matches_example(title, ex) and tr.priority < best_priority:
                best = tr
                best_priority = tr.priority

    if best:
        return best, 1.0
    return None, 0.0


def _exact_avoid_match(title: str, profile: CandidateProfile) -> tuple[str | None, float]:
    for av in profile.avoid_tracks:
        if _normalize_title(av.label) in _normalize_title(_strip_parens(title)):
            return av.label, 1.0
        for ex in av.example_titles or []:
            if _title_matches_example(title, ex):
                return av.label, 1.0
    return None, 0.0


def _track_descriptor(track: Track | AvoidTrack) -> str:
    """One text blob per track for embedding — meaning, not exact title whitelist."""
    parts = [track.label]
    if track.example_titles:
        parts.append("Example titles: " + ", ".join(track.example_titles[:12]))
    return ". ".join(parts)


# Min cosine similarity (0–1) to accept a track match. Tune via golden set.
_TRACK_MATCH_MIN = 0.30
_AVOID_MATCH_MIN = 0.38


def match_title_to_profile(
    title: str,
    profile: CandidateProfile,
) -> dict:
    """Return semantic track match metadata for a job title.

    Keys: matched_track (Track|None), similarity, avoid_match (bool), avoid_label
    """
    title = (title or "").strip()
    if not title or not profile.tracks:
        return {
            "matched_track": None,
            "similarity": 0.0,
            "avoid_match": False,
            "avoid_label": None,
        }

    exact_track, exact_sim = _exact_track_match(title, profile)
    avoid_label_exact, avoid_sim_exact = _exact_avoid_match(title, profile)
    if avoid_label_exact and avoid_sim_exact >= (exact_sim if exact_track else 0):
        return {
            "matched_track": None,
            "similarity": exact_sim if exact_track else 0.0,
            "avoid_match": True,
            "avoid_label": avoid_label_exact,
        }

    want: list[tuple[Track, str]] = [(tr, _track_descriptor(tr)) for tr in profile.tracks]
    avoid: list[tuple[AvoidTrack, str]] = [(a, _track_descriptor(a)) for a in profile.avoid_tracks]

    texts = [title] + [d for _, d in want] + [d for _, d in avoid]
    try:
        vectors = embed_texts(texts)
    except Exception:
        if exact_track:
            return {
                "matched_track": exact_track,
                "similarity": exact_sim,
                "avoid_match": False,
                "avoid_label": None,
            }
        return {
            "matched_track": None,
            "similarity": 0.0,
            "avoid_match": False,
            "avoid_label": None,
        }

    title_vec = vectors[0]
    best_track: Track | None = exact_track
    best_sim = exact_sim
    for i, (tr, _) in enumerate(want):
        sim = _cosine_similarity(title_vec, vectors[1 + i])
        if sim > best_sim:
            best_sim = sim
            best_track = tr
        elif sim == best_sim and tr.priority < (best_track.priority if best_track else 999):
            best_track = tr

    avoid_sim = 0.0
    avoid_label = None
    offset = 1 + len(want)
    for j, (av, _) in enumerate(avoid):
        sim = _cosine_similarity(title_vec, vectors[offset + j])
        if sim > avoid_sim:
            avoid_sim = sim
            avoid_label = av.label

    avoid_match = avoid_sim >= _AVOID_MATCH_MIN and avoid_sim >= best_sim

    if best_sim < _TRACK_MATCH_MIN:
        best_track = None

    return {
        "matched_track": best_track,
        "similarity": round(best_sim, 3),
        "avoid_match": avoid_match,
        "avoid_label": avoid_label if avoid_match else None,
    }


def _job_content_blob(title: str, jd: JDParse | None, jd_text: str) -> str:
    """Title + parsed JD responsibilities/skills — role content, not title alone."""
    parts: list[str] = []
    if title:
        parts.append(f"Job title: {title}")
    if jd and jd.available:
        if jd.seniority:
            parts.append(f"Level: {jd.seniority}")
        for req in jd.requirements:
            if req.category in (
                "required_skill",
                "preferred_skill",
                "responsibility",
                "experience",
                "other",
            ):
                parts.append(req.text)
    elif jd_text:
        parts.append(jd_text[:2500])
    blob = ". ".join(p for p in parts if p)
    return blob[:4500] if len(blob) > 4500 else blob


def resolve_job_title(title: str | None, jd_text: str | None) -> str:
    """Best-effort title — LinkedIn sometimes fails to send the h1."""
    t = (title or "").strip()
    if t and len(t) >= 6:
        return t
    raw = (jd_text or "").strip()
    if not raw:
        return t

    skip_prefix = (
        "work environment",
        "we collaborate",
        "about ",
        "company ",
        "equal opportunity",
        "location:",
    )
    role_kw = re.compile(
        r"\b(analyst|engineer|manager|developer|architect|consultant|designer|scientist)\b",
        re.I,
    )
    candidates: list[str] = []
    for line in raw.splitlines()[:15]:
        line = line.strip()
        if len(line) < 8 or len(line) > 140:
            continue
        low = line.lower()
        if any(low.startswith(p) for p in skip_prefix):
            continue
        candidates.append(line)

    for line in candidates:
        if role_kw.search(line):
            return line
    if candidates:
        return candidates[0]
    return t or raw[:140].split("\n", 1)[0].strip()


def match_job_to_profile(
    title: str,
    jd_text: str,
    jd: JDParse | None,
    profile: CandidateProfile,
) -> dict:
    """Match job title to profile tracks (JD text is intentionally ignored for track family).

    Full JD embeddings previously pulled hardware/AI keywords toward the wrong P-tier
    (e.g. Analyst title + CPU/GPU JD → P1 AI track at 100%).
    """
    title = (title or "").strip()
    if not title or not profile.tracks:
        return match_title_to_profile(title, profile)

    avoid_label_exact, avoid_sim_exact = _exact_avoid_match(title, profile)
    exact_track, exact_sim = _exact_track_match(title, profile)
    if avoid_label_exact and avoid_sim_exact >= (exact_sim if exact_track else 0):
        return {
            "matched_track": None,
            "similarity": exact_sim if exact_track else 0.0,
            "avoid_match": True,
            "avoid_label": avoid_label_exact,
        }

    kw_track = _keyword_track_from_title(title, profile)
    if kw_track:
        sim = exact_sim if exact_track and exact_track.id == kw_track.id else _similarity_to_track(title, kw_track)
        if sim < _TRACK_MATCH_MIN:
            sim = _TRACK_MATCH_MIN
        return {
            "matched_track": kw_track,
            "similarity": round(sim, 3),
            "avoid_match": False,
            "avoid_label": None,
        }

    return match_title_to_profile(title, profile)
