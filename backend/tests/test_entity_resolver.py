"""Entity resolver minimum-evidence rules (Salt AI-style false positives)."""

from app.tools.entity_resolver import EntityResolver


def _signals(
    *,
    shared: int,
    linkedin: int,
    dol: int,
    exact_core: bool = False,
    subset: bool = False,
) -> dict:
    return {
        "shared_count": shared,
        "linkedIn_count": linkedin,
        "dol_count": dol,
        "token_overlap_ratio": shared / linkedin if linkedin else 0,
        "reverse_overlap_ratio": shared / dol if dol else 0,
        "exact_core_match": exact_core,
        "subset_match": subset,
        "single_token_match": linkedin == 1,
        "extra_dol_tokens": [],
    }


def test_salt_ai_single_token_ambiguous_rejected():
    r = EntityResolver()
    # "Salt AI" → only "salt"; many DOL employers share that token.
    signals = _signals(shared=1, linkedin=1, dol=3, exact_core=True)
    assert r._passes_minimum_evidence(signals, ambiguity=12) is False


def test_single_word_company_still_matches_when_unique():
    r = EntityResolver()
    signals = _signals(shared=1, linkedin=1, dol=1, exact_core=True)
    assert r._passes_minimum_evidence(signals, ambiguity=1) is True


def test_subset_match_single_ambiguous_token_rejected():
    r = EntityResolver()
    signals = _signals(shared=1, linkedin=1, dol=4, subset=True)
    assert r._passes_minimum_evidence(signals, ambiguity=10) is False
