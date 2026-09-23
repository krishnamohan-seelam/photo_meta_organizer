"""What counts as a photo: the single source of truth for indexable image formats."""

from pathlib import PurePath

IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".jpg", ".jpeg", ".png", ".tiff", ".tif",
        ".bmp", ".gif", ".webp", ".heic", ".heif",
        ".raw", ".cr2", ".nef", ".arw", ".dng",
    }
)


def is_image_filename(filename: str) -> bool:
    """True if ``filename`` has an indexable image extension (case-insensitive)."""
    return PurePath(filename).suffix.lower() in IMAGE_EXTENSIONS
