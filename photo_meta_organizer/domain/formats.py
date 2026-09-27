"""What counts as a photo: the single source of truth for indexable image formats."""

from pathlib import PurePath

# Camera RAW: decoded through LibRaw (the embedded preview, or a half-size demosaic).
RAW_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".raw", ".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".dng",
        ".raf", ".orf", ".rw2", ".pef", ".srw",
    }
)

IMAGE_EXTENSIONS: frozenset[str] = (
    frozenset(
        {
            ".jpg", ".jpeg", ".png", ".tiff", ".tif",
            ".bmp", ".gif", ".webp", ".heic", ".heif",
        }
    )
    | RAW_EXTENSIONS
)

# MIME types the stdlib ``mimetypes`` table does not know on every platform.
_MIME_TYPES: dict[str, str] = {
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".cr2": "image/x-canon-cr2",
    ".cr3": "image/x-canon-cr3",
    ".nef": "image/x-nikon-nef",
    ".nrw": "image/x-nikon-nrw",
    ".arw": "image/x-sony-arw",
    ".srf": "image/x-sony-srf",
    ".sr2": "image/x-sony-sr2",
    ".dng": "image/x-adobe-dng",
    ".raf": "image/x-fuji-raf",
    ".orf": "image/x-olympus-orf",
    ".rw2": "image/x-panasonic-rw2",
    ".pef": "image/x-pentax-pef",
    ".srw": "image/x-samsung-srw",
    ".raw": "image/x-raw",
}


def is_image_filename(filename: str) -> bool:
    """True if ``filename`` has an indexable image extension (case-insensitive)."""
    return PurePath(filename).suffix.lower() in IMAGE_EXTENSIONS


def is_raw_filename(filename: str) -> bool:
    """True if ``filename`` is a camera RAW file (case-insensitive)."""
    return PurePath(filename).suffix.lower() in RAW_EXTENSIONS


def image_mime_type(filename: str) -> str | None:
    """MIME type for the RAW and HEIF formats, or None to defer to ``mimetypes``."""
    return _MIME_TYPES.get(PurePath(filename).suffix.lower())
