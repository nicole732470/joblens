#!/usr/bin/env python3
"""Smoke-test entity resolution against employers.json."""

from __future__ import annotations

import json
from pathlib import Path

from export_employer_index import meaningful_tokens, normalize, tokenize_raw
from generic_tokens import GENERIC_TOKENS, NOISE_WORDS

BASE = Path(__file__).resolve().parent
INDEX = BASE.parent / "data" / "h1b" / "employers.json"


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


def linkedin_tokens(slug: str, page: str | None) -> set[str]:
    page_tokens = meaningful_tokens(page) if page else []
    slug_tokens = meaningful_tokens(slug.replace("-", " ")) if slug else []
    if page_tokens:
        tokens = set(page_tokens)
        for slug_token in slug_tokens:
            if slug_token in tokens:
                continue
            dominated = any(
                slug_token in page_token
                or page_token in slug_token
                or slug_token.startswith(page_token)
                or page_token.startswith(slug_token)
                for page_token in tokens
            )
            if not dominated:
                tokens.add(slug_token)
        return tokens
    return set(slug_tokens)


def soft_core(text: str) -> str:
    return " ".join(
        t
        for t in strip_noise_tokens(tokenize_raw(text))
        if len(t) >= 2 and t not in GENERIC_TOKENS
    )


def linkedin_soft_core(slug: str, page: str | None) -> str:
    page_core = soft_core(page) if page else ""
    slug_core = soft_core(slug.replace("-", " ")) if slug else ""
    if page_core and (not slug_core or len(page_core) >= len(slug_core)):
        return page_core
    return slug_core


def employer_soft_cores(employer: dict) -> set[str]:
    out: set[str] = set()
    for raw in [employer["name"], *employer.get("names", []), *employer.get("search_keys", [])]:
        core = soft_core(raw)
        if core:
            out.add(core)
    return out


def employer_tokens(employer: dict) -> set[str]:
    out: set[str] = set()
    for raw in [employer["name"], *employer.get("names", []), *employer.get("search_keys", [])]:
        out.update(meaningful_tokens(raw))
    return out


def ambiguity(linked: set[str], token_index: dict[str, set[str]]) -> int:
    feins: set[str] | None = None
    for token in linked:
        hits = token_index.get(token, set())
        if not hits:
            return 10**9
        feins = hits if feins is None else feins & hits
    return len(feins or set())


def resolve(slug: str, page: str | None, employers: list[dict]) -> dict | None:
    linked = linkedin_tokens(slug, page)
    if not linked:
        return None

    token_index: dict[str, set[str]] = {}
    for emp in employers:
        for token in employer_tokens(emp):
            token_index.setdefault(token, set()).add(emp["fein"])

    amb = ambiguity(linked, token_index)
    candidates = []
    for emp in employers:
        dol = employer_tokens(emp)
        shared = linked & dol
        if not shared:
            continue
        subset = linked <= dol
        overlap = len(shared) / len(linked)
        reverse = len(shared) / len(dol) if dol else 0
        soft_li = linkedin_soft_core(slug, page)
        soft_dol = soft_core(emp["name"])
        exact = bool(soft_li and soft_li in employer_soft_cores(emp))
        candidates.append(
            {
                "employer": emp,
                "shared": len(shared),
                "subset": subset,
                "overlap": overlap,
                "reverse": reverse,
                "exact": exact,
                "ambiguity": amb,
            }
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda c: (
            c["exact"],
            c["subset"],
            c["shared"],
            c["overlap"],
            -c["ambiguity"],
            c["employer"]["lca_count"],
        ),
        reverse=True,
    )
    top = candidates[0]
    conf = "medium"
    if top["exact"] and top["ambiguity"] <= 1:
        conf = "high"
    elif top["subset"] and len(linked) >= 2 and top["overlap"] >= 0.8 and top["ambiguity"] <= 2:
        conf = "high"
    elif len(linked) == 1 and top["ambiguity"] > 1:
        conf = "low"
    elif top["overlap"] < 0.5:
        conf = "low"

    return {
        "name": top["employer"]["name"],
        "confidence": conf,
        "shared": top["shared"],
        "ambiguity": top["ambiguity"],
        "overlap": round(top["overlap"], 2),
    }


def main() -> None:
    if not INDEX.exists():
        raise SystemExit(f"Missing {INDEX} — run export_employer_index.py first")

    data = json.loads(INDEX.read_text(encoding="utf-8"))
    employers = data["employers"]

    cases = [
        ("microsoft", "Microsoft", "high"),
        ("eversana", "Eversana", None),
        ("meta", "Meta", None),
        ("coforge", "Coforge", None),
        ("ornua-foods-north-america-inc", "Ornua", None),
        ("tencentglobal", "Tencent", None),
        ("a-hiring-company", "A Hiring Company", None),  # should not match square hiring
        ("ansys", "Ansys", None),
        ("zscaler", "Zscaler", None),
    ]

    print(f"Index v{data.get('version')} · {len(employers):,} employers\n")
    for slug, page, expect_conf in cases:
        hit = resolve(slug, page, employers)
        if hit:
            line = f"{slug:30} -> {hit['name'][:50]:50} conf={hit['confidence']} amb={hit['ambiguity']} ov={hit['overlap']}"
        else:
            line = f"{slug:30} -> NOT FOUND"
        if expect_conf and hit and hit["confidence"] != expect_conf:
            line += f"  (expected {expect_conf})"
        print(line)


if __name__ == "__main__":
    main()
