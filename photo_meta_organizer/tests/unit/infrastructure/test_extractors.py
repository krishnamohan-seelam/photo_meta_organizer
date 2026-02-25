"""Unit tests for infrastructure.extractors.disk_metadata_extractor.

Tests for _ExifFieldMapper internal utility class including:
- GPS coordinate parsing (DMS → decimal)
- Exposure time formatting
- Focal length formatting
- EXIF datetime parsing
- Raw tags filtering
"""

import pytest
from datetime import datetime
from unittest.mock import Mock

from photo_meta_organizer.domain.models import CameraProfile, GpsCoordinates
from photo_meta_organizer.infrastructure.extractors.disk_metadata_extractor import (
    _ExifFieldMapper,
)


@pytest.mark.unit
class TestExifFieldMapper:
    """Tests for internal EXIF field mapping utility."""

    # --- Exposure Time Formatting ---

    def test_format_exposure_time_fraction(self) -> None:
        """0.00625 → '1/160'."""
        result = _ExifFieldMapper.format_exposure_time(0.00625)
        assert result == "1/160"

    def test_format_exposure_time_hundredth(self) -> None:
        """0.01 → '1/100'."""
        result = _ExifFieldMapper.format_exposure_time(0.01)
        assert result == "1/100"

    def test_format_exposure_time_half(self) -> None:
        """0.5 → '1/2'."""
        result = _ExifFieldMapper.format_exposure_time(0.5)
        assert result == "1/2"

    def test_format_exposure_time_seconds(self) -> None:
        """2.0 → '2.0\"'."""
        result = _ExifFieldMapper.format_exposure_time(2.0)
        assert result == '2.0"'

    def test_format_exposure_time_one_second(self) -> None:
        """1.0 → '1.0\"'."""
        result = _ExifFieldMapper.format_exposure_time(1.0)
        assert result == '1.0"'

    def test_format_exposure_time_zero(self) -> None:
        """0 → '0'."""
        result = _ExifFieldMapper.format_exposure_time(0)
        assert result == "0"

    def test_format_exposure_time_non_clean_fraction(self) -> None:
        """Non-clean fraction gets decimal format."""
        result = _ExifFieldMapper.format_exposure_time(0.003)
        assert result.endswith("s")

    # --- Focal Length Formatting ---

    def test_format_focal_length_integer(self) -> None:
        """35.0 → '35mm'."""
        result = _ExifFieldMapper.format_focal_length(35.0)
        assert result == "35mm"

    def test_format_focal_length_decimal(self) -> None:
        """50.5 → '50.5mm'."""
        result = _ExifFieldMapper.format_focal_length(50.5)
        assert result == "50.5mm"

    def test_format_focal_length_small(self) -> None:
        """3.9 → '3.9mm' (mobile phone)."""
        result = _ExifFieldMapper.format_focal_length(3.9)
        assert result == "3.9mm"

    # --- DateTime Parsing ---

    def test_parse_exif_datetime_standard(self) -> None:
        """Standard EXIF format: 'YYYY:MM:DD HH:MM:SS'."""
        dt = _ExifFieldMapper.parse_exif_datetime("2022:09:21 19:49:51")
        assert dt == datetime(2022, 9, 21, 19, 49, 51)

    def test_parse_exif_datetime_with_spaces(self) -> None:
        """EXIF with space separators in time component."""
        dt = _ExifFieldMapper.parse_exif_datetime("2019:01:15 12: 59: 32")
        assert dt == datetime(2019, 1, 15, 12, 59, 32)

    def test_parse_exif_datetime_invalid(self) -> None:
        """Invalid format returns None."""
        dt = _ExifFieldMapper.parse_exif_datetime("invalid")
        assert dt is None

    def test_parse_exif_datetime_empty(self) -> None:
        """Empty string returns None."""
        dt = _ExifFieldMapper.parse_exif_datetime("")
        assert dt is None

    # --- GPS Coordinate Parsing ---

    def test_parse_gps_coordinates_missing_tags(self) -> None:
        """Missing GPS tags returns None."""
        coords = _ExifFieldMapper.parse_gps_coordinates({})
        assert coords is None

    def test_parse_gps_coordinates_partial_tags(self) -> None:
        """Partial GPS tags (missing longitude) returns None."""
        tags = {
            "GPS GPSLatitude": Mock(values=[17, 30, 33.4]),
            "GPS GPSLatitudeRef": Mock(__str__=lambda self: "N"),
        }
        coords = _ExifFieldMapper.parse_gps_coordinates(tags)
        assert coords is None

    # --- Raw Tags Collection ---

    def test_collect_raw_tags_filters_mapped(self) -> None:
        """Mapped EXIF tags are excluded from raw_tags."""
        exif_tags = {
            "Image Make": "Sony",
            "Image Model": "A7III",
            "EXIF ISOSpeedRatings": 100,
            "EXIF LensModel": "FE 35mm",  # NOT in MAPPED_TAGS
            "EXIF CustomTag": "custom_value",  # NOT in MAPPED_TAGS
        }
        raw = _ExifFieldMapper.collect_raw_tags(exif_tags)
        # Make and Model are in MAPPED_TAGS, should be excluded
        assert "Image Make" not in raw
        assert "Image Model" not in raw
        assert "EXIF ISOSpeedRatings" not in raw
        # These are NOT in MAPPED_TAGS, should be included
        assert "EXIF LensModel" in raw
        assert "EXIF CustomTag" in raw

    def test_collect_raw_tags_empty_input(self) -> None:
        """Empty exif_tags returns empty dict."""
        raw = _ExifFieldMapper.collect_raw_tags({})
        assert raw == {}

    # --- Tag Value Extraction ---

    def test_get_tag_str_present(self) -> None:
        """Extract string from present tag."""
        tags = {"Image Make": Mock(__str__=lambda self: "Sony")}
        result = _ExifFieldMapper.get_tag_str(tags, "Image Make")
        assert result == "Sony"

    def test_get_tag_str_missing(self) -> None:
        """Missing tag returns None."""
        result = _ExifFieldMapper.get_tag_str({}, "Image Make")
        assert result is None

    def test_get_tag_int_present(self) -> None:
        """Extract integer from present tag."""
        tags = {"EXIF ISOSpeedRatings": Mock(values=[100])}
        result = _ExifFieldMapper.get_tag_int(tags, "EXIF ISOSpeedRatings")
        assert result == 100

    def test_get_tag_int_missing(self) -> None:
        """Missing tag returns None."""
        result = _ExifFieldMapper.get_tag_int({}, "EXIF ISOSpeedRatings")
        assert result is None

    def test_get_tag_float_present(self) -> None:
        """Extract float from present tag."""
        tags = {"EXIF FNumber": Mock(values=[2.8])}
        result = _ExifFieldMapper.get_tag_float(tags, "EXIF FNumber")
        assert result == 2.8

    def test_get_tag_float_missing(self) -> None:
        """Missing tag returns None."""
        result = _ExifFieldMapper.get_tag_float({}, "EXIF FNumber")
        assert result is None
