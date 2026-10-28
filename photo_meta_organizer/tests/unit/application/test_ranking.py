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
        token = snapshots.put("q", _hits(0.9, 0.8))
        assert [h.file_hash for h in snapshots.get(token, "q") or []] == ["h0", "h1"]

    def test_unknown_token_is_none(self):
        assert RankSnapshots().get("nope", "q") is None

    def test_a_token_belongs_to_the_search_that_made_it(self):
        snapshots = RankSnapshots()
        token = snapshots.put("beach", _hits(0.9))
        assert snapshots.get(token, "mountain") is None
        assert snapshots.get(token, "beach") is not None

    def test_expires_ttl_after_its_last_use(self):
        now = [1000.0]
        snapshots = RankSnapshots(ttl_seconds=600, clock=lambda: now[0])
        token = snapshots.put("q", _hits(0.9))
        now[0] += 599
        assert snapshots.get(token, "q") is not None  # used: lives another 600 s
        now[0] += 599
        assert snapshots.get(token, "q") is not None
        now[0] += 601
        assert snapshots.get(token, "q") is None

    def test_holds_a_bounded_number_and_drops_the_oldest(self):
        snapshots = RankSnapshots(max_snapshots=2)
        first = snapshots.put("a", _hits(0.1))
        second = snapshots.put("b", _hits(0.2))
        snapshots.get(first, "a")  # used: now the newest
        third = snapshots.put("c", _hits(0.3))
        assert snapshots.get(second, "b") is None
        assert snapshots.get(first, "a") is not None and snapshots.get(third, "c") is not None

    @pytest.mark.parametrize("bad", [0, -1])
    def test_rejects_a_non_positive_bound(self, bad):
        with pytest.raises(ValueError):
            RankSnapshots(max_snapshots=bad)
