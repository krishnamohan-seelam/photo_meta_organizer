"""Open any indexable photo as a Pillow image, including HEIC/HEIF and camera RAW (PMO-23).

Pillow alone decodes neither (B-11): HEIC/HEIF comes from ``pillow-heif``, registered
as a Pillow plugin on import, and RAW from LibRaw through ``rawpy``. For RAW the
camera's embedded preview is used when it has one (fast, and what the camera showed);
otherwise the sensor data is demosaiced at half size.

Both the extractor (dimensions) and the thumbnail service go through this module, so
a format that gets a thumbnail also gets real dimensions and vice versa.
"""

import io
import logging
from typing import BinaryIO

import pillow_heif
import rawpy
from PIL import Image, ImageOps

from photo_meta_organizer.domain.formats import is_raw_filename

logger = logging.getLogger(__name__)

pillow_heif.register_heif_opener()

# LibRaw's ``sizes.flip`` → the Pillow transpose that shows the image upright.
_FLIP_TRANSPOSE = {
    3: Image.Transpose.ROTATE_180,
    5: Image.Transpose.ROTATE_90,
    6: Image.Transpose.ROTATE_270,
}


def open_image(source: str | BinaryIO, filename: str) -> Image.Image:
    """Decode ``source`` (a path or a binary stream) into an upright Pillow image.

    ``filename`` picks the decoder by extension. The result is loaded (not lazy),
    already rotated for display, and owned by the caller.

    Raises:
        OSError / ValueError / rawpy.LibRawError: if the file cannot be decoded.
    """
    if is_raw_filename(filename):
        return _open_raw(source)
    with Image.open(source) as img:
        img.load()
        return ImageOps.exif_transpose(img)


def image_size(source: str | BinaryIO, filename: str) -> tuple[int, int]:
    """(width, height) as stored, without decoding pixels where the format allows it.

    Like Pillow's ``Image.size`` for a JPEG, this is the sensor orientation: an EXIF
    or RAW rotation is not applied.
    """
    if is_raw_filename(filename):
        with rawpy.imread(_raw_input(source)) as raw:
            return raw.sizes.width, raw.sizes.height
    with Image.open(source) as img:
        return img.size


def _raw_input(source: str | BinaryIO) -> str | BinaryIO:
    if isinstance(source, str):
        return source
    source.seek(0)
    return source


def _open_raw(source: str | BinaryIO) -> Image.Image:
    with rawpy.imread(_raw_input(source)) as raw:
        try:
            thumb = raw.extract_thumb()
        except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
            thumb = None
        if thumb is not None and thumb.format == rawpy.ThumbFormat.JPEG:
            with Image.open(io.BytesIO(thumb.data)) as preview:
                preview.load()
                return _orient_preview(preview, raw.sizes.flip)
        if thumb is not None and thumb.format == rawpy.ThumbFormat.BITMAP:
            return _apply_flip(Image.fromarray(thumb.data), raw.sizes.flip)
        # No usable preview: demosaic. postprocess() applies the flip itself.
        logger.debug("RAW has no embedded preview; demosaicing at half size")
        return Image.fromarray(raw.postprocess(half_size=True, use_camera_wb=True))


def _orient_preview(preview: Image.Image, flip: int) -> Image.Image:
    """An embedded JPEG that carries its own orientation wins; otherwise use LibRaw's."""
    if preview.getexif().get(0x0112, 1) != 1:
        return ImageOps.exif_transpose(preview)
    return _apply_flip(preview.copy(), flip)


def _apply_flip(img: Image.Image, flip: int) -> Image.Image:
    transpose = _FLIP_TRANSPOSE.get(flip)
    return img.transpose(transpose) if transpose is not None else img
