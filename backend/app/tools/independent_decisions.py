"""Parallel, independently validated profile decisions for one job."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from app.config import settings
from app.schemas.candidate_profile import CandidateProfile
from app.schemas.report import JDParse
from app.tools.llm import complete_json_with_retry
from app.tools.profile_signals import evaluate_profile_signals
from app.tools.role_priority import apply_technical_penalties
from app.tools.track_match import match_role_content_to_profile

_ROLE_EMBEDDING_MIN = 0.55
_TRADITIONAL_ENGINEERING_TITLE_RE = re.compile(
    r"\b(electrical|mechanical|civil|architectural|structural|construction)\s+engineer(?:ing)?\b",
    re.I,
)
_AI_ROLE_RE = re.compile(
    r"\b(artificial intelligence|machine learning|deep learning|generative ai|llm|rag|agentic|ai engineer)\b",
    re.I,
)

ROLE_PROMPT_VERSION = "role-v1"
LOCATION_PROMPT_VERSION = "location-v1"
PREFS_PROMPT_VERSION = "profile-signals-v1"


def _record(dimension: str, prompt_version: str, inputs: dict) -> dict:
    return {
        "dimension": dimension,
        "model": settings.llm_model,
        "prompt_version": prompt_version,
        "method": "llm",
        "inputs": inputs,
        "evidence": [],
        "raw_output": None,
        "validated_output": None,
        "validation_error": None,
        "fallback_reason": None,
    }


def _run_with_fallback(record: dict, primary: Callable[[], dict], fallback: Callable[[], dict]) -> dict:
    try:
        raw = primary()
        record["raw_output"] = raw
        validated = raw.pop("_validated")
        record["evidence"] = raw.get("evidence") or []
        record["validated_output"] = validated
        return record
    except Exception as exc:  # noqa: BLE001
        record["validation_error"] = f"{type(exc).__name__}: {exc}"
        record["fallback_reason"] = "LLM failed or returned invalid structured output"
        record["method"] = "embedding/rules"
        validated = fallback()
        record["validated_output"] = validated
        record["evidence"] = validated.get("evidence") or []
        return record


def decide_role(title: str, jd_text: str, jd: JDParse, profile: CandidateProfile) -> dict:
    inputs = {
        "job_title": title,
        "tracks": [t.model_dump() for t in profile.tracks],
        "avoid_tracks": [t.model_dump() for t in profile.avoid_tracks],
        "technical_penalties": profile.technical_penalties,
        "jd_excerpt": jd_text[:2400],
    }
    record = _record("role", ROLE_PROMPT_VERSION, inputs)

    def primary() -> dict:
        raw = complete_json_with_retry(
            """Classify the job into exactly one configured target track, an avoid track, or unmatched.
Use responsibilities, not title keywords alone. Return JSON only:
{"track_id":"configured id or null","avoid_track_id":"configured avoid id or null",
"reason":"short reason","evidence":["exact job excerpts"]}. Never invent an id.""",
            json.dumps(inputs, ensure_ascii=False),
            max_attempts=2,
            max_tokens=700,
        )
        tid = raw.get("track_id")
        aid = raw.get("avoid_track_id")
        track = next((t for t in profile.tracks if t.id == tid), None)
        avoid = next((t for t in profile.avoid_tracks if t.id == aid), None)
        if tid is not None and track is None:
            raise ValueError(f"unknown track_id {tid!r}")
        if aid is not None and avoid is None:
            raise ValueError(f"unknown avoid_track_id {aid!r}")
        if (
            track
            and track.id == "ai_eng"
            and _TRADITIONAL_ENGINEERING_TITLE_RE.search(title)
            and not _AI_ROLE_RE.search(f"{title}\n{jd_text}")
        ):
            raise ValueError("AI track contradicts explicit traditional-engineering title and JD content")
        if avoid:
            out = {"track_id": None, "track_label": avoid.label, "track_priority": 4, "track_similarity": None, "role_status": "avoid"}
        elif track:
            out = {"track_id": track.id, "track_label": track.label, "track_priority": track.priority, "track_similarity": None, "role_status": "target"}
        else:
            out = {"track_id": None, "track_label": None, "track_priority": 4, "track_similarity": None, "role_status": "unmatched"}
        priority, hits = apply_technical_penalties(out["track_priority"], jd, jd_text, profile)
        out.update(track_priority=priority, technical_penalty_hits=hits, reason=str(raw.get("reason") or ""))
        raw["_validated"] = out
        return raw

    def fallback() -> dict:
        tm = match_role_content_to_profile(title, jd_text, jd, profile)
        track = tm.get("matched_track")
        # Embeddings must be confident enough to classify a role. The old 0.30
        # matcher threshold is useful for retrieval but too weak for assigning
        # a user's P-tier (e.g. Electrical Engineer -> AI at 0.448).
        if track and float(tm.get("similarity") or 0) < _ROLE_EMBEDDING_MIN:
            track = None
        priority = 4 if tm.get("avoid_match") or not track else track.priority
        priority, hits = apply_technical_penalties(priority, jd, jd_text, profile)
        return {
            "track_id": track.id if track and not tm.get("avoid_match") else None,
            "track_label": tm.get("avoid_label") or (track.label if track else None),
            "track_priority": priority,
            "track_similarity": tm.get("similarity"),
            "technical_penalty_hits": hits,
            "role_status": "avoid" if tm.get("avoid_match") else ("target" if track else "unmatched"),
            "reason": (
                "embedding fallback"
                if track or tm.get("avoid_match")
                else f"embedding similarity below {_ROLE_EMBEDDING_MIN:.2f}; left unmatched"
            ),
            "evidence": [tm.get("evidence_text") or title],
        }

    return _run_with_fallback(record, primary, fallback)


def decide_location(title: str, jd_text: str, jd: JDParse, profile: CandidateProfile, job_location: str | None) -> dict:
    inputs = {
        "job_location": job_location,
        "parsed_location": jd.location,
        "location_preferences": profile.locations.model_dump(),
        "location_requirements": [r.text for r in jd.requirements if r.category == "location"],
        "jd_excerpt": jd_text[:1800],
    }
    record = _record("location", LOCATION_PROMPT_VERSION, inputs)

    def primary() -> dict:
        raw = complete_json_with_retry(
            """Classify location against the user's P1/P2/P3 geography. Fully remote is P1 only
