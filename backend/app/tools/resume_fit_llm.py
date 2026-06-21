"""LLM classification of resume evidence vs JD requirements (after RAG retrieval)."""

from __future__ import annotations

from app.schemas.report import JDParse
from app.tools.llm import complete_json_with_retry, llm_available
from app.tools.resume_store import retrieve_resume_evidence

_SYSTEM = (
    "You are a precise resume–job-fit analyst. For each job requirement, read the "
    "retrieved resume snippets and judge fit.\n"
    "- strong: resume clearly demonstrates this requirement\n"
    "- partial: related experience but incomplete or indirect\n"
    "- weak: only weakly related evidence exists\n"
    "- missing: no meaningful evidence in the snippets\n"
    "Be conservative with strong. Cite the best resume_chunk id when not missing. "
    "Respond with JSON only."
)

_BATCH_SIZE = 8
_RETRIEVE_LIMIT = 3


def _format_batch_prompt(batch: list[dict]) -> str:
    lines = ["Classify each requirement against the resume evidence.\n"]
    lines.append(
        'Return JSON: {"matches":[{"requirement_id":"...","level":"strong|partial|weak|missing",'
        '"reasoning":"one sentence","resume_evidence_id":"chunk id or null"}]}\n'
    )
    for item in batch:
        lines.append(f"\n### {item['req_id']}")
        lines.append(f"Requirement: {item['text']}")
        if item.get("quote"):
            lines.append(f"JD quote: {item['quote']}")
        if not item["candidates"]:
            lines.append("Resume evidence: (none retrieved)")
        else:
            lines.append("Resume evidence:")
            for c in item["candidates"]:
                snippet = c["content"][:320].replace("\n", " ")
                lines.append(
                    f"  - id={c['id']} section={c['section']} distance={c['distance']:.3f} "
                    f"text=\"{snippet}\""
                )
    return "\n".join(lines)


def _parse_llm_matches(data: dict, batch: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in data.get("matches") or []:
        if not isinstance(row, dict):
            continue
        rid = str(row.get("requirement_id") or "").strip()
        level = str(row.get("level") or "").strip().lower()
        if level not in ("strong", "partial", "weak", "missing"):
            continue
        out[rid] = {
            "level": level,
            "reasoning": str(row.get("reasoning") or "").strip(),
            "resume_evidence_id": row.get("resume_evidence_id"),
        }
    # Default missing for reqs the model skipped
    for item in batch:
        rid = item["req_id"]
        if rid not in out:
            out[rid] = {
                "level": "missing",
                "reasoning": "LLM did not classify this requirement.",
                "resume_evidence_id": None,
            }
    return out


def classify_requirements_llm(
    jd: JDParse,
    resume_key: str,
) -> dict[str, dict]:
    """Return req_id → {level, reasoning, resume_evidence_id, candidates}."""
    if not llm_available():
        raise RuntimeError("LLM not configured")

    items: list[dict] = []
    for req in jd.requirements:
        query = req.text
        if req.evidence_quote:
            query = f"{req.text}. {req.evidence_quote}"
        candidates = retrieve_resume_evidence(query, resume_key, limit=_RETRIEVE_LIMIT)
        items.append(
            {
                "req_id": req.id,
                "text": req.text,
                "quote": req.evidence_quote or "",
                "candidates": candidates,
                "req": req,
            }
        )

    classified: dict[str, dict] = {}
    for i in range(0, len(items), _BATCH_SIZE):
        batch = items[i : i + _BATCH_SIZE]
        data = complete_json_with_retry(
            _SYSTEM,
            _format_batch_prompt(batch),
            max_attempts=2,
            max_tokens=2500,
        )
        batch_results = _parse_llm_matches(data, batch)
        for item in batch:
            rid = item["req_id"]
            meta = batch_results[rid]
            meta["candidates"] = item["candidates"]
            meta["req"] = item["req"]
            classified[rid] = meta
    return classified
