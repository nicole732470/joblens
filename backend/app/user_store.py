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
    if not data.get("trajectory") and base_data.get("trajectory"):
        data["trajectory"] = base_data["trajectory"]
    if not data.get("technical_penalties") and base_data.get("technical_penalties"):
        data["technical_penalties"] = base_data["technical_penalties"]
    if not data.get("alumni_schools") and base_data.get("alumni_schools"):
        data["alumni_schools"] = base_data["alumni_schools"]
    if loc.get("relocation_ok") is None and base_loc.get("relocation_ok") is not None:
        loc["relocation_ok"] = base_loc["relocation_ok"]
    return CandidateProfile.model_validate(data)


def is_owner_email(email: str | None) -> bool:
    if not email or not settings.owner_email:
        return False
    return email.strip().lower() == settings.owner_email.strip().lower()


def sync_user_from_golden_defaults(user_id: uuid.UUID) -> dict:
    """Overwrite user profile + primary resume from repo golden set (extension parity)."""
    profile = _yaml_default_profile()
    if profile is None:
        raise FileNotFoundError("golden candidate_profile.yaml not found")
    save_user_profile(user_id, profile)

    from app.tools.resume_loader import load_default_resume
    from app.tools.resume_store import index_resume

    resume_text = load_default_resume()
    rid = save_user_resume(user_id, "resume.md", resume_text)
    indexed = index_resume(resume_text, resume_key=f"user_{user_id}", force=True)
    return {
        "profile": "synced",
        "resume_id": str(rid),
        "resume_chars": len(resume_text),
        "resume_indexed": indexed.get("indexed", False),
    }


def sync_owner_from_golden(email: str | None = None) -> dict:
    """Sync owner account by email (CLI / login hook)."""
    target = (email or settings.owner_email or "").strip().lower()
    if not target:
        raise ValueError("owner email not configured")
    from app.auth import fetch_user_by_email

    row = fetch_user_by_email(target)
    if not row:
        raise ValueError(f"no user registered for {target}")
    out = sync_user_from_golden_defaults(row["id"])
    out["email"] = target
    out["user_id"] = str(row["id"])
    return out


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
