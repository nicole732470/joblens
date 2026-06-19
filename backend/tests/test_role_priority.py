"""Offline tests for Role P-tier logic (no API / embeddings required)."""

from __future__ import annotations

import unittest

from app.schemas.candidate_profile import Track
from app.schemas.report import JDParse
from app.tools.role_priority import _strict_phrase_hit, apply_technical_penalties
from app.tools.track_match import _keyword_track_from_title


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
                Track(id="research_eng", label="Research", priority=4, example_titles=[]),
                Track(id="business_analyst", label="Analyst", priority=4, example_titles=[]),
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


class TechnicalPenaltyTests(unittest.TestCase):
    def test_penalty_skipped_for_p3_plus(self) -> None:
        profile = _minimal_profile([], penalties=["GPU hardware"])
        jd = JDParse(available=False)
        pri, hits = apply_technical_penalties(4, jd, "GPU hardware cluster admin", profile)
        self.assertEqual(pri, 4)
        self.assertEqual(hits, [])

    def test_penalty_applies_for_p1_with_hpc(self) -> None:
        profile = _minimal_profile([], penalties=["HPC hardware"])
        jd = JDParse(available=False)
        pri, hits = apply_technical_penalties(1, jd, "HPC hardware and GPU cluster", profile)
        self.assertEqual(pri, 2)
        self.assertTrue(hits)


if __name__ == "__main__":
    unittest.main()
