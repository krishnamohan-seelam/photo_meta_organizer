"""Performance Benchmarking Script for Photo Meta Organizer (Phase 2 - T2.2).

Generates a synthetic photo dataset of varying sizes, executes full indexing
with 1, 2, 4, 8 worker threads, measures throughput (images/min), execution time,
and peak memory consumption using tracemalloc.
"""

import os
import sys
import time
import shutil
import tempfile
import tracemalloc
from pathlib import Path
from PIL import Image

# Ensure package is on sys.path when running script directly
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from photo_meta_organizer.application.use_cases import (
    IndexPhotosUseCase,
    ParallelIndexPhotosUseCase,
)
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


def generate_synthetic_images(target_dir: Path, count: int = 100) -> None:
    """Generate synthetic JPEG image files for benchmarking."""
    print(f"Generating {count} synthetic test images in {target_dir}...")
    target_dir.mkdir(parents=True, exist_ok=True)
    
    colors = ["red", "green", "blue", "yellow", "purple", "cyan"]
    for i in range(count):
        filename = target_dir / f"bench_img_{i:04d}.jpg"
        color = colors[i % len(colors)]
        img = Image.new("RGB", (200, 200), color=color)
        img.save(filename, format="JPEG", quality=85)


def run_benchmark_for_workers(photos_dir: Path, db_dir: Path, workers: int) -> dict:
    """Run indexing with specified worker count and track time + memory."""
    db_file = db_dir / f"metadata_workers_{workers}.json"
    if db_file.exists():
        db_file.unlink()

    base_retriever = LocalDiskRetriever(base_path=str(photos_dir))
    retriever = ExtensionFilteredRetriever(base_retriever, {".jpg", ".png"})
    extractor = DiskMetaDataExtractor()
    repository = TinyDBRepository(db_path=str(db_file))

    tracemalloc.start()
    start_time = time.time()

    if workers == 1:
        use_case = IndexPhotosUseCase(
            retriever=retriever,
            extractor=extractor,
            repository=repository,
        )
    else:
        use_case = ParallelIndexPhotosUseCase(
            retriever=retriever,
            extractor=extractor,
            repository=repository,
            num_workers=workers,
        )

    results = use_case.execute()
    elapsed_seconds = time.time() - start_time
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    processed_count = len(results)
    throughput_imgs_per_min = (processed_count / elapsed_seconds) * 60.0 if elapsed_seconds > 0 else 0.0

    return {
        "workers": workers,
        "processed": processed_count,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "throughput_imgs_per_min": round(throughput_imgs_per_min, 2),
        "peak_memory_mb": round(peak_mem / (1024 * 1024), 2),
    }


def main():
    temp_dir = Path(tempfile.mkdtemp(prefix="pmo_benchmark_"))
    try:
        photos_dir = temp_dir / "photos"
        db_dir = temp_dir / "db"
        db_dir.mkdir()

        total_test_images = 100
        generate_synthetic_images(photos_dir, count=total_test_images)

        worker_configs = [1, 2, 4, 8]
        results = []

        print("\n=======================================================")
        print("  PHOTO META ORGANIZER - PERFORMANCE BENCHMARK SUITE   ")
        print("=======================================================\n")
        print(f"{'Workers':<10} | {'Processed':<10} | {'Elapsed (s)':<12} | {'Imgs/Min':<12} | {'Peak RAM (MB)':<12}")
        print("-" * 70)

        for w in worker_configs:
            stats = run_benchmark_for_workers(photos_dir, db_dir, workers=w)
            results.append(stats)
            print(
                f"{stats['workers']:<10} | "
                f"{stats['processed']:<10} | "
                f"{stats['elapsed_seconds']:<12} | "
                f"{stats['throughput_imgs_per_min']:<12} | "
                f"{stats['peak_memory_mb']:<12}"
            )

        print("-" * 70)

        # Calculate speedup relative to single-threaded (1 worker)
        baseline_time = results[0]["elapsed_seconds"]
        print("\nSpeedup vs Single-Threaded:")
        for res in results:
            speedup = round(baseline_time / res["elapsed_seconds"], 2) if res["elapsed_seconds"] > 0 else 1.0
            print(f"  - {res['workers']} Worker(s): {speedup}x speedup ({res['throughput_imgs_per_min']} imgs/min)")

        print("\nBenchmark completed successfully.")
        return results

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
