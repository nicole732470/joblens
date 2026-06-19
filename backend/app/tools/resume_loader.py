"""Load default resume text for dev/eval (single-user MVP default)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.config import settings

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _resolve_resume_path() -> Path:
    raw = Path(settings.default_resume_path)
    if raw.is_absolute():
        return raw
    for base in (Path.cwd(), _REPO_ROOT):
        candidate = base / raw
        if candidate.is_file():
            return candidate
    return Path.cwd() / raw


def load_default_resume() -> str:
    """Return resume body text. Raises FileNotFoundError if missing."""
    path = _resolve_resume_path()
    if not path.is_file():
        raise FileNotFoundError(f"default resume not found: {path}")
    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=1)
def get_default_resume() -> str:
    return load_default_resume()


def resolve_resume_text(uploaded: str | None) -> tuple[str | None, str]:
    """Pick uploaded resume or fall back to the dev default file.

    Returns (text_or_none, source) where source is 'upload' | 'default' | 'none'.
    """
    if uploaded and uploaded.strip():
        return uploaded.strip(), "upload"
    try:
        return get_default_resume(), "default"
    except FileNotFoundError:
        return None, "none"
