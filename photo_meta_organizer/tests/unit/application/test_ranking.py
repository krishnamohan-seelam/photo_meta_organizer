"""Ranked search snapshots and the relative cut-off (ADR-003 R9, ticket 15)."""

import pytest

from photo_meta_organizer.application.ranking import RankedHit, RankSnapshots, cut_off


def _hits(*scores: float) -> list[RankedHit]:
    return [RankedHit(file_hash=f"h{i}", score=s) for i, s in enumerate(scores)]


class TestCutOff:
    def test_keeps_scores_within_the_margin_of_the_best(self):
        kept = cut_off(_hits(0.9, 0.85, 0.79, 0.5), top_n=10, margin=0.1)
        assert [h.score for h in kept] == [0.9, 0.85]

    def test_keeps_at_most_top_n(self):
        assert len(cut_off(_hits(0.9, 0.9, 0.9, 0.9), top_n=2, margin=0.5)) == 2

    def test_everything_keeps_every_hit(self):
        assert len(cut_off(_hits(0.9, 0.1, -0.5), top_n=1, margin=0.0, everything=True)) == 3

    def test_no_hits(self):
        assert cut_off([], top_n=5, margin=0.1) == []


class TestRankSnapshots:
    def test_a_token_names_the_ranked_list(self):
        snapshots = RankSnapshots()
        token = snapshots.put(_hits(0.9, 0.8))
        assert [h.file_hash for h in snapshots.get(token) or []] == ["h0", "h1"]

    def test_unknown_token_is_none(self):
        assert RankSnapshots().get("nope") is None

    def test_expires_after_the_ttl(self):
        now = [1000.0]
        snapshots = RankSnapshots(ttl_seconds=600, clock=lambda: now[0])
        token = snapshots.put(_hits(0.9))
        now[0] += 599
        assert snapshots.get(token) is not None
        now[0] += 2
        assert snapshots.get(token) is None

    def test_holds_a_bounded_number_and_drops_the_oldest(self):
        snapshots = RankSnapshots(max_snapshots=2)
        first = snapshots.put(_hits(0.1))
        second = snapshots.put(_hits(0.2))
        snapshots.get(first)  # used: now the newest
        third = snapshots.put(_hits(0.3))
        assert snapshots.get(second) is None
        assert snapshots.get(first) is not None and snapshots.get(third) is not None

    @pytest.mark.parametrize("bad", [0, -1])
    def test_rejects_a_non_positive_bound(self, bad):
        with pytest.raises(ValueError):
            RankSnapshots(max_snapshots=bad)
