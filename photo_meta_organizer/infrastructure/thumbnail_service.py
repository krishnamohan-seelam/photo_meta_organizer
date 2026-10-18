"""Thumbnail generation and caching service for photo organizer.

Provides on-the-fly thumbnail generation using Pillow, converting images to
lightweight WebP format, cached on disk (PMO-25, B-19):

- Cache writes are atomic (temp file + ``os.replace``), so a concurrent reader never
  sees a truncated WebP. Stray temp files from a crash are removed on start.
- Requests for the same thumbnail are single-flight: one thread renders it, the
  others wait and read the cached result. At most ``max_concurrent`` renders run at
  once, so a grid asking for hundreds of missing thumbnails does not decode them all
  in parallel.
- The cache is bounded by ``max_bytes`` and evicts the least recently used files
  (recency is the file mtime, refreshed on every hit, so it survives restarts).
"""

import io
import logging
import os
import threading
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from PIL import Image

from photo_meta_organizer.infrastructure.image_decoding import open_image

logger = logging.getLogger(__name__)

DEFAULT_MAX_BYTES = 1024 * 1024 * 1024  # 1 GiB
_TEMP_SUFFIX = ".tmp"


class ThumbnailService:
    """Service to create, cache, and serve optimized image thumbnails."""

    def __init__(
        self,
        cache_dir: str | Path,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_concurrent: int | None = None,
    ) -> None:
        """Initialize ThumbnailService.

        Args:
            cache_dir: Directory where generated thumbnails are stored
                       (``Settings.thumbnail_dir``; nothing is assumed about the CWD).
            max_bytes: Size budget of the cache; least recently used files are
                       evicted beyond it.
            max_concurrent: Renders allowed at once (default: half the CPUs, min 2).
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes

        self._lock = threading.Lock()
        # file name -> size, least recently used first
        self._entries: OrderedDict[str, int] = OrderedDict()
        self._total_bytes = 0
        # Per-key locks for single-flight rendering, with a waiter count so they
        # can be dropped once nobody holds them.
        self._key_locks: dict[str, tuple[threading.Lock, int]] = {}
        workers = max_concurrent or max(2, (os.cpu_count() or 4) // 2)
        self._render_slots = threading.BoundedSemaphore(workers)

        self._load_index()
        logger.info(
            "ThumbnailService initialized with cache directory: %s (%d files, %.1f MB)",
            self.cache_dir,
            len(self._entries),
            self._total_bytes / 1e6,
        )

    def get_thumbnail_path(self, file_hash: str, width: int = 320, height: int = 320) -> Path:
        """Get the cached thumbnail file path for a given file hash and dimension."""
        filename = f"{file_hash}_{width}x{height}.webp"
        return self.cache_dir / filename

    def generate_thumbnail(
        self,
        source_path: str,
        file_hash: str,
        width: int = 320,
        height: int = 320,
        quality: int = 80,
    ) -> bytes | None:
        """Return a WebP thumbnail, from the disk cache or freshly rendered and cached.

        Args:
            source_path: Path to the original image file.
            file_hash: SHA-256 hash of the image.
            width: Target maximum width.
            height: Target maximum height.
            quality: WebP compression quality (1-100).

        Returns:
            Bytes of the WebP thumbnail, or None if generation failed.
        """
        cached_path = self.get_thumbnail_path(file_hash, width, height)
        cached = self._read_cached(cached_path)
        if cached is not None:
            return cached

        with self._key_lock(cached_path.name):
            # Another request may have rendered it while this one waited.
            cached = self._read_cached(cached_path)
            if cached is not None:
                return cached

            if not os.path.exists(source_path):
                logger.warning("Source image path does not exist: %s", source_path)
                return None

            with self._render_slots:
                thumb_bytes = self._render(source_path, width, height, quality)
            if thumb_bytes is not None:
                self._store(cached_path, thumb_bytes)
            return thumb_bytes

    def clear_cache(self) -> int:
        """Clear all cached thumbnail files."""
        count = 0
        for item in self.cache_dir.glob("*.webp"):
            try:
                item.unlink()
                count += 1
            except OSError:
                pass
        with self._lock:
            self._entries.clear()
            self._total_bytes = 0
        return count

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _render(self, source_path: str, width: int, height: int, quality: int) -> bytes | None:
        """Decode ``source_path`` and encode a WebP thumbnail (no caching)."""
        try:
            # Any supported format (HEIC, RAW included), already upright.
            with open_image(source_path, Path(source_path).name) as img:
                # Convert to RGB if RGBA or P to avoid issues with WebP
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGBA")
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                # Generate thumbnail preserving aspect ratio
                img.thumbnail((width, height), Image.Resampling.LANCZOS)

                buffer = io.BytesIO()
                img.save(buffer, format="WEBP", quality=quality, method=4)
                return buffer.getvalue()
        except Exception as err:
            logger.error("Error generating thumbnail for %s: %s", source_path, err)
            return None

    def _read_cached(self, path: Path) -> bytes | None:
        """Cached bytes (marking the entry recently used), or None on a miss."""
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as e:
            logger.warning("Failed to read cached thumbnail %s: %s", path, e)
            return None
        try:
            os.utime(path)  # recency survives a restart
        except OSError:
            pass
        with self._lock:
            if path.name in self._entries:
                self._entries.move_to_end(path.name)
        return data

    def _store(self, path: Path, data: bytes) -> None:
        """Write ``data`` atomically, then evict down to the size budget."""
        temp = path.with_name(f"{path.name}.{os.getpid()}-{threading.get_ident()}{_TEMP_SUFFIX}")
        try:
            temp.write_bytes(data)
            os.replace(temp, path)
        except OSError as write_err:
            logger.warning("Failed to write thumbnail cache: %s", write_err)
            temp.unlink(missing_ok=True)
            return
        with self._lock:
            self._total_bytes += len(data) - self._entries.pop(path.name, 0)
            self._entries[path.name] = len(data)
            victims = self._pop_over_budget(keep=path.name)
        self._unlink(victims)

    def _pop_over_budget(self, keep: str | None = None) -> list[str]:
        """Drop least recently used entries until within budget. Caller holds the lock."""
        victims: list[str] = []
        for name in list(self._entries):
            if self._total_bytes <= self.max_bytes:
                break
            if name == keep:
                continue
            self._total_bytes -= self._entries.pop(name)
            victims.append(name)
        return victims

    def _unlink(self, names: list[str]) -> None:
        for name in names:
            try:
                (self.cache_dir / name).unlink(missing_ok=True)
            except OSError as e:
                logger.warning("Failed to evict thumbnail %s: %s", name, e)

    def _load_index(self) -> None:
        """Index the existing cache by recency, drop crash leftovers, trim to budget."""
        found: list[tuple[float, str, int]] = []
        for item in self.cache_dir.iterdir():
            if not item.is_file():
                continue
            if item.name.endswith(_TEMP_SUFFIX):
                item.unlink(missing_ok=True)
                continue
            if item.suffix == ".webp":
                stat = item.stat()
                found.append((stat.st_mtime, item.name, stat.st_size))
        for _, name, size in sorted(found):
            self._entries[name] = size
            self._total_bytes += size
        with self._lock:
            victims = self._pop_over_budget()
        self._unlink(victims)

    @contextmanager
    def _key_lock(self, key: str) -> Iterator[None]:
        """Hold the lock for one cache key; dropped again once nobody waits on it."""
        with self._lock:
            lock, waiters = self._key_locks.get(key, (threading.Lock(), 0))
            self._key_locks[key] = (lock, waiters + 1)
        with lock:
            try:
                yield
            finally:
                with self._lock:
                    _, waiters = self._key_locks[key]
                    if waiters == 1:
                        del self._key_locks[key]
                    else:
                        self._key_locks[key] = (lock, waiters - 1)
