"""Per-user profile and resume persistence."""

from __future__ import annotations

import json
import uuid

import psycopg

from app.config import settings
from app.db import fetch_all, fetch_one
from app.schemas.candidate_profile import CandidateProfile


def get_user_profile(user_id: uuid.UUID) -> CandidateProfile | None:
    row = fetch_one("SELECT profile FROM user_profiles WHERE user_id = %s", (user_id,))
    if not row or not row.get("profile"):
        return CandidateProfile()
    data = row["profile"]
    if isinstance(data, str):
        data = json.loads(data)
    return CandidateProfile.model_validate(data)


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
