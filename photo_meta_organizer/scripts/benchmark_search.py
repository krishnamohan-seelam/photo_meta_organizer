"""Search benchmark: a synthetic library of N photos, timed through the repository port.

Uses only the public repository API (``save_many``, ``query``, ``facets``, ``count``), so
the same script measures any schema. ADR-003 asks for it to be re-run after R3 (assets,
files and curation as separate tables). Usage::

    python -m scripts.benchmark_search --count 100000
"""

import argparse
import random
import statistics
import tempfile
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from photo_meta_organizer.application.interfaces.search_types import SearchQuery
from photo_meta_organizer.domain.models import (
    GpsCoordinates,
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import SqliteRepository

MAKES = ["Sony", "Canon", "Nikon", "Apple", "Google", "Fujifilm"]
LABELS = ["family", "beach", "work", "trip", "pets", "food", "night", "city"]


def _photo(i: int, rng: random.Random) -> ImageMetadata:
    captured = datetime(2010, 1, 1) + timedelta(minutes=rng.randrange(0, 15 * 365 * 24 * 60))
    located = rng.random() < 0.4
    return ImageMetadata(
        file_hash=f"{i:064x}",
        file_info=ImageFileInfo(
            name=f"IMG_{i:06d}.jpg",
            path=f"D:/photos/{captured.year}/{captured.month:02d}/IMG_{i:06d}.jpg",
            size_bytes=rng.randrange(500_000, 12_000_000),
            mime_type="image/jpeg",
            modified_time=captured,
        ),
        dimensions=ImageDimensions(width=6000, height=4000),
        exif=ImageExifData(
            camera_make=rng.choice(MAKES),
            camera_model="Model",
            captured_at=None if rng.random() < 0.03 else captured,
            iso=rng.choice([100, 200, 400, 800, 1600]),
            location=(
                GpsCoordinates(latitude=rng.uniform(-60, 60), longitude=rng.uniform(-180, 180))
                if located
                else None
            ),
            raw_tags={"Make": "x", "Software": "y"},
        ),
        labels=rng.sample(LABELS, k=rng.randrange(0, 3)),
        rating=rng.choice([None, None, None, 1, 2, 3, 4, 5]),
        flagged=rng.random() < 0.1,
    )


def _time(label: str, action: Callable[[], object], repeats: int = 5) -> None:
    action()  # warm the page cache
    runs = []
    for _ in range(repeats):
        start = time.perf_counter()
        action()
        runs.append((time.perf_counter() - start) * 1000)
    print(f"  {label:<44} median {statistics.median(runs):8.1f} ms")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--count", type=int, default=100_000)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        repo = SqliteRepository(str(Path(tmp) / "bench.db"))
        rng = random.Random(42)
        start = time.perf_counter()
        batch: list[ImageMetadata] = []
        for i in range(args.count):
            batch.append(_photo(i, rng))
            if len(batch) == 5_000:
                repo.save_many(batch)
                batch.clear()
        repo.save_many(batch)
        print(f"{args.count} photos written in {time.perf_counter() - start:.1f} s")

        page = 200
        _time("count", repo.count)
        _time("first page, newest first", lambda: repo.query(_q(sort_order="desc", ps=page)))
        _time("page 100, newest first", lambda: repo.query(_q(sort_order="desc", p=100, ps=page)))
        _time("first page, by size", lambda: repo.query(_q(sort_by="size_bytes", ps=page)))
        _time("camera filter (1 of 6 makes)", lambda: repo.query(_q(camera_makes=["Sony"])))
        _time("rated 4 and flagged", lambda: repo.query(_q(rating=4, flagged=True)))
        _time("two labels (AND)", lambda: repo.query(_q(tags=["family", "beach"])))
        _time("search term in path", lambda: repo.query(_q(search_term="2019/07")))
        _time("has location", lambda: repo.query(_q(has_location=True)))
        _time("facets", repo.facets)
        repo.close()


def _q(*, p: int = 1, ps: int = 200, **filters: object) -> SearchQuery:
    return SearchQuery(page=p, page_size=ps, **filters)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
