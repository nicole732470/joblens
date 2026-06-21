"""P4+ track → Skip recommendation."""

from app.schemas.candidate_profile import CandidateProfile, Constraints, Track
from app.schemas.report import Claim, JDParse, Recommendation, ResumeFitAnalysis
from app.tools.recommendation import _generate_recommendation_rules as generate_recommendation


def _profile() -> CandidateProfile:
    return CandidateProfile(
        tracks=[
            Track(
                id="research_eng",
                label="Research Engineer",
                priority=3,
                example_titles=["Applied Research Engineer", "Research Engineer"],
            ),
            Track(
                id="business_analyst",
                label="Analyst role",
                priority=3,
                example_titles=["Business Analyst", "Technical Business Analyst"],
            ),
        ],
        avoid_tracks=[],
        technical_penalties=["HPC hardware", "Slurm", "GPU hardware"],
        constraints=Constraints(),
    )


def _resume_fit_partial() -> ResumeFitAnalysis:
    return ResumeFitAnalysis(
        available=True,
        strong_matches=[Claim(claim="python", claim_type="resume_fit")],
        partial_matches=[Claim(claim="linux", claim_type="resume_fit")],
        missing=[Claim(claim="gap1", claim_type="resume_fit")] * 3,
    )


def test_research_p3_is_not_system_p4():
    jd = JDParse(available=True, requirements=[])
    out = generate_recommendation(
        jd,
        _resume_fit_partial(),
        _profile(),
        "Applied Research Engineer",
        "Research engineering team alongside research scientists.",
    )
    assert out.get("track_priority") == 3


def test_hpc_analyst_penalty_p4_skips():
    jd = JDParse(available=True, requirements=[])
    jd_text = (
        "Technical Business Analyst for HPC platforms. Slurm scheduler, "
        "InfiniBand, GPU hardware, parallel storage."
    )
    out = generate_recommendation(
        jd,
        _resume_fit_partial(),
        _profile(),
        "Technical Business Analyst (HPC, Linux)",
        jd_text,
    )
    assert out["decision"] == Recommendation.SKIP
    assert out.get("track_priority") == 4
