"""JWT auth helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.db import fetch_all, fetch_one

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(user_id: uuid.UUID, email: str) -> str:
    exp = datetime.now(UTC) + timedelta(days=settings.jwt_expire_days)
    return jwt.encode(
        {"sub": str(user_id), "email": email, "exp": exp},
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail="invalid token") from e


def get_current_user_id(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> uuid.UUID | None:
    if not creds or creds.scheme.lower() != "bearer":
        return None
    payload = decode_token(creds.credentials)
    return uuid.UUID(payload["sub"])


def require_user_id(user_id: uuid.UUID | None = Depends(get_current_user_id)) -> uuid.UUID:
    if user_id is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return user_id


def ensure_auth_schema() -> None:
    from pathlib import Path

    import psycopg

    sql_path = Path(__file__).resolve().parents[2] / "db" / "auth_schema.sql"
    with psycopg.connect(settings.database_url) as conn:
        conn.execute(sql_path.read_text(encoding="utf-8"))
        conn.commit()


def fetch_user_by_email(email: str) -> dict | None:
    rows = fetch_all("SELECT id, email, password_hash FROM users WHERE email = %s", (email.lower(),))
    return rows[0] if rows else None


def create_user(email: str, password: str) -> uuid.UUID:
    ensure_auth_schema()
    import psycopg

    uid = uuid.uuid4()
    with psycopg.connect(settings.database_url) as conn:
        conn.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (%s, %s, %s)",
            (uid, email.lower(), hash_password(password)),
        )
        conn.execute(
            "INSERT INTO user_profiles (user_id, profile) VALUES (%s, %s::jsonb)",
            (uid, "{}"),
        )
        conn.commit()
    return uid
