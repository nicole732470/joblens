"""H-1B sponsorship lookup tool.

`search_h1b_company` resolves a raw company name to a FEIN-keyed employer using
the evidence-first server resolver and
returns its historical sponsorship signals — preserving the extension's
confidence, warnings, notes, and alternatives — plus evidence IDs for the
platform's citation contract.
"""

from __future__ import annotations

from app.tools.entity_resolver import get_resolver


def _no_match(query: str, reason: str) -> dict:
    return {
        "matched": False,
        "query": query,
        "reason": reason,
        "match_confidence": None,
        "evidence": [],
        "evidence_ids": [],
    }


def _sponsored_titles(employer: dict) -> list[dict]:
    return [
        {"title": j.get("title"), "count": j.get("count")}
        for j in (employer.get("top_jobs") or [])
        if j.get("title")
    ]


def _build_evidence(employer: dict, confidence: str, query: str, matched_on: str) -> list[dict]:
    fein = employer["fein"]
    evidence = [
        {
            "id": f"h1b:{fein}:lca_count",
            "type": "sponsorship_volume",
            "value": employer.get("lca_count", 0),
            "detail": f"{employer.get('lca_count', 0)} H-1B LCA filings on record",
        },
        {
            "id": f"h1b:{fein}:certified",
            "type": "sponsorship_volume",
            "value": employer.get("certified_count", 0),
            "detail": f"{employer.get('certified_count', 0)} certified filings",
        },
        {
            "id": f"h1b:{fein}:entity_match",
            "type": "entity_match",
            "value": matched_on,
            "detail": f"Resolved '{query}' to {employer.get('name')} "
            f"(match confidence: {confidence}, matched on: {matched_on})",
        },
    ]
    for i, job in enumerate(_sponsored_titles(employer)[:3]):
        evidence.append(
            {
                "id": f"h1b:{fein}:title:{i}",
                "type": "sponsored_title",
                "value": job,
                "detail": f"{job['count']} filings for '{job['title']}'",
            }
        )
    return evidence


def search_h1b_company(company_name: str) -> dict:
    """Find the matched employer entity and its sponsorship history.

    Returns matched company, entity-resolution confidence (high/medium/low,
    NOT sponsorship probability), LCA counts, sponsored titles, aliases,
    warnings/notes, ambiguous alternatives, and evidence IDs.
    """
    name = (company_name or "").strip()
    if not name:
        return _no_match(name, "no company name provided")

    result = get_resolver().resolve_company(name)
    if not result:
        return _no_match(name, "no reliable match in H-1B index")

    employer = result["employer"]
    confidence = result["confidence"]
    evidence = _build_evidence(employer, confidence, name, result["matched_on"])

    alternatives = [
        {
            "fein": alt["employer"]["fein"],
            "name": alt["employer"]["name"],
            "lca_count": alt["employer"].get("lca_count", 0),
            "confidence": alt["confidence"],
        }
        for alt in result.get("alternatives", [])
    ]

    return {
        "matched": True,
        "query": name,
        # Entity-resolution confidence, not sponsorship
        # probability. Drives how much to trust the company match itself.
        "match_confidence": confidence,
        "method": result["method"],
        "matched_on": result["matched_on"],
        "company": {
            "fein": employer["fein"],
            "name": employer.get("name"),
            "naics_code": employer.get("naics_code"),
            "naics_sector": employer.get("naics_sector"),
            "city": employer.get("city"),
            "state": employer.get("state"),
        },
        "total_lca_count": employer.get("lca_count", 0),
        "h1b_count": employer.get("h1b_count", 0),
        "certified_count": employer.get("certified_count", 0),
        # Year-by-year recency needs the raw LCA records (a future import).
        "recent_lca_count": None,
        "sponsored_titles": _sponsored_titles(employer),
        "aliases": employer.get("names", []),
        "warnings": result.get("warnings", []),
        "notes": result.get("notes", []),
        "ambiguous_alternatives": alternatives,
        "evidence": evidence,
        "evidence_ids": [e["id"] for e in evidence],
    }
