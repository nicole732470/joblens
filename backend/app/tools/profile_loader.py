"""Load candidate_profile.yaml into a validated CandidateProfile."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from app.config import settings
from app.schemas.candidate_profile import CandidateProfile

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _resolve_profile_path() -> Path:
    raw = Path(settings.candidate_profile_path)
    if raw.is_absolute():
        return raw
    # CWD first (Docker WORKDIR=/app); fall back to monorepo root for local runs.
    for base in (Path.cwd(), _REPO_ROOT):
        candidate = base / raw
        if candidate.is_file():
            return candidate
    return Path.cwd() / raw


def load_candidate_profile(path: Path | None = None) -> CandidateProfile:
    """Parse and validate the YAML profile. Raises if the file is missing."""
    profile_path = path or _resolve_profile_path()
    if not profile_path.is_file():
        raise FileNotFoundError(f"candidate profile not found: {profile_path}")

    with profile_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return CandidateProfile.model_validate(data)


@lru_cache(maxsize=1)
def get_candidate_profile() -> CandidateProfile:
    """Cached profile for request handlers (reload server to pick up edits)."""
    return load_candidate_profile()
