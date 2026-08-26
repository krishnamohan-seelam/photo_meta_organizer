"""Thumbnail generation and caching service for photo organizer.

Provides on-the-fly thumbnail generation using Pillow, converting images to
lightweight WebP format with an LRU-friendly file-based disk cache.
"""

import hashlib
import io
import logging
import os
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)


class ThumbnailService:
    """Service to create, cache, and serve optimized image thumbnails."""

    def __init__(self, cache_dir: Optional[str] = None) -> None:
        """Initialize ThumbnailService.

        Args:
            cache_dir: Directory where generated thumbnails are stored.
                       Defaults to '.cache/thumbnails' in current working dir.
        """
        if cache_dir is None:
            cache_dir = os.path.join(os.getcwd(), ".cache", "thumbnails")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info("ThumbnailService initialized with cache directory: %s", self.cache_dir)

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
    ) -> Optional[bytes]:
        """Generate a WebP thumbnail from a source image and cache it on disk.

        Args:
            source_path: Path to the original image file.
            file_hash: SHA-256 hash of the image.
            width: Target maximum width.
            height: Target maximum height.
            quality: WebP compression quality (1-100).

        Returns:
            Bytes of the generated WebP thumbnail, or None if generation failed.
        """
        cached_path = self.get_thumbnail_path(file_hash, width, height)
        if cached_path.exists():
            try:
                return cached_path.read_bytes()
            except Exception as e:
                logger.warning("Failed to read cached thumbnail %s: %s", cached_path, e)

        if not os.path.exists(source_path):
            logger.warning("Source image path does not exist: %s", source_path)
            return None

        try:
            with Image.open(source_path) as img:
                # Correct EXIF orientation if present
                img = ImageOps.exif_transpose(img)
                
                # Convert to RGB if RGBA or P to avoid issues with WebP
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGBA")
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                # Generate thumbnail preserving aspect ratio
                img.thumbnail((width, height), Image.Resampling.LANCZOS)

                buffer = io.BytesIO()
                img.save(buffer, format="WEBP", quality=quality, method=4)
                thumb_bytes = buffer.getvalue()

                # Save to disk cache
                try:
                    cached_path.write_bytes(thumb_bytes)
                except Exception as write_err:
                    logger.warning("Failed to write thumbnail cache: %s", write_err)

                return thumb_bytes
        except Exception as err:
            logger.error("Error generating thumbnail for %s: %s", source_path, err)
            return None

    def clear_cache(self) -> int:
        """Clear all cached thumbnail files."""
        count = 0
        for item in self.cache_dir.glob("*.webp"):
            try:
                item.unlink()
                count += 1
            except Exception:
                pass
        return count
