"""PMO-25 (B-19): atomic cache writes, one generation per key, bounded cache size."""

import os
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

from photo_meta_organizer.infrastructure import thumbnail_service as module
from photo_meta_organizer.infrastructure.thumbnail_service import ThumbnailService


@pytest.fixture
def source(tmp_path) -> str:
    path = tmp_path / "src.jpg"
    Image.new("RGB", (400, 300), (200, 30, 30)).save(path)
    return str(path)


def _cache_files(service: ThumbnailService) -> list[Path]:
    return [p for p in service.cache_dir.iterdir() if p.is_file()]


def test_cache_holds_only_complete_webp_files(tmp_path, source):
    service = ThumbnailService(cache_dir=str(tmp_path / "thumbs"))
    data = service.generate_thumbnail(source, "h1", 100, 100)

    files = _cache_files(service)
    assert [p.name for p in files] == ["h1_100x100.webp"]
    assert files[0].read_bytes() == data
    assert data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def test_failed_write_leaves_no_partial_file(tmp_path, source, monkeypatch):
    service = ThumbnailService(cache_dir=str(tmp_path / "thumbs"))

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(module.os, "replace", boom)
    data = service.generate_thumbnail(source, "h1", 100, 100)

    assert data is not None  # still served, just not cached
    assert _cache_files(service) == []


def test_concurrent_requests_for_one_thumbnail_render_it_once(tmp_path, source, monkeypatch):
    service = ThumbnailService(cache_dir=str(tmp_path / "thumbs"))
    renders = 0
    real_render = service._render

    def slow_render(*args, **kwargs):
        nonlocal renders
        renders += 1
        time.sleep(0.05)
        return real_render(*args, **kwargs)

    monkeypatch.setattr(service, "_render", slow_render)
    results: list[bytes | None] = []
    threads = [
        threading.Thread(target=lambda: results.append(service.generate_thumbnail(source, "h1")))
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert renders == 1
    assert len(results) == 8 and len(set(results)) == 1 and results[0]


def test_cache_is_bounded_and_evicts_least_recently_used(tmp_path, source):
    service = ThumbnailService(cache_dir=str(tmp_path / "thumbs"))
    one = len(service.generate_thumbnail(source, "probe", 100, 100))
    service.clear_cache()

    service = ThumbnailService(cache_dir=str(tmp_path / "thumbs"), max_bytes=one * 3)
    for name in ("a", "b", "c"):
        service.generate_thumbnail(source, name, 100, 100)
        time.sleep(0.02)  # distinct recency stamps
    service.generate_thumbnail(source, "a", 100, 100)  # a hit makes "a" recent again
    time.sleep(0.02)
    service.generate_thumbnail(source, "d", 100, 100)  # over budget: evict

    names = {p.name.split("_")[0] for p in _cache_files(service)}
    assert "b" not in names  # least recently used
    assert {"a", "d"} <= names
    assert sum(p.stat().st_size for p in _cache_files(service)) <= one * 3


def test_existing_cache_counts_toward_the_budget(tmp_path, source):
    thumbs = tmp_path / "thumbs"
    first = ThumbnailService(cache_dir=str(thumbs))
    for name in ("a", "b", "c", "d"):
        first.generate_thumbnail(source, name, 100, 100)
    one = os.path.getsize(first.get_thumbnail_path("a", 100, 100))

    ThumbnailService(cache_dir=str(thumbs), max_bytes=one * 2)  # trims on start

    assert sum(p.stat().st_size for p in thumbs.iterdir()) <= one * 2


def test_stray_temp_files_are_removed_on_start(tmp_path):
    thumbs = tmp_path / "thumbs"
    thumbs.mkdir()
    (thumbs / "h1_100x100.webp.123.tmp").write_bytes(b"partial")

    ThumbnailService(cache_dir=str(thumbs))

    assert list(thumbs.iterdir()) == []
