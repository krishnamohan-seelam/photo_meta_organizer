"""PMO-34: the CLI's date, location and tag parsing, moved out of main.py."""

from datetime import datetime

import pytest

from photo_meta_organizer.application.search_criteria import (
    LocationFilter,
    date_bounds,
    parse_date,
    parse_location,
    parse_tags,
)

END_OF_DAY = (23, 59, 59, 999999)


@pytest.mark.unit
class TestParseDate:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("2026-03", datetime(2026, 3, 1)),
            ("2026-03-05", datetime(2026, 3, 5)),
            (" 2026-03-05 ", datetime(2026, 3, 5)),
            ("2026-03-05T10:30:00", datetime(2026, 3, 5, 10, 30)),
            # tz is dropped without shifting the wall clock (ADR D3)
            ("2026-03-05T10:30:00+02:00", datetime(2026, 3, 5, 10, 30)),
        ],
    )
    def test_valid_dates_are_naive(self, text: str, expected: datetime) -> None:
        parsed = parse_date(text)
        assert parsed == expected
        assert parsed is not None and parsed.tzinfo is None

    @pytest.mark.parametrize("text", [None, "", "   "])
    def test_empty_is_none(self, text: str | None) -> None:
        assert parse_date(text) is None

    @pytest.mark.parametrize("text", ["2026-13", "yesterday", "2026-02-30", "26-1-1"])
    def test_invalid_raises(self, text: str) -> None:
        with pytest.raises(ValueError, match="date"):
            parse_date(text)


@pytest.mark.unit
class TestDateBounds:
    def test_nothing_given(self) -> None:
        assert date_bounds() == (None, None)

    def test_single_month_covers_the_whole_month(self) -> None:
        assert date_bounds(date="2024-02") == (
            datetime(2024, 2, 1),
            datetime(2024, 2, 29, *END_OF_DAY),
        )

    def test_single_month_in_december(self) -> None:
        assert date_bounds(date="2024-12") == (
            datetime(2024, 12, 1),
            datetime(2024, 12, 31, *END_OF_DAY),
        )

    def test_single_day_covers_the_whole_day(self) -> None:
        assert date_bounds(date="2024-03-20") == (
            datetime(2024, 3, 20),
            datetime(2024, 3, 20, *END_OF_DAY),
        )

    def test_date_to_as_a_day_includes_that_day(self) -> None:
        """--date-to 2024-03-20 used to stop at 00:00 and miss photos taken that day."""
        start, end = date_bounds(date_from="2024-03-01", date_to="2024-03-20")
        assert start == datetime(2024, 3, 1)
        assert end == datetime(2024, 3, 20, *END_OF_DAY)

    def test_date_to_as_a_month_includes_that_month(self) -> None:
        assert date_bounds(date_to="2024-03")[1] == datetime(2024, 3, 31, *END_OF_DAY)

    def test_date_to_with_a_time_is_exact(self) -> None:
        assert date_bounds(date_to="2024-03-20T12:00:00")[1] == datetime(2024, 3, 20, 12)

    def test_range_beats_single_date(self) -> None:
        assert date_bounds(date="2020-01", date_from="2024-03-01") == (
            datetime(2024, 3, 1),
            None,
        )

    def test_reversed_range_raises(self) -> None:
        with pytest.raises(ValueError, match="after"):
            date_bounds(date_from="2024-05-01", date_to="2024-03-01")


@pytest.mark.unit
class TestParseLocation:
    def test_nothing_given(self) -> None:
        assert parse_location() is None

    def test_combined_argument(self) -> None:
        assert parse_location("37.77, -122.42, 10") == LocationFilter(37.77, -122.42, 10.0)

    def test_separate_arguments(self) -> None:
        assert parse_location(lat=1.5, lon=2.5, radius_km=3) == LocationFilter(1.5, 2.5, 3.0)

    def test_separate_arguments_beat_combined(self) -> None:
        assert parse_location("9,9,9", lat=1, lon=2, radius_km=3) == LocationFilter(1, 2, 3)

    @pytest.mark.parametrize("text", ["1,2", "a,b,c", "1,2,3,4", ","])
    def test_malformed_combined_raises(self, text: str) -> None:
        with pytest.raises(ValueError, match="location"):
            parse_location(text)

    def test_partial_separate_arguments_raise(self) -> None:
        with pytest.raises(ValueError, match="--lat, --lon and --radius"):
            parse_location(lat=1.0, lon=2.0)

    @pytest.mark.parametrize(
        ("lat", "lon", "radius"), [(91, 0, 1), (-91, 0, 1), (0, 181, 1), (0, 0, 0), (0, 0, -5)]
    )
    def test_out_of_range_raises(self, lat: float, lon: float, radius: float) -> None:
        with pytest.raises(ValueError):
            parse_location(lat=lat, lon=lon, radius_km=radius)


@pytest.mark.unit
class TestParseTags:
    @pytest.mark.parametrize("text", [None, "", " , ,"])
    def test_empty_is_none(self, text: str | None) -> None:
        assert parse_tags(text) is None

    def test_splits_and_strips(self) -> None:
        assert parse_tags(" beach, vacation ,,sunset") == ["beach", "vacation", "sunset"]
