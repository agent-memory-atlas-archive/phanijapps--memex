# STUB: AC-0012
from eval.candidates import RankedCandidate, reciprocal_rank_fusion


def test_fusion_deduplicates_and_uses_slug_as_final_tie_break() -> None:
    sources = [
        [RankedCandidate("beta", 1), RankedCandidate("alpha", 2)],
        [RankedCandidate("alpha", 1), RankedCandidate("beta", 2)],
    ]

    ranked = reciprocal_rank_fusion(sources)

    assert [candidate.slug for candidate in ranked] == ["alpha", "beta"]
