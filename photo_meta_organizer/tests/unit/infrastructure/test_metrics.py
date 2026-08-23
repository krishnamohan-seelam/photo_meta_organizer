"""Unit tests for ProgressReporter and IndexingStatistics in infrastructure/metrics.py."""

import pytest
from photo_meta_organizer.infrastructure.metrics import (
    IndexingStatistics,
    ProgressReporter,
)


@pytest.mark.unit
class TestIndexingStatistics:
    """Tests for IndexingStatistics dataclass."""

    def test_duration_seconds_calculation(self) -> None:
        stats = IndexingStatistics(start_time=100.0, end_time=125.5)
        assert stats.duration_seconds == 25.5

    def test_duration_seconds_zero_when_unfinished(self) -> None:
        stats = IndexingStatistics(start_time=100.0, end_time=0.0)
        assert stats.duration_seconds == 0.0

    def test_throughput_calculation(self) -> None:
        # 120 images in 60 seconds (1 minute) = 120 imgs/min
        stats = IndexingStatistics(
            start_time=100.0,
            end_time=160.0,
            total_files_processed=120,
        )
        assert stats.throughput_images_per_minute == 120.0

    def test_throughput_zero_when_no_duration(self) -> None:
        stats = IndexingStatistics(total_files_processed=50)
        assert stats.throughput_images_per_minute == 0.0


@pytest.mark.unit
class TestProgressReporter:
    """Tests for ProgressReporter class."""

    def test_progress_reporter_lifecycle_disabled_bar(self) -> None:
        reporter = ProgressReporter(total_files=10, disable_bar=True)
        reporter.start(total=10, desc="Testing")

        # Mock metadata object
        class DummyInfo:
            size_bytes = 1024
            mime_type = "image/jpeg"

        class DummyMetadata:
            file_info = DummyInfo()

        reporter.update(1, metadata=DummyMetadata())
        reporter.record_error("test_error")

        stats = reporter.stop()
        assert stats.total_files_discovered == 10
        assert stats.total_files_processed == 1
        assert stats.total_size_bytes == 1024
        assert stats.mime_type_counts["image/jpeg"] == 1
        assert stats.total_errors == 1
        assert stats.error_types["test_error"] == 1

    def test_progress_reporter_handles_metadata_tracking_error(self) -> None:
        reporter = ProgressReporter(disable_bar=True)
        reporter.start()
        # Invalid object without expected attributes
        reporter.update(1, metadata=object())
        stats = reporter.stop()
        assert stats.total_files_processed == 1
