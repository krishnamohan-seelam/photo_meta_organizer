"""Domain models for image metadata management.

This module contains core business entities that represent the domain logic
for handling image metadata. These are pure Python dataclasses with no
external dependencies, making them highly testable and portable.

The module follows Domain-Driven Design principles, with domain entities
being the source of truth for business rules and constraints. All entities
are immutable (frozen=True) to ensure business rule integrity.

The EXIF model uses a three-tier architecture:
- Tier 1 (Universal): Fields present in >95% of images
- Tier 2 (Common): Fields with stable semantics across camera types
- Tier 3 (Camera-Specific): Everything else via raw_tags dict
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional


# =============================================================================
# Enums
# =============================================================================


class CameraProfile(Enum):
    """Classification of camera types based on EXIF patterns.

    Used by extraction layer to apply recovery strategies for missing fields.
    Stored as metadata on ImageExifData to enable downstream inference
    (e.g., don't warn about LensModel for mobile cameras).
    """

    UNKNOWN = "unknown"
    DSLR = "dslr"
    MIRRORLESS = "mirrorless"
    MOBILE = "mobile"
    ACTION_CAM = "action_cam"
    FILM_SCANNER = "film_scanner"


# =============================================================================
# Value Objects
# =============================================================================


@dataclass(frozen=True)
class ImageFileInfo:
    """Value object representing file-level metadata.

    This immutable value object contains low-level file information
    extracted during discovery and initial processing.

    Attributes:
        name: Original filename (e.g., "DSC001.jpg").
        path: Full file path or storage key.
        size_bytes: File size in bytes.
        mime_type: MIME type (e.g., "image/jpeg").
    """

    name: str
    path: str
    size_bytes: int
    mime_type: str


@dataclass(frozen=True)
class ImageDimensions:
    """Value object representing image spatial dimensions.

    Attributes:
        width: Image width in pixels.
        height: Image height in pixels.
    """

    width: int
    height: int

    @property
    def aspect_ratio(self) -> float:
        """Calculate aspect ratio (width/height)."""
        return self.width / self.height if self.height > 0 else 0.0


@dataclass(frozen=True)
class GpsCoordinates:
    """Value object representing geographic coordinates from GPS metadata.

    Stores pre-converted decimal coordinates extracted from EXIF GPS tags.
    DMS (degrees, minutes, seconds) conversion happens in extraction layer only.

    Attributes:
        latitude: Decimal degrees, range [-90, 90]. Negative = South.
        longitude: Decimal degrees, range [-180, 180]. Negative = West.
        altitude: Elevation in meters (optional).
        datum: Reference datum (default "WGS84" for all modern cameras).
    """

    latitude: float
    longitude: float
    altitude: Optional[float] = None
    datum: str = "WGS84"

    def __post_init__(self) -> None:
        if not -90 <= self.latitude <= 90:
            raise ValueError(f"Latitude {self.latitude} out of range [-90, 90]")
        if not -180 <= self.longitude <= 180:
            raise ValueError(
                f"Longitude {self.longitude} out of range [-180, 180]"
            )


# Backward-compatible alias for migration
ImageLocation = GpsCoordinates


@dataclass(frozen=True)
class ImageExifData:
    """Value object representing EXIF metadata extracted from image.

    Handles heterogeneous camera types (DSLR, mobile, action cam, etc.)
    through a three-tier architecture:

    **Tier 1 (Universal)**: Fields present in >95% of images
    - camera_make, camera_model, captured_at, iso, f_stop,
      exposure_time, focal_length

    **Tier 2 (Common)**: Fields with stable semantics across camera types
    - camera_profile, location, flash_fired, focal_length_35mm,
      white_balance_mode, exposure_program, metering_mode, orientation

    **Tier 3 (Camera-Specific)**: Everything else → raw_tags dict

    All unknown/missing fields are None (graceful degradation).
    No field is required; domain model works with minimal EXIF.

    Field Format Notes:
    - exposure_time: String format (e.g., "1/200") for display
    - focal_length: String format (e.g., "35mm") for display
    - captured_at: From EXIF DateTimeOriginal or DateTimeDigitized
    - location: Pre-converted from GPS tags (DMS→decimal in extractor)
    - orientation: EXIF orientation tag (1-8)
    """

    # Tier 1: Universal fields (>95% of images)
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    f_stop: Optional[float] = None
    exposure_time: Optional[str] = None
    iso: Optional[int] = None
    focal_length: Optional[str] = None
    captured_at: Optional[datetime] = None

    # Tier 2: Common fields with stable semantics
    camera_profile: CameraProfile = CameraProfile.UNKNOWN
    location: Optional[GpsCoordinates] = None
    flash_fired: Optional[bool] = None
    focal_length_35mm: Optional[str] = None
    white_balance_mode: Optional[str] = None
    exposure_program: Optional[str] = None
    metering_mode: Optional[str] = None
    orientation: Optional[int] = None

    # Tier 3: Camera-specific fields
    raw_tags: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Domain Entity
# =============================================================================


@dataclass(frozen=True)
class ImageMetadata:
    """Domain entity representing extracted metadata from an image file.

    ImageMetadata is the primary immutable domain entity representing complete
    image information. It contains all metadata extracted during processing and
    serves as the source of truth for image state within the domain.

    This entity is designed for:
    - Content-based deduplication (via file_hash)
    - Query and filtering (by date, camera, location, tags)
    - Persistence to any storage backend
    - Conversion to API responses and UI models

    Attributes:
        file_hash: SHA-256 hash of file content for duplicate detection (primary key).
        file_info: File-level metadata (name, path, size, mime type).
        dimensions: Image dimensions (width, height).
        exif: EXIF metadata extracted from image.
        labels: User-defined or AI-generated tags for classification.
        added_at: Timestamp when metadata was added to index.

    Example:
        >>> metadata = ImageMetadata(
        ...     file_hash="e3b0c44298fc1c149afb...",
        ...     file_info=ImageFileInfo(
        ...         name="vacation.jpg",
        ...         path="/photos/2024/vacation.jpg",
        ...         size_bytes=5242880,
        ...         mime_type="image/jpeg"
        ...     ),
        ...     dimensions=ImageDimensions(width=4000, height=3000),
        ...     exif=ImageExifData(
        ...         camera_make="Sony",
        ...         camera_model="A7III",
        ...         camera_profile=CameraProfile.MIRRORLESS,
        ...         captured_at=datetime(2024, 1, 15, 14, 30, 0)
        ...     ),
        ...     labels=["beach", "sunset"],
        ...     added_at=datetime.now()
        ... )
    """

    file_hash: str
    file_info: ImageFileInfo
    dimensions: ImageDimensions
    exif: ImageExifData
    labels: list[str] = field(default_factory=list)
    added_at: datetime = field(default_factory=datetime.utcnow)


# =============================================================================
# Sync Domain Models
# =============================================================================


@dataclass(frozen=True)
class FileInfo:
    """Lightweight file metadata from a disk scan (for fingerprinting).

    Obtained cheaply via os.stat() without reading file content.
    Used by MetadataStateAnalyzer to detect changes without hashing.

    Attributes:
        path: Normalised absolute file path.
        size_bytes: File size in bytes (from stat.st_size).
        modified_time: Last modification time (from stat.st_mtime).
    """

    path: str
    size_bytes: int
    modified_time: datetime


@dataclass(frozen=True)
class FileState:
    """Represents the detected state of a single file during synchronization.

    Produced by MetadataStateAnalyzer after comparing disk state against
    the metadata DB. Consumed by SyncOrchestrator to decide the action
    to take for each file.

    Attributes:
        file_path: Normalised absolute file path.
        state: Classification — NEW, MODIFIED, UNCHANGED, or DELETED.
        file_hash: Current content hash (None for DELETED files).
        size_bytes: Current size in bytes (None for DELETED files).
        last_modified: Current mtime (None for DELETED files).
        previous_hash: Former DB hash, set only for MODIFIED files.
    """

    file_path: str
    state: Literal["NEW", "MODIFIED", "UNCHANGED", "DELETED"]
    file_hash: Optional[str] = None
    size_bytes: Optional[int] = None
    last_modified: Optional[datetime] = None
    previous_hash: Optional[str] = None  # Only set for MODIFIED


@dataclass
class SyncResult:
    """Summary returned after a metadata synchronization run.

    Attributes:
        new_files: Number of new files added to DB.
        modified_files: Number of modified files updated in DB.
        deleted_entries: Number of orphaned DB entries removed.
        unchanged_files: Number of files skipped (identical fingerprint).
        errors: List of error messages for files that failed processing.
        duration_seconds: Wall-clock time for the full sync run.
    """

    new_files: int = 0
    modified_files: int = 0
    deleted_entries: int = 0
    unchanged_files: int = 0
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def total_changes(self) -> int:
        """Total number of records added, updated, or removed."""
        return self.new_files + self.modified_files + self.deleted_entries
