"""Company-name normalization, ported from the offline pipeline.

Source of truth for the algorithm: data-pipeline/generic_tokens.py and the
normalization helpers in data-pipeline/export_employer_index.py (which mirror
extension/lib/matcher.js). Kept in sync manually for now; both sides must agree
so backend lookups hit the keys the pipeline indexed.
"""

from __future__ import annotations

import re

NOISE_WORDS = frozenset(
    {
        "inc", "incorporated", "llc", "ltd", "limited", "corporation", "corp",
        "company", "co", "group", "holdings", "services", "solutions",
        "technologies", "systems", "international", "usa", "us", "america",
        "llp", "lp", "plc",
    }
)

GENERIC_TOKENS = frozenset(
    {
        "american", "global", "international", "group", "services", "service",
        "solutions", "technology", "technologies", "systems", "management",
        "consulting", "partners", "partner", "capital", "holdings", "labs",
        "health", "care", "university", "hiring", "staffing", "industries",
        "industry", "enterprises", "enterprise", "associates", "resources",
        "digital", "software", "companies", "gamma", "united", "national",
        "advanced", "north", "south", "east", "west", "central", "community",
        "first", "general", "professional", "business", "world", "city",
        "state", "pacific", "atlantic", "prime", "blue", "green", "red", "new",
        "best", "all", "one",
    }
)


def tokenize_raw(text: str) -> list[str]:
    text = text.lower().strip()
    text = text.replace("&", " and ")
    text = re.sub(r"[^\w\s-]", " ", text)
    text = text.replace("-", " ")
    return [t for t in re.sub(r"\s+", " ", text).strip().split() if t]


def strip_noise_tokens(tokens: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i] == "north" and i + 1 < len(tokens) and tokens[i + 1] == "america":
            i += 2
            continue
        if tokens[i] not in NOISE_WORDS:
            out.append(tokens[i])
        i += 1
    return out


def meaningful_tokens(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for token in strip_noise_tokens(tokenize_raw(text)):
        if len(token) < 3 or token in GENERIC_TOKENS or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def normalize(text: str) -> str:
    return " ".join(meaningful_tokens(text))


def slugify(text: str) -> str:
    return re.sub(r"\s+", "-", normalize(text))


def slugify_raw(text: str) -> str:
    """Hyphenated slug from display name before legal-suffix stripping."""
    text = text.lower().strip()
    text = text.replace("&", " and ")
    text = re.sub(r"[^\w\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+", "-", text)


def brand_tokens_from_raw(raw: str) -> set[str]:
    """Candidate short brand tokens (ornua, coforge) from a legal name."""
    found: set[str] = set()
    parts = [p for p in slugify_raw(raw).split("-") if p]
    if len(parts) >= 2:
        lead = parts[0]
        if len(lead) >= 4 and lead not in GENERIC_TOKENS:
            found.add(lead)
    norm = normalize(raw)
    if not norm or len(norm) < 4:
        return found
    n_parts = norm.split()
    if n_parts[0] not in GENERIC_TOKENS and len(n_parts[0]) >= 4:
        if len(n_parts) >= 2 or len(n_parts[0]) >= 5:
            found.add(n_parts[0])
    return found


def candidate_keys(name: str) -> list[str]:
    """Lookup keys to probe against company_search_keys for a raw company name.

    Mirrors the key shapes produced by the pipeline's search_keys_for():
    raw hyphen slug, normalized (space + hyphen), and short brand tokens.
    """
    keys: set[str] = set()
    raw_slug = slugify_raw(name)
    if raw_slug:
        keys.add(raw_slug)
    norm = normalize(name)
    if norm:
        keys.add(norm)
        keys.add(slugify(name))
    keys.update(brand_tokens_from_raw(name))
    toks = meaningful_tokens(name)
    if len(toks) == 1:
        keys.add(toks[0])
    return [k for k in keys if k]


def is_multiword_key(key: str) -> bool:
    return "-" in key or " " in key
