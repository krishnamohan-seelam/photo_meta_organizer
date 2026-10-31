"""Vector search benchmark: the first search after a restart, with and without the saved index.

Builds a synthetic library of N photos with random 512-dimensional embeddings, then opens it
again the way the app does after a restart and times the first ``nearest()`` (ticket 16,
ADR-003 R6). The operating system's file cache stays warm between runs, so the "cold" numbers
are a restart, not a reboot. Usage::

    python -m scripts.benchmark_vector_index --count 100000
"""

import argparse
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np

from photo_meta_organizer.application.composition import build_analysis_repository
from photo_meta_organizer.application.interfaces.search_types import SearchQuery
from photo_meta_organizer.domain.analysis import Embedding
from photo_meta_organizer.domain.models import (
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import SqliteRepository

MODEL = "clip-benchmark"
DIM = 512
MAKES = ["Sony", "Canon", "Nikon", "Apple"]


def _photo(i: int) -> ImageMetadata:
    return ImageMetadata(
        file_hash=f"{i:064x}",
        file_info=ImageFileInfo(
            name=f"IMG_{i:06d}.jpg",
            path=f"D:/photos/IMG_{i:06d}.jpg",
            size_bytes=1_000_000 + i,
            mime_type="image/jpeg",
        ),
        dimensions=ImageDimensions(width=6000, height=4000),
        exif=ImageExifData(camera_make=MAKES[i % len(MAKES)]),
    )


def _ms(action: Callable[[], object]) -> float:
    start = time.perf_counter()
    action()
    return (time.perf_counter() - start) * 1000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--count", type=int, default=100_000)
    args = parser.parse_args()
    rng = np.random.default_rng(42)
    query = rng.standard_normal(DIM).tolist()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db, models = Path(tmp) / "bench.db", Path(tmp) / "models"
        repo = SqliteRepository(str(db))
        analysis = build_analysis_repository(repo, models)
        start = time.perf_counter()
        for batch in range(0, args.count, 5_000):
            ids = range(batch, min(batch + 5_000, args.count))
            repo.save_many([_photo(i) for i in ids])
            vectors = rng.standard_normal((len(ids), DIM), dtype=np.float32)
            analysis.save_embeddings(
                [
                    Embedding(f"{i:064x}", MODEL, tuple(v.tolist()))
                    for i, v in zip(ids, vectors, strict=True)
                ]
            )
        print(f"{args.count} photos and embeddings written in {time.perf_counter() - start:.1f} s")
        first = _ms(lambda: analysis.nearest(query, 50, MODEL))
        print(f"  first search, builds and saves the index  {first:8.1f} ms")
        repo.close()

        _restart("restart, no saved index", db, None, query)
        _restart("restart, saved index", db, models, query)

        repo = SqliteRepository(str(db))
        clear = _ms(lambda: build_analysis_repository(repo).clear_embeddings(MODEL))
        print(f"  clear_embeddings (one trigger per row)    {clear:8.1f} ms")
        repo.close()


def _restart(label: str, db: Path, models_dir: Path | None, query: list[float]) -> None:
    """Open the library as a fresh process would and time its first searches."""
    repo = SqliteRepository(str(db))
    analysis = build_analysis_repository(repo, models_dir)
    cold = _ms(lambda: analysis.nearest(query, 50, MODEL))
    warm = _ms(lambda: analysis.nearest(query, 50, MODEL))
    filtered = _ms(lambda: analysis.nearest(query, 50, MODEL, SearchQuery(camera_makes=["Sony"])))
    print(f"  {label:<26} first {cold:8.1f} ms, then {warm:6.1f} ms, 25% filter {filtered:6.1f} ms")
    repo.close()


if __name__ == "__main__":
    main()
