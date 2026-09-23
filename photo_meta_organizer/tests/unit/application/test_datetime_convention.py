"""PMO-03: one datetime convention (naive local time, ADR D3).

The extractor produces naive datetimes (EXIF has no timezone). Search bounds coming
from the CLI or API may carry tzinfo. Comparing the two used to raise
``TypeError: can't compare offset-naive and offset-aware datetimes`` (flaw B-04).
"""

import argparse
from datetime import datetime, timezone

import pytest

from photo_meta_organizer.application.use_cases.search_photos_use_case import (
    SearchPhotosQuery,
    SearchPhotosUseCase,
)
from photo_meta_organizer.domain.datetimes import to_naive
from photo_meta_organizer.domain.models import (
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.repositories.tinydb_repository import TinyDBRepository


def _photo(file_hash: str, captured_at) -> ImageMetadata:
    return ImageMetadata(
        file_hash=file_hash,
        file_info=ImageFileInfo(
            name=f"{file_hash}.jpg", path=f"/p/{file_hash}.jpg", size_bytes=1, mime_type="image/jpeg"
        ),
        dimensions=ImageDimensions(width=1, height=1),
        exif=ImageExifData(captured_at=captured_at),
    )


class _ListRepo:
    def __init__(self, items):
        self._items = items

    def list_all(self):
        return list(self._items)


def _search(items, **query):
    return SearchPhotosUseCase(_ListRepo(items)).execute(SearchPhotosQuery(**query))


class TestToNaive:
    def test_none_stays_none(self):
        assert to_naive(None) is None

    def test_naive_is_returned_unchanged(self):
        dt = datetime(2026, 1, 1, 12, 0)
        assert to_naive(dt) == dt

    def test_aware_drops_tzinfo_without_shifting_wall_clock(self):
        aware = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        assert to_naive(aware) == datetime(2026, 1, 1, 12, 0)
        assert to_naive(aware).tzinfo is None


class TestSearchWithMixedDatetimes:
    def test_naive_records_with_aware_bounds_do_not_crash(self):
        """The exact B-04 reproduction."""
        items = [_photo("a", datetime(2026, 3, 1, 12, 0, 0))]
        result = _search(items, date_start=datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert result.total_count == 1

    def test_aware_records_with_naive_bounds_do_not_crash(self):
        items = [_photo("a", datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc))]
        result = _search(items, date_start=datetime(2026, 1, 1), date_end=datetime(2026, 12, 31))
        assert result.total_count == 1

    def test_zulu_bound_is_read_as_wall_clock(self):
        items = [
            _photo("in", datetime(2026, 1, 1, 0, 30)),
            _photo("out", datetime(2025, 12, 31, 23, 30)),
        ]
        result = _search(items, date_start=datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert [m.file_hash for m in result.items] == ["in"]

    def test_query_normalises_its_own_bounds(self):
        query = SearchPhotosQuery(
            date_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            date_end=datetime(2026, 2, 1, tzinfo=timezone.utc),
        )
        assert query.date_start.tzinfo is None
        assert query.date_end.tzinfo is None

    @pytest.mark.parametrize("order", ["asc", "desc"])
    def test_sorting_mixed_naive_aware_and_missing_does_not_crash(self, order):
        items = [
            _photo("naive", datetime(2026, 1, 2)),
            _photo("aware", datetime(2026, 1, 1, tzinfo=timezone.utc)),
            _photo("none", None),
        ]
        result = _search(items, sort_by="captured_at", sort_order=order)
        known = [m.file_hash for m in result.items if m.file_hash != "none"]
        assert known == (["aware", "naive"] if order == "asc" else ["naive", "aware"])


class TestRepositoryIndexes:
    def test_mixed_stored_datetimes_build_indexes_and_range_queries(self, tmp_path):
        repo = TinyDBRepository(str(tmp_path / "mixed.json"))
        repo.save(_photo("naive", datetime(2026, 1, 2, 10, 0)))
        repo.save(_photo("aware", datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)))

        hits = repo.find_by_date_range(date_start=datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert {m.file_hash for m in hits} == {"naive", "aware"}
        hits = repo.find_by_date_range(date_end=datetime(2026, 1, 1, 23, 0))
        assert {m.file_hash for m in hits} == {"aware"}
        repo.close()


class TestCliDateParsing:
    def test_parse_date_arg_returns_naive_datetimes(self):
        from photo_meta_organizer.main import _parse_date_arg

        for text in ("2026-03", "2026-03-05", "2026-03-05T10:30:00"):
            parsed = _parse_date_arg(text)
            assert parsed is not None and parsed.tzinfo is None, text

    def test_cli_date_search_works_on_naive_records(self, tmp_path, capsys):
        """README-documented ``search --date-from ...`` against real extractor output."""
        from photo_meta_organizer.main import handle_search_command

        db = str(tmp_path / "cli.json")
        repo = TinyDBRepository(db)
        repo.save(_photo("keep", datetime(2026, 3, 1, 12, 0)))
        repo.save(_photo("drop", datetime(2025, 3, 1, 12, 0)))
        repo.close()

        args = argparse.Namespace(
            db=db, date=None, date_from="2026-01-01", date_to="2026-12-31", camera=None,
            location=None, lat=None, lon=None, radius=None, tags=None,
            sort="captured_at", order="asc", page=1, page_size=50,
        )
        assert handle_search_command(args) == 0
        out = capsys.readouterr().out
        assert "keep.jpg" in out and "drop.jpg" not in out
