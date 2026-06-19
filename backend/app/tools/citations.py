"""Citation enforcement — the engineering backbone of "evidence over keywords".

Every interpretive Claim must reference evidence IDs that actually exist in the
retrieved context. This validator runs over generated claims before a report is
returned; claims that violate the contract are flagged (and, once the LLM stage
exists, rejected/regenerated).
"""

from __future__ import annotations

from app.schemas.report import Claim


def claim_evidence_ids(claim: Claim) -> list[str]:
    return [*claim.jd_evidence_ids, *claim.resume_evidence_ids, *claim.h1b_evidence_ids]


def validate_claims(claims: list[Claim], available_evidence_ids: set[str]) -> list[dict]:
    """Return a list of contract violations. Empty list == all claims valid.

    Rules (see docs/REPORT_SCHEMA.md):
      1. A non-inference claim must cite at least one evidence ID.
      2. Every cited evidence ID must exist in the retrieved context.
    """
    issues: list[dict] = []
    for claim in claims:
        ids = claim_evidence_ids(claim)
        if claim.claim_type == "recommendation" and claim.h1b_evidence_ids:
            issues.append(
                {
                    "claim": claim.claim,
                    "claim_type": claim.claim_type,
                    "issue": "h1b_in_recommendation",
                    "detail": "recommendation claims must not cite H-1B database evidence",
                }
            )
        if not ids and not claim.inference:
            issues.append(
                {
                    "claim": claim.claim,
                    "claim_type": claim.claim_type,
                    "issue": "no_evidence",
                    "detail": "claim cites no evidence and is not marked as inference",
                }
            )
        for eid in ids:
            if eid not in available_evidence_ids:
                issues.append(
                    {
                        "claim": claim.claim,
                        "claim_type": claim.claim_type,
                        "issue": "unknown_evidence_id",
                        "detail": f"evidence id not in retrieved context: {eid}",
                    }
                )
    return issues