when explicitly 100% remote; hybrid uses its physical location. Account for city/state/metro and
rural rules. Outside configured targets is P4. Return JSON only:
{"tier":1,"reason":"short geographic reason","evidence":["exact location excerpts"]}.""",
            json.dumps(inputs, ensure_ascii=False),
            max_attempts=1,
            max_tokens=550,
        )
        tier = raw.get("tier")
        if not isinstance(tier, int) or not 1 <= tier <= 4:
            raise ValueError(f"invalid location tier {tier!r}")
        reason = str(raw.get("reason") or "AI geographic classification")
        raw["_validated"] = {
            "location_tier": tier,
            "location_score": {1: 1.0, 2: 0.75, 3: 0.5, 4: 0.1}[tier],
            "location_label": f"P{tier} · {reason[:100]}",
        }
        return raw

    def fallback() -> dict:
        signals = evaluate_profile_signals(jd, jd_text, profile, title, job_location)
        return {
            "location_tier": signals.get("location_tier"),
            "location_score": signals.get("location_score"),
            "location_label": signals.get("location_label"),
            "evidence": [job_location or jd.location or "location unavailable"],
        }

    return _run_with_fallback(record, primary, fallback)


def decide_profile_signals(title: str, jd_text: str, jd: JDParse, profile: CandidateProfile) -> dict:
    inputs = {
        "preferences": profile.preferences,
        "dealbreakers": profile.dealbreakers,
        "job_title": title,
        "jd_excerpt": jd_text[:4000],
    }
    record = _record("preferences_dealbreakers", PREFS_PROMPT_VERSION, inputs)

    def validate_hits(raw_hits: Any, configured: list[str]) -> list[str]:
        if not isinstance(raw_hits, list):
            raise ValueError("hits must be arrays")
        lookup = {v.casefold(): v for v in configured}
        return list(dict.fromkeys(lookup[str(v).casefold()] for v in raw_hits if str(v).casefold() in lookup))

    def primary() -> dict:
        raw = complete_json_with_retry(
            """Identify which configured preferences and dealbreakers are clearly supported by
the job text. Return only exact configured strings. A missing fact is not a hit. JSON only:
{"preference_hits":[],"dealbreaker_hits":[],"evidence":["exact job excerpts"]}.""",
            json.dumps(inputs, ensure_ascii=False),
            max_attempts=1,
            max_tokens=700,
        )
        prefs = validate_hits(raw.get("preference_hits"), profile.preferences)
        deals = validate_hits(raw.get("dealbreaker_hits"), profile.dealbreakers)
        raw["_validated"] = {
            "preferences_matched": len(prefs), "preferences_total": len(profile.preferences), "preference_hits": prefs,
            "dealbreakers_matched": len(deals), "dealbreakers_total": len(profile.dealbreakers), "dealbreaker_hits": deals,
        }
        return raw

    def fallback() -> dict:
        signals = evaluate_profile_signals(jd, jd_text, profile, title)
        return {key: signals[key] for key in (
            "preferences_matched", "preferences_total", "preference_hits",
            "dealbreakers_matched", "dealbreakers_total", "dealbreaker_hits",
        )}

    return _run_with_fallback(record, primary, fallback)


def run_independent_decisions(title: str, jd_text: str, jd: JDParse, profile: CandidateProfile, job_location: str | None) -> dict:
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            "role": pool.submit(decide_role, title, jd_text, jd, profile),
            "location": pool.submit(decide_location, title, jd_text, jd, profile, job_location),
            "preferences_dealbreakers": pool.submit(decide_profile_signals, title, jd_text, jd, profile),
        }
        return {name: future.result() for name, future in futures.items()}
