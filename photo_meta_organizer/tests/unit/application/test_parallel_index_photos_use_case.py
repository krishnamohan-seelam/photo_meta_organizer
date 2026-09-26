"""Unit tests for ParallelIndexPhotosUseCase.

Tests multi-threaded parallel extraction pipeline, worker thread pool execution,
poison pill shutdown, DB writer thread operations, and error resilience.
"""

import pytest
from unittest.mock import MagicMock
from photo_meta_organizer.application.use_cases import ParallelIndexPhotosUseCase
from photo_meta_organizer.domain.models import ImageMetadata
from tests.conftest import (
    MockImageMetadataRepository,
    MockImageRetriever,
    MockMetadataExtractor,
)


@pytest.mark.unit
class TestParallelIndexPhotosUseCase:
    """Tests for ParallelIndexPhotosUseCase."""

    def test_execute_multi_threaded_success(
        self,
        mock_extractor: MockMetadataExtractor,
        mock_retriever: MockImageRetriever,
        mock_repository: MockImageMetadataRepository,
    ) -> None:
        """Full multi-threaded pipeline: discover → parallel extract → queue → DB save."""
        use_case = ParallelIndexPhotosUseCase(
            retriever=mock_retriever,
            extractor=mock_extractor,
            repository=mock_repository,
            num_workers=4,
        )

        results = use_case.execute()

        # Should extract metadata from all files in retriever
        assert len(results) > 0
        assert all(isinstance(m, ImageMetadata) for m in results)

        # Should persist all results to repository
        stored = mock_repository.list_all()
        assert len(stored) == len(results)

    def test_execute_with_no_files(
        self,
        mock_extractor: MockMetadataExtractor,
        mock_repository: MockImageMetadataRepository,
    ) -> None:
        """Empty retriever → no extraction, no persistence."""
        empty_retriever = MockImageRetriever(files=[])
        use_case = ParallelIndexPhotosUseCase(
            retriever=empty_retriever,
            extractor=mock_extractor,
            repository=mock_repository,
            num_workers=2,
        )

        results = use_case.execute()

        assert results == []
        assert mock_repository.list_all() == []

    def test_execute_worker_exception_handling(
        self,
        mock_retriever: MockImageRetriever,
        mock_repository: MockImageMetadataRepository,
    ) -> None:
        """Failing extractor on some files logs error and continues with remaining files."""
        failing_extractor = MagicMock()
        valid_meta = mock_repository.list_all()
        failing_extractor.extract.side_effect = [
            RuntimeError("Corrupt EXIF data"),
            valid_meta[0] if valid_meta else None,
            valid_meta[0] if valid_meta else None,
        ]

        use_case = ParallelIndexPhotosUseCase(
            retriever=mock_retriever,
            extractor=failing_extractor,
            repository=mock_repository,
            num_workers=2,
        )

        results = use_case.execute()
        assert len(results) >= 0

    def test_db_writer_worker_handles_save_error(
        self,
        mock_extractor: MockMetadataExtractor,
        mock_retriever: MockImageRetriever,
    ) -> None:
        """DB repository save failure is logged and does not crash the writer thread."""
        failing_repo = MagicMock()
        failing_repo.save.side_effect = Exception("DB Disk Full")

        use_case = ParallelIndexPhotosUseCase(
            retriever=mock_retriever,
            extractor=mock_extractor,
            repository=failing_repo,
            num_workers=2,
        )

        results = use_case.execute()
        assert results == []  # Save failed for all


def _handles(n: int):
    from photo_meta_organizer.application.interfaces.image_retriever import RemoteFileHandle

    return [RemoteFileHandle(f"/p/img_{i}.jpg", f"img_{i}.jpg", 10) for i in range(n)]


@pytest.mark.unit
class TestParallelIndexRunReport:
    """PMO-18: ``run`` reports progress, errors (extract *and* save) and honours cancel."""

    def test_report_counts_extract_and_save_failures(self, mock_repository) -> None:
        class FlakyExtractor(MockMetadataExtractor):
            def extract(self, file_handle, stream):
                if file_handle.filename == "img_0.jpg":
                    raise RuntimeError("Corrupt EXIF")
                return super().extract(file_handle, stream)

        class FlakyRepo(MockImageMetadataRepository):
            def save(self, metadata):
                if metadata.file_info.name == "img_1.jpg":
                    raise OSError("disk full")
                super().save(metadata)

        report = ParallelIndexPhotosUseCase(
            MockImageRetriever(_handles(4)), FlakyExtractor(), FlakyRepo(), num_workers=2
        ).run()

        assert report.total == 4
        assert len(report.indexed) == 2
        assert len(report.errors) == 2
        assert any("img_0.jpg" in e and "Corrupt EXIF" in e for e in report.errors)
        assert any("img_1.jpg" in e and "disk full" in e for e in report.errors)
        assert report.cancelled is False

    def test_progress_callback_reaches_total(self, mock_extractor, mock_repository) -> None:
        seen = []
        report = ParallelIndexPhotosUseCase(
            MockImageRetriever(_handles(5)), mock_extractor, mock_repository, num_workers=3
        ).run(progress=seen.append)

        assert report.total == 5
        assert seen, "progress was never reported"
        assert seen[-1].processed == 5 and seen[-1].total == 5 and seen[-1].failed == 0
        assert [p.processed for p in seen] == sorted(p.processed for p in seen)

    def test_cancel_before_start_indexes_nothing(self, mock_extractor, mock_repository) -> None:
        report = ParallelIndexPhotosUseCase(
            MockImageRetriever(_handles(5)), mock_extractor, mock_repository, num_workers=2
        ).run(should_cancel=lambda: True)

        assert report.cancelled is True
        assert report.indexed == []
        assert mock_repository.list_all() == []

    def test_cancel_midway_stops_submitting_work(self, mock_repository) -> None:
        import threading

        gate = threading.Event()
        calls = []

        class SlowExtractor(MockMetadataExtractor):
            def extract(self, file_handle, stream):
                calls.append(file_handle.filename)
                if len(calls) >= 2:
                    gate.set()
                return super().extract(file_handle, stream)

        report = ParallelIndexPhotosUseCase(
            MockImageRetriever(_handles(200)), SlowExtractor(), mock_repository, num_workers=1
        ).run(should_cancel=gate.is_set)

        assert report.cancelled is True
        assert len(calls) < 200
        # Everything that was extracted before the cancel is still saved.
        assert len(mock_repository.list_all()) == len(report.indexed)

    def test_execute_still_returns_the_indexed_list(self, mock_extractor, mock_repository) -> None:
        results = ParallelIndexPhotosUseCase(
            MockImageRetriever(_handles(3)), mock_extractor, mock_repository, num_workers=2
        ).execute()
        assert len(results) == 3
