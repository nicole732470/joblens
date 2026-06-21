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


def test_vector_fallback_uses_four_similarity_bands(monkeypatch):
    requirements = [
        JDRequirement(id=f"jd_req_{i}", category="required_skill", text=f"Skill {i}")
        for i in range(4)
    ]
    jd = JDParse(available=True, requirements=requirements)
    distances = iter([0.20, 0.40, 0.60, 0.61])

    def fake_retrieve(query, resume_key, limit=1):
        distance = next(distances)
        return [{"id": f"chunk_{distance}", "section": "Skills", "content": query, "distance": distance}]

    monkeypatch.setattr("app.tools.resume_fit.retrieve_resume_evidence", fake_retrieve)
    out = _analyze_with_vector(jd, "resume_test")
    assert len(out["strong_matches"]) == 1
    assert len(out["partial_matches"]) == 1
    assert len(out["missing"]) == 2
    assert out["missing"][0]["claim"].startswith("[weak]")
    assert out["missing"][0]["resume_evidence_ids"]
    assert out["missing"][1]["claim"].startswith("[missing]")
    assert out["missing"][1]["resume_evidence_ids"] == []
