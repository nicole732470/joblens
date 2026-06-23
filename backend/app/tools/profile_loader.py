"""Request-scoped candidate profile (YAML default or logged-in user)."""

from __future__ import annotations

from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

import yaml

from app.config import settings
from app.schemas.candidate_profile import CandidateProfile, CandidateProfileDocument

_REPO_ROOT = Path(__file__).resolve().parents[3]
_profile_override: ContextVar[CandidateProfile | None] = ContextVar("profile_override", default=None)


def _resolve_profile_path() -> Path:
    raw = Path(settings.candidate_profile_path)
    if raw.is_absolute():
        return raw
    for base in (Path.cwd(), _REPO_ROOT):
        candidate = base / raw
        if candidate.is_file():
            return candidate
    return Path.cwd() / raw


def load_candidate_profile_document(path: Path | None = None) -> CandidateProfileDocument:
    profile_path = path or _resolve_profile_path()
    if not profile_path.is_file():
        raise FileNotFoundError(f"candidate profile not found: {profile_path}")
    with profile_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return CandidateProfileDocument.model_validate(data)


def load_candidate_profile(path: Path | None = None) -> CandidateProfile:
    """Load only the public/user-facing portion of the owner YAML."""
    return load_candidate_profile_document(path).public_profile()


@lru_cache(maxsize=1)
def _cached_yaml_profile() -> CandidateProfile:
    return load_candidate_profile()


def set_request_profile(profile: CandidateProfile | None) -> None:
    _profile_override.set(profile)


def get_candidate_profile() -> CandidateProfile:
    override = _profile_override.get()
    if override is not None:
        return override
    return _cached_yaml_profile()
