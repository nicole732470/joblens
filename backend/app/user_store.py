"""Per-user profile and resume persistence."""

from __future__ import annotations

import json
import uuid

import psycopg

from app.config import settings
from app.db import fetch_all, fetch_one
from app.schemas.candidate_profile import CandidateProfile
from app.tools.profile_loader import load_candidate_profile


def _yaml_default_profile() -> CandidateProfile | None:
    try:
        return load_candidate_profile()
    except FileNotFoundError:
        return None


def _profile_needs_yaml_defaults(profile: CandidateProfile) -> bool:
    if not profile.tracks:
        return True
    loc = profile.locations
    if not loc.tier_1 and not loc.tier_2 and not (loc.summary or "").strip():
        return True
    return False


def merge_profile_with_yaml_defaults(profile: CandidateProfile) -> CandidateProfile:
    """Fill empty lists from repo YAML so web matches extension defaults."""
    base = _yaml_default_profile()
    if base is None:
        return profile
    data = profile.model_dump()
    base_data = base.model_dump()
    if not data.get("tracks"):
        data["tracks"] = base_data.get("tracks") or []
    if not data.get("avoid_tracks") and base_data.get("avoid_tracks"):
        data["avoid_tracks"] = base_data["avoid_tracks"]
    loc = data.setdefault("locations", {})
    base_loc = base_data.get("locations") or {}
    if not loc.get("tier_1") and base_loc.get("tier_1"):
        loc["tier_1"] = base_loc["tier_1"]
    if not loc.get("tier_2") and base_loc.get("tier_2"):
        loc["tier_2"] = base_loc["tier_2"]
    if not loc.get("tier_3") and base_loc.get("tier_3"):
        loc["tier_3"] = base_loc["tier_3"]
    if not (loc.get("summary") or "").strip() and (base_loc.get("summary") or "").strip():
        loc["summary"] = base_loc["summary"]
    if loc.get("remote_ok") is None and base_loc.get("remote_ok") is not None:
        loc["remote_ok"] = base_loc["remote_ok"]
    if not data.get("preferences") and base_data.get("preferences"):
        data["preferences"] = base_data["preferences"]
    if not data.get("dealbreakers") and base_data.get("dealbreakers"):
        data["dealbreakers"] = base_data["dealbreakers"]
    if not data.get("constraints") and base_data.get("constraints"):
        data["constraints"] = base_data["constraints"]
    return CandidateProfile.model_validate(data)


def get_user_profile(user_id: uuid.UUID) -> CandidateProfile:
    row = fetch_one("SELECT profile FROM user_profiles WHERE user_id = %s", (user_id,))
    if not row or not row.get("profile"):
        base = _yaml_default_profile()
        return base if base is not None else CandidateProfile()
    data = row["profile"]
    if isinstance(data, str):
        data = json.loads(data)
    profile = CandidateProfile.model_validate(data)
    return merge_profile_with_yaml_defaults(profile)


def save_user_profile(user_id: uuid.UUID, profile: CandidateProfile) -> None:
    payload = profile.model_dump()
    with psycopg.connect(settings.database_url) as conn:
        conn.execute(
            """
            INSERT INTO user_profiles (user_id, profile, updated_at)
            VALUES (%s, %s::jsonb, now())
            ON CONFLICT (user_id) DO UPDATE SET
                profile = EXCLUDED.profile,
                updated_at = now()
            """,
            (user_id, json.dumps(payload)),
        )
        conn.commit()


def save_user_resume(user_id: uuid.UUID, filename: str, text: str) -> uuid.UUID:
    rid = uuid.uuid4()
    with psycopg.connect(settings.database_url) as conn:
        conn.execute(
            "UPDATE user_resumes SET is_primary = false WHERE user_id = %s",
            (user_id,),
        )
        conn.execute(
            """
            INSERT INTO user_resumes (id, user_id, filename, extracted_text, is_primary)
            VALUES (%s, %s, %s, %s, true)
            """,
            (rid, user_id, filename, text),
        )
        conn.commit()
    return rid


def get_primary_resume_text(user_id: uuid.UUID) -> str | None:
    row = fetch_one(
        """
        SELECT extracted_text FROM user_resumes
        WHERE user_id = %s AND is_primary = true
        ORDER BY created_at DESC LIMIT 1
        """,
        (user_id,),
    )
    return row["extracted_text"] if row else None
