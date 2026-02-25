"""Disk-based metadata extractor for image files.

Extracts comprehensive metadata from image files on the local filesystem
using exifread for EXIF parsing and PIL/Pillow for dimensions.

This extractor is stateless — it receives a file handle and binary stream,
and returns an ImageMetadata domain entity. All conversion logic
(DMS→decimal GPS, date parsing, format normalization) is encapsulated
in the internal _ExifFieldMapper utility class.
"""

import hashlib
import logging
import mimetypes
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO, Dict, Optional

import exifread
from PIL import Image

from photo_meta_organizer.application.interfaces.image_extractor import (
    ImageMetadataExtractor,
)
from photo_meta_organizer.application.interfaces.image_retriever import (
    RemoteFileHandle,
)
from photo_meta_organizer.domain.models import (
    GpsCoordinates,
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.domain.services import CameraClassifier

logger = logging.getLogger(__name__)


# =============================================================================
# Internal Utilities
# =============================================================================


def get_file_size(file_path: str) -> int:
    """Return the size of the file in bytes.

    Args:
        file_path: Absolute path to the file.

    Returns:
        File size in bytes.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the path is not a file.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")

    return path.stat().st_size


class _ExifFieldMapper:
    """Internal utility for mapping exifread tags to ImageExifData fields.

    Handles:
    - Tag name normalization (exifread uses paths like "EXIF DateTimeOriginal")
    - Format conversion (DMS → decimal, string rationals → float)
    - Fallback chains (DateTimeDigitized if DateTimeOriginal missing)
    - GPS coordinate parsing with validation
    - Exposure time and focal length formatting

    This class contains NO domain logic — only extraction/conversion concerns.
    Camera profile inference is delegated to the CameraClassifier domain service.
    """

    # Standard tag mappings from exifread keys to domain field names.
    # Used to determine which tags have been mapped (for raw_tags filtering).
    MAPPED_TAGS = {
        "Image Make",
        "Image Model",
        "EXIF ISOSpeedRatings",
        "EXIF FNumber",
        "EXIF ExposureTime",
        "EXIF FocalLength",
        "EXIF DateTimeOriginal",
        "EXIF DateTimeDigitized",
        "EXIF WhiteBalance",
        "EXIF ExposureProgram",
        "EXIF MeteringMode",
        "EXIF Flash",
        "EXIF FocalLengthIn35mmFilm",
        "Image Orientation",
        # GPS tags are also mapped
        "GPS GPSLatitude",
        "GPS GPSLatitudeRef",
        "GPS GPSLongitude",
        "GPS GPSLongitudeRef",
        "GPS GPSAltitude",
        "GPS GPSAltitudeRef",
    }

    @staticmethod
    def parse_gps_coordinates(tags: Dict[str, Any]) -> Optional[GpsCoordinates]:
        """Convert GPS tags from exifread (DMS format) to GpsCoordinates.

        exifread returns GPS coords as [degrees, minutes, seconds] arrays
        with Ratio objects. Formula: decimal = deg + min/60 + sec/3600.
        Direction (N/S/E/W) determines sign.

        Args:
            tags: Raw exifread tag dictionary.

        Returns:
            GpsCoordinates if valid GPS data found, None otherwise.
        """
        try:
            gps_lat = tags.get("GPS GPSLatitude")
            gps_lat_ref = tags.get("GPS GPSLatitudeRef")
            gps_lon = tags.get("GPS GPSLongitude")
            gps_lon_ref = tags.get("GPS GPSLongitudeRef")

            if not all([gps_lat, gps_lat_ref, gps_lon, gps_lon_ref]):
                return None

            # Parse DMS arrays: [degrees, minutes, seconds]
            lat_values = gps_lat.values
            lat_decimal = (
                float(lat_values[0])
                + float(lat_values[1]) / 60
                + float(lat_values[2]) / 3600
            )
            if str(gps_lat_ref) == "S":
                lat_decimal = -lat_decimal

            lon_values = gps_lon.values
            lon_decimal = (
                float(lon_values[0])
                + float(lon_values[1]) / 60
                + float(lon_values[2]) / 3600
            )
            if str(gps_lon_ref) == "W":
                lon_decimal = -lon_decimal

            altitude = None
            gps_alt = tags.get("GPS GPSAltitude")
            if gps_alt:
                alt_values = gps_alt.values
                if alt_values:
                    altitude = float(alt_values[0])

            return GpsCoordinates(
                latitude=lat_decimal,
                longitude=lon_decimal,
                altitude=altitude,
                datum="WGS84",
            )
        except (KeyError, AttributeError, ZeroDivisionError, ValueError, IndexError) as e:
            logger.debug("Failed to parse GPS coordinates: %s", e)
            return None

    @staticmethod
    def format_exposure_time(exif_value: float) -> str:
        """Convert numeric exposure time to human-readable string.

        Examples:
        - 0.00625 → "1/160"
        - 0.01 → "1/100"
        - 0.5 → "1/2"
        - 1.0 → '1.0"'
        - 2.0 → '2.0"'
        """
        if exif_value == 0:
            return "0"

        if exif_value >= 1:
            return f'{exif_value:.1f}"'

        denominator = 1 / exif_value
        if abs(denominator - round(denominator)) < 0.01:
            return f"1/{int(round(denominator))}"

        return f"{exif_value:.4f}s"

    @staticmethod
    def format_focal_length(exif_value: float) -> str:
        """Convert numeric focal length to display string with 'mm' postfix.

        Examples:
        - 35.0 → "35mm"
        - 50.5 → "50.5mm"
        """
        if exif_value == int(exif_value):
            return f"{int(exif_value)}mm"
        return f"{exif_value:.1f}mm"

    @staticmethod
    def parse_exif_datetime(datetime_str: str) -> Optional[datetime]:
        """Parse EXIF datetime string to Python datetime.

        EXIF format: "YYYY:MM:DD HH:MM:SS" or "YYYY:MM:DD HH: MM: SS"
        (Note: some cameras use spaces instead of colons in time)

        Args:
            datetime_str: Raw EXIF datetime string.

        Returns:
            Parsed datetime, or None if format is invalid.
        """
        try:
            # Normalize spaces in time component
            normalized = datetime_str.replace(": ", ":").strip()
            return datetime.strptime(normalized, "%Y:%m:%d %H:%M:%S")
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def get_tag_str(tags: Dict[str, Any], key: str) -> Optional[str]:
        """Safely extract a string tag value."""
        tag = tags.get(key)
        if tag is None:
            return None
        return str(tag).strip() or None

    @staticmethod
    def get_tag_int(tags: Dict[str, Any], key: str) -> Optional[int]:
        """Safely extract an integer tag value."""
        tag = tags.get(key)
        if tag is None:
            return None
        try:
            values = tag.values
            if isinstance(values, list) and len(values) > 0:
                return int(values[0])
            return int(values)
        except (ValueError, TypeError, AttributeError, IndexError):
            try:
                return int(str(tag))
            except (ValueError, TypeError):
                return None

    @staticmethod
    def get_tag_float(tags: Dict[str, Any], key: str) -> Optional[float]:
        """Safely extract a float tag value."""
        tag = tags.get(key)
        if tag is None:
            return None
        try:
            values = tag.values
            if isinstance(values, list) and len(values) > 0:
                return float(values[0])
            return float(values)
        except (ValueError, TypeError, AttributeError, IndexError):
            try:
                return float(str(tag))
            except (ValueError, TypeError):
                return None

    @staticmethod
    def collect_raw_tags(
        exif_tags: Dict[str, Any],
    ) -> Dict[str, str]:
        """Collect all unmapped EXIF tags into raw_tags dict.

        Filters out tags that have already been mapped to Tier 1/2 fields.
        Uses MAPPED_TAGS keys (exifread tag names), not domain field names.

        Args:
            exif_tags: Full exifread tag dictionary.

        Returns:
            Dictionary of unmapped tag name → string value.
        """
        return {
            k: str(v)
            for k, v in exif_tags.items()
            if k not in _ExifFieldMapper.MAPPED_TAGS
        }


# =============================================================================
# Extractor Implementation
# =============================================================================


class DiskMetaDataExtractor(ImageMetadataExtractor):
    """Extract metadata from image files on local disk.

    This extractor is fully stateless. It receives a RemoteFileHandle
    (file metadata) and a BytesIO stream (file content), and returns
    an ImageMetadata domain entity.

    Processing pipeline:
    1. Parse EXIF tags with exifread
    2. Extract Tier 1 universal fields (make, model, etc.)
    3. Infer camera profile via CameraClassifier domain service
    4. Extract Tier 2 common fields (GPS, flash, white balance, etc.)
    5. Collect remaining tags into Tier 3 raw_tags
    6. Extract image dimensions via PIL
    7. Compute SHA-256 content hash
    8. Build and return ImageMetadata entity
    """

    def __init__(self) -> None:
        super().__init__()

    def extract(
        self, file_handle: RemoteFileHandle, stream: BinaryIO
    ) -> ImageMetadata:
        """Extract metadata from an image file stream.

        Implements recovery strategies:
        1. Try DateTimeOriginal, fallback to DateTimeDigitized, then file mtime
        2. All extraction failures are logged as warnings; returns best-effort data
        3. Camera profile is inferred via CameraClassifier domain service

        Args:
            file_handle: File handle with path and size metadata.
            stream: Binary stream of the image file content.

        Returns:
            ImageMetadata with all extracted fields populated best-effort.
        """
        mapper = _ExifFieldMapper()

        # --- Parse EXIF tags ---
        stream.seek(0)
        try:
            exif_tags = exifread.process_file(stream, details=True)
        except Exception as e:
            logger.warning("EXIF parsing failed for %s: %s", file_handle.filename, e)
            exif_tags = {}
        stream.seek(0)

        # --- Tier 1: Universal Fields ---
        camera_make = mapper.get_tag_str(exif_tags, "Image Make")
        camera_model = mapper.get_tag_str(exif_tags, "Image Model")
        iso = mapper.get_tag_int(exif_tags, "EXIF ISOSpeedRatings")
        f_stop = mapper.get_tag_float(exif_tags, "EXIF FNumber")

        exposure_time_raw = mapper.get_tag_float(exif_tags, "EXIF ExposureTime")
        exposure_time = (
            mapper.format_exposure_time(exposure_time_raw)
            if exposure_time_raw is not None
            else None
        )

        focal_length_raw = mapper.get_tag_float(exif_tags, "EXIF FocalLength")
        focal_length = (
            mapper.format_focal_length(focal_length_raw)
            if focal_length_raw is not None
            else None
        )

        # Captured datetime with fallback chain
        captured_at = mapper.parse_exif_datetime(
            mapper.get_tag_str(exif_tags, "EXIF DateTimeOriginal")
            or mapper.get_tag_str(exif_tags, "EXIF DateTimeDigitized")
            or ""
        )
        if not captured_at:
            try:
                mtime = Path(file_handle.original_path).stat().st_mtime
                captured_at = datetime.fromtimestamp(mtime)
            except (OSError, ValueError):
                captured_at = None

        # --- Camera profile inference (domain service) ---
        has_lens_model = "EXIF LensModel" in exif_tags
        camera_profile = CameraClassifier.classify(
            camera_make, camera_model, has_lens_model
        )

        # --- Tier 2: Common Fields ---
        location = mapper.parse_gps_coordinates(exif_tags)

        flash_fired = None
        flash_tag = mapper.get_tag_str(exif_tags, "EXIF Flash")
        if flash_tag:
            flash_tag_lower = flash_tag.lower()
            flash_fired = "fired" in flash_tag_lower

        white_balance_mode = mapper.get_tag_str(exif_tags, "EXIF WhiteBalance")
        exposure_program = mapper.get_tag_str(exif_tags, "EXIF ExposureProgram")
        metering_mode = mapper.get_tag_str(exif_tags, "EXIF MeteringMode")

        focal_length_35mm_raw = mapper.get_tag_float(
            exif_tags, "EXIF FocalLengthIn35mmFilm"
        )
        focal_length_35mm = (
            mapper.format_focal_length(focal_length_35mm_raw)
            if focal_length_35mm_raw is not None
            else None
        )

        orientation = mapper.get_tag_int(exif_tags, "Image Orientation")

        # --- Tier 3: Raw Tags ---
        raw_tags = mapper.collect_raw_tags(exif_tags)

        # --- Build ImageExifData ---
        exif = ImageExifData(
            camera_make=camera_make,
            camera_model=camera_model,
            captured_at=captured_at,
            iso=iso,
            f_stop=f_stop,
            exposure_time=exposure_time,
            focal_length=focal_length,
            camera_profile=camera_profile,
            location=location,
            flash_fired=flash_fired,
            focal_length_35mm=focal_length_35mm,
            white_balance_mode=white_balance_mode,
            exposure_program=exposure_program,
            metering_mode=metering_mode,
            orientation=orientation,
            raw_tags=raw_tags,
        )

        # --- Dimensions via PIL ---
        try:
            stream.seek(0)
            with Image.open(stream) as img:
                width, height = img.size
            dimensions = ImageDimensions(width=width, height=height)
        except Exception as e:
            logger.warning(
                "Failed to read dimensions for %s: %s", file_handle.filename, e
            )
            dimensions = ImageDimensions(width=0, height=0)

        # --- Content hash (SHA-256) ---
        stream.seek(0)
        file_hash = hashlib.sha256(stream.read()).hexdigest()

        # --- File info ---
        file_size = get_file_size(file_handle.original_path)
        mime_type = mimetypes.guess_type(file_handle.filename)[0] or "application/octet-stream"
        file_info = ImageFileInfo(
            name=file_handle.filename,
            path=file_handle.original_path,
            size_bytes=file_size,
            mime_type=mime_type,
        )

        return ImageMetadata(
            file_hash=file_hash,
            file_info=file_info,
            dimensions=dimensions,
            exif=exif,
        )
