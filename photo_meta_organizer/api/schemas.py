"""Pydantic schemas for API request/response models."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from photo_meta_organizer.domain.curation import (
    MAX_RATING,
    MIN_RATING,
    validate_rating,
    validate_tag,
)


class GpsCoordinatesSchema(BaseModel):
    """GPS coordinates for API responses."""

    latitude: float
    longitude: float
    altitude: float | None = None
    datum: str = "WGS84"


class FileInfoSchema(BaseModel):
    """File-level metadata schema for API responses."""

    name: str
    path: str
    size_bytes: int
    mime_type: str


class DimensionsSchema(BaseModel):
    """Image dimensions schema."""

    width: int
    height: int


class ExifDataSchema(BaseModel):
    """EXIF metadata schema for API responses."""

    camera_make: str | None = None
    camera_model: str | None = None
    f_stop: float | None = None
    exposure_time: str | None = None
    iso: int | None = None
    focal_length: str | None = None
    captured_at: datetime | None = None
    camera_profile: str = "unknown"
    location: GpsCoordinatesSchema | None = None
    flash_fired: bool | None = None
    focal_length_35mm: str | None = None
    white_balance_mode: str | None = None
    exposure_program: str | None = None
    metering_mode: str | None = None
    orientation: int | None = None
    raw_tags: dict[str, Any] = Field(default_factory=dict)


class PhotoMetadataResponse(BaseModel):
    """Full photo metadata response schema."""

    file_hash: str
    file_info: FileInfoSchema
    dimensions: DimensionsSchema
    exif: ExifDataSchema
    labels: list[str] = Field(default_factory=list)
    rating: int | None = None
    flagged: bool = False
    added_at: datetime


class PaginatedPhotosResponse(BaseModel):
    """Paginated list of photo metadata."""

    items: list[PhotoMetadataResponse]
    total_count: int
    page: int
    page_size: int
    total_pages: int


class SearchRequest(BaseModel):
    """Advanced search request body schema."""

    search_term: str | None = None
    date_start: datetime | None = None
    date_end: datetime | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    location_lat: float | None = None
    location_lon: float | None = None
    radius_km: float | None = None
    tags: list[str] | None = None
    rating: int | None = None
    flagged: bool | None = None
    sort_by: str = "captured_at"
    sort_order: str = "asc"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)


class PatchPhotoRequest(BaseModel):
    """Request schema for updating metadata of a single photo."""

    rating: int | None = Field(default=None, ge=MIN_RATING, le=MAX_RATING)
    flagged: bool | None = None
    labels: list[str] | None = None
    add_tags: list[str] | None = None
    remove_tags: list[str] | None = None


class BatchPhotoRequest(BaseModel):
    """Request schema for atomic batch operations across photos.

    ``value`` is validated against ``action``: tags need a non-empty string,
    ``set_rating`` an int 1-5 (or null to clear), ``set_flag`` a real boolean,
    and ``delete`` takes no value.
    """

    photo_hashes: list[str] = Field(min_length=1)
    action: Literal["add_tag", "remove_tag", "set_rating", "set_flag", "delete"] = Field(
        description="Action to perform: add_tag, remove_tag, set_rating, set_flag, delete"
    )
    value: Any | None = None

    @model_validator(mode="after")
    def _check_value_for_action(self) -> "BatchPhotoRequest":
        if self.action in ("add_tag", "remove_tag"):
            self.value = validate_tag(self.value)
        elif self.action == "set_rating":
            validate_rating(self.value)
        elif self.action == "set_flag":
            if not isinstance(self.value, bool):
                raise ValueError(f"set_flag requires a boolean value; got {self.value!r}")
        return self


class BatchPhotoResponse(BaseModel):
    """Response schema for batch operations."""

    updated_count: int
    deleted_count: int = 0
    action: str
    message: str


class CollectionCreateRequest(BaseModel):
    """Request schema for creating or updating a collection."""

    name: str
    description: str = ""
    photo_hashes: list[str] = Field(default_factory=list)


class CollectionResponse(BaseModel):
    """Response schema for collection data."""

    name: str
    description: str
    photo_hashes: list[str]
    updated_at: str


class DeleteResponse(BaseModel):
    """Response for delete operations."""

    deleted: bool
    file_hash: str
    message: str


class IndexFolderRequest(BaseModel):
    """Request schema for indexing photos from a local directory."""

    folder_path: str = Field(description="Absolute path to directory containing photos")
    num_workers: int = Field(default=4, ge=1, le=32, description="Concurrent extraction threads")


class JobResponse(BaseModel):
    """A background job (PMO-18): poll ``GET /api/jobs/{id}`` until ``status`` is final.

    ``processed`` counts successes and failures; ``failed_count`` is the failures so
    far. ``counts`` holds the kind-specific final numbers (for an index job:
    ``total``, ``indexed``, ``failed``). ``errors`` lists per-file messages, capped.
    """

    id: str
    kind: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    folder_path: str
    total: int | None = None
    processed: int = 0
    failed_count: int = 0
    counts: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    message: str = ""
    cancel_requested: bool = False
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class FacetCountSchema(BaseModel):
    """One value of a facet and how many records carry it."""

    name: str
    count: int


class GpsBoundsSchema(BaseModel):
    """The bounding box of every geotagged record."""

    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


class FacetsResponse(BaseModel):
    """Aggregate counts used to populate filter UIs (PMO-10)."""

    cameras: list[FacetCountSchema] = Field(default_factory=list)
    tags: list[FacetCountSchema] = Field(default_factory=list)
    years: list[FacetCountSchema] = Field(default_factory=list)
    gps_bounds: GpsBoundsSchema | None = None
