"""Tests for resume fit orchestration (vector path — no API key required)."""

from app.schemas.report import JDParse, JDRequirement
from app.tools.resume_fit import _analyze_with_vector


def test_vector_classifies_by_distance(monkeypatch):
    jd = JDParse(
        available=True,
        requirements=[
            JDRequirement(
                id="jd_req_01",
                category="required_skill",
                text="Python",
                evidence_quote="Python required",
            )
        ],
    )

    def fake_retrieve(query, resume_key, limit=1):
        return [
            {
                "id": "chunk_1",
                "section": "Experience",
                "content": "Built APIs in Python",
                "distance": 0.20,
            }
        ]

    monkeypatch.setattr("app.tools.resume_fit.retrieve_resume_evidence", fake_retrieve)
    out = _analyze_with_vector(jd, "resume_test")
    assert out["match_method"] == "vector"
    assert len(out["strong_matches"]) == 1
    assert out["strong_matches"][0]["resume_evidence_ids"] == ["chunk_1"]
