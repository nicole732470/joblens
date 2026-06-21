"""Token normalization primitives for employer entity resolution.

These mirror tokenizeRaw / stripNoiseTokens / meaningfulTokens / coreNormalize
exactly so backend entity resolution behaves identically to the extension.
Token lists are kept in sync with data-pipeline/generic_tokens.py.
"""

from __future__ import annotations

import re

# NOISE_WORDS = LEGAL_SUFFIXES ∪ WEAK_CORPORATE_WORDS
LEGAL_SUFFIXES = frozenset(
    {
        "inc", "incorporated", "llc", "ltd", "limited", "corporation", "corp",
        "company", "co", "llp", "lp", "plc",
    }
)
WEAK_CORPORATE_WORDS = frozenset(
    {
        "group", "holdings", "services", "solutions", "systems", "technologies",
        "international", "usa", "us", "america",
    }
)
NOISE_WORDS = LEGAL_SUFFIXES | WEAK_CORPORATE_WORDS

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
    text = str(text).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^\w\s-]", " ", text)
    text = text.replace("-", " ")
    return [t for t in re.split(r"\s+", text) if t]


def strip_noise_tokens(tokens: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i] == "north" and i + 1 < len(tokens) and tokens[i + 1] == "america":
            i += 1
            i += 1
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


def core_normalize(text: str) -> str:
    return " ".join(meaningful_tokens(text))


# Alias kept for resolver readability.
normalize = core_normalize


def slugify_raw(text: str) -> str:
    """Hyphenated slug from a raw name (keeps generic words). Used to synthesize
    a LinkedIn-style slug from a plain company name on the backend."""
    text = str(text).lower().strip()
    text = text.replace("&", " and ")
    text = re.sub(r"[^\w\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+", "-", text)


def short_label(text: str, max_len: int = 48) -> str:
    if not text:
        return ""
    one = re.sub(r"\s+", " ", str(text)).strip()
    if len(one) <= max_len:
        return one
    return re.sub(r"\s+\S*$", "", one[:max_len]).strip() + "\u2026"
