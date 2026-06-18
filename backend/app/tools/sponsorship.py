"""H-1B sponsorship lookup tool.

`search_h1b_company` resolves a raw company name to a FEIN-keyed employer in the
imported DOL LCA index and returns its historical sponsorship signals with
evidence IDs. This is a first, transparent version of the resolver; the full
evidence-first ranking (ported from extension/lib/matcher.js) comes later.
"""

from __future__ import annotations

from app.db import fetch_all
from app.tools.text_normalize import candidate_keys, is_multiword_key


def _no_match(query: str, reason: str) -> dict:
    return {
        "matched": False,
        "query": query,
        "reason": reason,
        "alias_confidence": None,
        "evidence": [],
        "evidence_ids": [],
    }


def _company_payload(fein: str) -> dict:
    rows = fetch_all(
        """
        SELECT fein, name, naics_code, naics_sector, city, state,
               lca_count, h1b_count, certified_count, top_jobs
        FROM companies WHERE fein = %s
        """,
        (fein,),
    )
    return rows[0] if rows else {}


def _aliases(fein: str) -> list[str]:
    rows = fetch_all(
        "SELECT alias_name FROM company_aliases WHERE fein = %s ORDER BY alias_name",
        (fein,),
    )
    return [r["alias_name"] for r in rows]


def search_h1b_company(company_name: str) -> dict:
    """Find the matched employer entity and its sponsorship history.

    Returns matched company, alias confidence, LCA counts, sponsored titles,
    location, ambiguous alternatives, and evidence IDs for citation.
    """
    name = (company_name or "").strip()
    if not name:
        return _no_match(name, "no company name provided")

    keys = candidate_keys(name)
    matches: list[dict] = []
    if keys:
        matches = fetch_all(
            "SELECT search_key, fein FROM company_search_keys "
            "WHERE search_key = ANY(%s)",
            (keys,),
        )

    # Exact name / alias match (case-insensitive) is the strongest signal.
    exact = fetch_all(
        """
        SELECT fein FROM companies WHERE lower(name) = lower(%s)
        UNION
        SELECT fein FROM company_aliases WHERE lower(alias_name) = lower(%s)
        """,
        (name, name),
    )
    exact_feins = {r["fein"] for r in exact}

    if not matches and not exact_feins:
        return _no_match(name, "no matching employer in H-1B index")

    specific_feins = {m["fein"] for m in matches if is_multiword_key(m["search_key"])}
    token_feins = {m["fein"] for m in matches if not is_multiword_key(m["search_key"])}
    all_feins = exact_feins | specific_feins | token_feins

    # Choose the FEIN bucket by priority, then the highest-volume employer in it.
    if exact_feins:
        pool, confidence = exact_feins, "high"
    elif specific_feins:
        pool = specific_feins
        confidence = "high" if len(all_feins) == 1 else "medium"
    else:
        pool = token_feins
        confidence = "medium" if len(token_feins) == 1 else "low"

    ranked = fetch_all(
        "SELECT fein, name, lca_count FROM companies "
        "WHERE fein = ANY(%s) ORDER BY lca_count DESC",
        (list(pool),),
    )
    primary = ranked[0]
    fein = primary["fein"]

    company = _company_payload(fein)
    aliases = _aliases(fein)
    top_jobs = company.get("top_jobs") or []
    sponsored_titles = [
        {"title": j.get("title"), "count": j.get("count")}
        for j in top_jobs
        if j.get("title")
    ]

    alternatives = [
        {"fein": r["fein"], "name": r["name"], "lca_count": r["lca_count"]}
        for r in fetch_all(
            "SELECT fein, name, lca_count FROM companies "
            "WHERE fein = ANY(%s) AND fein <> %s ORDER BY lca_count DESC LIMIT 5",
            (list(all_feins), fein),
        )
    ]

    matched_keys = sorted({m["search_key"] for m in matches if m["fein"] == fein})

    evidence = [
        {
            "id": f"h1b:{fein}:lca_count",
            "type": "sponsorship_volume",
            "value": company.get("lca_count", 0),
            "detail": f"{company.get('lca_count', 0)} H-1B LCA filings on record",
        },
        {
            "id": f"h1b:{fein}:certified",
            "type": "sponsorship_volume",
            "value": company.get("certified_count", 0),
            "detail": f"{company.get('certified_count', 0)} certified filings",
        },
        {
            "id": f"h1b:{fein}:entity_match",
            "type": "entity_match",
            "value": matched_keys or ["exact_name"],
            "detail": f"Resolved '{name}' to {company.get('name')} "
            f"(confidence: {confidence})",
        },
    ]
    for i, job in enumerate(sponsored_titles[:3]):
        evidence.append(
            {
                "id": f"h1b:{fein}:title:{i}",
                "type": "sponsored_title",
                "value": job,
                "detail": f"{job['count']} filings for '{job['title']}'",
            }
        )

    return {
        "matched": True,
        "query": name,
        "alias_confidence": confidence,
        "company": {
            "fein": fein,
            "name": company.get("name"),
            "naics_code": company.get("naics_code"),
            "naics_sector": company.get("naics_sector"),
            "city": company.get("city"),
            "state": company.get("state"),
        },
        "total_lca_count": company.get("lca_count", 0),
        "h1b_count": company.get("h1b_count", 0),
        "certified_count": company.get("certified_count", 0),
        # Year-by-year recency is not in the aggregated index yet; requires the
        # raw LCA records (a future import). Marked unknown rather than guessed.
        "recent_lca_count": None,
        "sponsored_titles": sponsored_titles,
        "aliases": aliases,
        "ambiguous_alternatives": alternatives,
        "evidence": evidence,
        "evidence_ids": [e["id"] for e in evidence],
    }
