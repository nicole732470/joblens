"""Semantic job-title ↔ profile track matching via embeddings (not keyword lists)."""

from __future__ import annotations

import math

from app.schemas.candidate_profile import AvoidTrack, CandidateProfile, Track
from app.tools.embeddings import embed_texts


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


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

    want: list[tuple[Track, str]] = [(tr, _track_descriptor(tr)) for tr in profile.tracks]
    avoid: list[tuple[AvoidTrack, str]] = [(a, _track_descriptor(a)) for a in profile.avoid_tracks]

    texts = [title] + [d for _, d in want] + [d for _, d in avoid]
    try:
        vectors = embed_texts(texts)
    except Exception:
        return {
            "matched_track": None,
            "similarity": 0.0,
            "avoid_match": False,
            "avoid_label": None,
        }

    title_vec = vectors[0]
    best_track: Track | None = None
    best_sim = 0.0
    for i, (tr, _) in enumerate(want):
        sim = _cosine_similarity(title_vec, vectors[1 + i])
        if sim > best_sim:
            best_sim = sim
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
