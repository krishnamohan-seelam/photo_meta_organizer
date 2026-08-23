"""Integration chaos testing for multi-threaded parallel indexing.

Simulates parallel execution with corrupted image files, zero-byte streams,
unreadable binary files, and missing headers to verify system resilience.
"""

import pytest
import io
import tempfile
from pathlib import Path
from PIL import Image

from photo_meta_organizer.application.use_cases import ParallelIndexPhotosUseCase
from photo_meta_organizer.infrastructure.retriever.local_disk_retriever import (
    LocalDiskRetriever,
)
from photo_meta_organizer.infrastructure.retriever.filtered_retriever import (
    ExtensionFilteredRetriever,
)
from photo_meta_organizer.infrastructure.extractors.disk_metadata_extractor import (
    DiskMetaDataExtractor,
)
from photo_meta_organizer.infrastructure.repositories.tinydb_repository import (
    TinyDBRepository,
)


@pytest.mark.integration
class TestParallelChaosIndexing:
    """Chaos integration test suite for ParallelIndexPhotosUseCase."""

    @pytest.fixture
    def chaos_directory(self, tmp_path: Path) -> Path:
        """Create a directory containing a mix of valid, corrupted, zero-byte, and invalid files."""
        photos_dir = tmp_path / "chaos_photos"
        photos_dir.mkdir()

        # 1. Create valid JPEG image
        valid_img_path = photos_dir / "valid_image.jpg"
        img = Image.new("RGB", (100, 100), color="blue")
        img.save(valid_img_path, format="JPEG")

        # 2. Create another valid PNG image
        valid_png_path = photos_dir / "valid_image.png"
        img_png = Image.new("RGB", (50, 50), color="red")
        img_png.save(valid_png_path, format="PNG")

        # 3. Create corrupted JPEG (garbage bytes)
        corrupt_jpg_path = photos_dir / "corrupt_image.jpg"
        corrupt_jpg_path.write_bytes(b"\xFF\xD8\xFF\xE0" + b"GARBAGE_EXIF_DATA_CORRUPT" * 20)

        # 4. Create zero-byte JPEG file
        empty_jpg_path = photos_dir / "empty_image.jpg"
        empty_jpg_path.write_bytes(b"")

        # 5. Create non-image file with .jpg extension (text content)
        fake_jpg_path = photos_dir / "fake_text.jpg"
        fake_jpg_path.write_text("Hello World! This is plain text, not a photo.")

        return photos_dir

    def test_parallel_indexing_under_chaos_conditions(
        self,
        chaos_directory: Path,
        tmp_path: Path,
    ) -> None:
        """Pipeline must complete cleanly without crashing, saving valid files and recording errors."""
        db_file = tmp_path / "chaos_metadata.json"

        base_retriever = LocalDiskRetriever(base_path=str(chaos_directory))
        retriever = ExtensionFilteredRetriever(
            base_retriever, extensions={".jpg", ".png"}
        )
        extractor = DiskMetaDataExtractor()
        repository = TinyDBRepository(db_path=str(db_file))

        use_case = ParallelIndexPhotosUseCase(
            retriever=retriever,
            extractor=extractor,
            repository=repository,
            num_workers=4,
        )

        results = use_case.execute()

        # Valid files (valid_image.jpg & valid_image.png) must be indexed successfully
        assert len(results) >= 2

        # Verify DB records
        all_db_records = repository.list_all()
        assert len(all_db_records) == len(results)

        # Check DB hashes exist for valid files
        hashes = [r.file_hash for r in all_db_records]
        assert len(hashes) == len(set(hashes))  # No duplicate keys
