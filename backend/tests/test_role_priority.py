"""Offline tests for Role P-tier logic (no API / embeddings required)."""

from __future__ import annotations

import unittest

from app.schemas.candidate_profile import Track
from app.schemas.report import JDParse, ResumeFitAnalysis, Claim
from app.tools.role_priority import (
    _strict_phrase_hit,
    apply_jd_role_adjustments,
    apply_resume_priority_adjustment,
    apply_technical_penalties,
)
from app.tools.track_match import _exact_track_match, _keyword_track_from_title, _title_matches_example


def _minimal_profile(tracks: list[Track], penalties: list[str] | None = None):
    from app.schemas.candidate_profile import CandidateProfile, Constraints

    return CandidateProfile(
        tracks=tracks,
        avoid_tracks=[],
        technical_penalties=penalties or [],
        constraints=Constraints(),
    )


class StrictPhraseHitTests(unittest.TestCase):
    def test_mechanical_engineering_needs_both_tokens(self) -> None:
        blob = "software engineering team building apis"
        self.assertFalse(_strict_phrase_hit("mechanical engineering", blob))
        self.assertTrue(_strict_phrase_hit("mechanical engineering", "mechanical engineering degree"))

    def test_gpu_hardware_needs_both(self) -> None:
        blob = "cpu and gpu hardware optimization"
        self.assertTrue(_strict_phrase_hit("GPU hardware", blob))
        self.assertFalse(_strict_phrase_hit("GPU hardware", "general hardware knowledge"))


class TitleKeywordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = _minimal_profile(
            [
                Track(id="customer_success", label="CSM", priority=3, example_titles=["CSM"]),
                Track(id="research_eng", label="Research", priority=3, example_titles=[]),
                Track(id="business_analyst", label="Analyst", priority=3, example_titles=[]),
            ]
        )

    def test_csm_title(self) -> None:
        tr = _keyword_track_from_title("Technical Customer Success Manager", self.profile)
        self.assertIsNotNone(tr)
        assert tr is not None
        self.assertEqual(tr.id, "customer_success")

    def test_research_engineer_title(self) -> None:
        tr = _keyword_track_from_title("Applied Research Engineer", self.profile)
        self.assertIsNotNone(tr)
        assert tr is not None
        self.assertEqual(tr.id, "research_eng")


class SolutionEngineerTitleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = _minimal_profile(
            [
                Track(
                    id="pm_eng",
                    label="product roles",
                    priority=1,
                    example_titles=["Solution Engineer", "Product Engineer"],
                ),
                Track(id="research_eng", label="Research", priority=3, example_titles=["Research Engineer"]),
                Track(id="ai_eng", label="AI Engineer", priority=1, example_titles=["AI Engineer"]),
            ]
        )

    def test_intern_title_matches_solution_engineer_example(self) -> None:
        self.assertTrue(_title_matches_example("Solution Engineering Intern", "Solution Engineer"))
        tr, sim = _exact_track_match("Solution Engineering Intern", self.profile)
        self.assertIsNotNone(tr)
        assert tr is not None
        self.assertEqual(tr.id, "pm_eng")
        self.assertEqual(sim, 1.0)

    def test_keyword_solution_engineering_intern(self) -> None:
        tr = _keyword_track_from_title("Solution Engineering Intern", self.profile)
        self.assertIsNotNone(tr)
        assert tr is not None
        self.assertEqual(tr.id, "pm_eng")

    def test_research_jd_does_not_flip_solution_intern_to_research(self) -> None:
        pm = self.profile.tracks[0]
        jd = JDParse(available=True, requirements=[])
        blob = (
            "Build prototypes with customers. Collaborate with research on ML models. "
            "Exposure to research papers."
        )
        track, priority, reasons = apply_jd_role_adjustments(
            pm, "Solution Engineering Intern", jd, blob, self.profile
        )
        self.assertEqual(track.id, "pm_eng")
        self.assertEqual(priority, 1)
        self.assertEqual(reasons, [])


class TechnicalPenaltyTests(unittest.TestCase):
    def test_penalty_skipped_for_p4_plus(self) -> None:
        profile = _minimal_profile([], penalties=["GPU hardware"])
        jd = JDParse(available=False)
        pri, hits = apply_technical_penalties(4, jd, "GPU hardware cluster admin", profile)
        self.assertEqual(pri, 4)
        self.assertEqual(hits, [])

    def test_penalty_p3_analyst_bumps_to_p4(self) -> None:
        profile = _minimal_profile([], penalties=["HPC hardware", "Slurm"])
        jd = JDParse(available=False)
        pri, hits = apply_technical_penalties(3, jd, "HPC hardware and Slurm scheduler", profile)
        self.assertEqual(pri, 4)
        self.assertTrue(hits)

    def test_penalty_applies_for_p1_with_hpc(self) -> None:
        profile = _minimal_profile([], penalties=["HPC hardware"])
        jd = JDParse(available=False)
        pri, hits = apply_technical_penalties(1, jd, "HPC hardware and GPU cluster", profile)
        self.assertEqual(pri, 2)
        self.assertTrue(hits)


class ResumePriorityTests(unittest.TestCase):
    def test_bump_when_low_overlap_on_p1(self) -> None:
        rf = ResumeFitAnalysis(
            available=True,
            strong_matches=[],
            partial_matches=[],
            missing=[Claim(claim="x", claim_type="resume_fit")] * 4,
        )
        pri, reasons = apply_resume_priority_adjustment(1, rf)
        self.assertEqual(pri, 2)
        self.assertTrue(reasons)

    def test_no_change_without_resume(self) -> None:
        pri, reasons = apply_resume_priority_adjustment(3, ResumeFitAnalysis(available=False))
        self.assertEqual(pri, 3)
        self.assertEqual(reasons, [])


if __name__ == "__main__":
    unittest.main()
