"""Unit and performance tests for TinyDBRepository indexing."""

from datetime import datetime, timezone
import time
import pytest

from photo_meta_organizer.domain.models import (
    GpsCoordinates,
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.repositories.tinydb_repository import (
    TinyDBRepository,
)


@pytest.fixture
def temp_db_path(tmp_path):
    return str(tmp_path / "test_indexed_metadata.json")


@pytest.fixture
def repo(temp_db_path):
    repository = TinyDBRepository(db_path=temp_db_path)
    yield repository
    repository.close()


def create_sample_metadata(i: int, size: int, dt: datetime) -> ImageMetadata:
    return ImageMetadata(
        file_hash=f"hash_{i:04d}",
        file_info=ImageFileInfo(
            path=f"/photos/img_{i:04d}.jpg",
            name=f"img_{i:04d}.jpg",
            size_bytes=size,
            mime_type="image/jpeg",
        ),
        dimensions=ImageDimensions(width=1920, height=1080),
        exif=ImageExifData(
            captured_at=dt,
            camera_make="CameraBrand",
            camera_model=f"Model-{i % 5}",
            location=GpsCoordinates(latitude=37.0 + (i * 0.001), longitude=-122.0),
        ),
    )


def test_hash_index_fast_lookup(repo):
    item = create_sample_metadata(1, 1024, datetime(2024, 1, 1, tzinfo=timezone.utc))
    repo.save(item)

    # Hash lookup
    retrieved = repo.get_by_filehash("hash_0001")
    assert retrieved is not None
    assert retrieved.file_hash == "hash_0001"
    assert retrieved.file_info.path == "/photos/img_0001.jpg"

    # Non-existent hash
    assert repo.get_by_filehash("non_existent") is None


def test_path_index_lookup(repo):
    item = create_sample_metadata(2, 2048, datetime(2024, 1, 2, tzinfo=timezone.utc))
    repo.save(item)

    retrieved = repo.get_by_path("/photos/img_0002.jpg")
    assert retrieved is not None
    assert retrieved.file_hash == "hash_0002"

    assert repo.get_by_path("/photos/non_existent.jpg") is None


def test_date_range_indexed_search(repo):
    d1 = datetime(2024, 1, 10, tzinfo=timezone.utc)
    d2 = datetime(2024, 2, 10, tzinfo=timezone.utc)
    d3 = datetime(2024, 3, 10, tzinfo=timezone.utc)

    repo.save(create_sample_metadata(10, 1000, d1))
    repo.save(create_sample_metadata(20, 2000, d2))
    repo.save(create_sample_metadata(30, 3000, d3))

    results = repo.find_by_date_range(
        date_start=datetime(2024, 2, 1, tzinfo=timezone.utc),
        date_end=datetime(2024, 2, 28, tzinfo=timezone.utc),
    )
    assert len(results) == 1
    assert results[0].file_hash == "hash_0020"


def test_size_range_indexed_search(repo):
    d = datetime(2024, 1, 1, tzinfo=timezone.utc)
    repo.save(create_sample_metadata(1, 500, d))
    repo.save(create_sample_metadata(2, 1500, d))
    repo.save(create_sample_metadata(3, 5000, d))

    results = repo.find_by_size_range(min_bytes=1000, max_bytes=2000)
    assert len(results) == 1
    assert results[0].file_hash == "hash_0002"


def test_index_cleanup_on_delete(repo):
    item = create_sample_metadata(1, 1024, datetime(2024, 1, 1, tzinfo=timezone.utc))
    repo.save(item)

    assert repo.get_by_filehash("hash_0001") is not None
    deleted = repo.delete("hash_0001")
    assert deleted is True
    assert repo.get_by_filehash("hash_0001") is None
    assert repo.count() == 0


def test_index_cleanup_on_delete_by_path(repo):
    item = create_sample_metadata(1, 1024, datetime(2024, 1, 1, tzinfo=timezone.utc))
    repo.save(item)

    deleted = repo.delete_by_path("/photos/img_0001.jpg")
    assert deleted is True
    assert repo.get_by_path("/photos/img_0001.jpg") is None
    assert repo.count() == 0


def test_indexing_performance_benchmark(temp_db_path):
    # Benchmark O(1) hash lookup with 200 items vs unindexed scan
    repo = TinyDBRepository(db_path=temp_db_path)
    dt = datetime(2024, 1, 1, tzinfo=timezone.utc)

    items = [create_sample_metadata(i, 1000 + i, dt) for i in range(200)]
    for item in items:
        repo.save(item)

    target_hash = "hash_0150"

    # Indexed lookup timing
    start_time = time.perf_counter()
    for _ in range(500):
        res = repo.get_by_filehash(target_hash)
        assert res is not None
    indexed_duration = time.perf_counter() - start_time

    repo.close()
    assert indexed_duration < 0.25  # 500 lookups should take < 250ms with coverage instrumentation
