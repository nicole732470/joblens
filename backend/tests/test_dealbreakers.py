"""Dealbreaker matching — must not false-positive on paid campus intern postings."""

from __future__ import annotations

import unittest

from app.tools.profile_signals import _dealbreaker_hits, _dealbreaker_phrase_hit

INTEL_INTERN = """
Job title: Campus Intern
For Pay Transparency Compensation Description (Hourly) - Campus Intern
The hourly rate range for this position in the selected city is $23.75 - $23.75.
Intel Corporation is seeking motivated students for a summer internship program.
"""


class DealbreakerTests(unittest.TestCase):
    def test_paid_campus_intern_not_unpaid(self) -> None:
        blob = INTEL_INTERN.lower()
        self.assertFalse(_dealbreaker_phrase_hit("unpaid internship", blob))

    def test_unpaid_internship_still_hits(self) -> None:
        blob = "this is an unpaid internship for course credit only"
        self.assertTrue(_dealbreaker_phrase_hit("unpaid internship", blob))

    def test_company_alone_not_prestigious_uni_dealbreaker(self) -> None:
        blob = "intel corporation is a global technology company"
        phrase = "no one in the company studied in a prestigious university"
        self.assertFalse(_dealbreaker_phrase_hit(phrase, blob))

    def test_prestigious_uni_requirement_hits(self) -> None:
        blob = "candidates must have studied at a prestigious university"
        phrase = "no one in the company studied in a prestigious university"
        self.assertTrue(_dealbreaker_phrase_hit(phrase, blob))

    def test_intel_intern_no_dealbreakers(self) -> None:
        phrases = [
            "rural areas",
            "small local companies in tranditional industries",
            "no one in the company studied in a prestigious university",
            "unpaid internship",
            "no visa sponsorship stated in JD",
        ]
        n, hits = _dealbreaker_hits(phrases, INTEL_INTERN)
        self.assertEqual(n, 0, hits)


if __name__ == "__main__":
    unittest.main()
