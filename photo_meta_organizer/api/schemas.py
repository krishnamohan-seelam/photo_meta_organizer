"""Pydantic schemas for API request/response models."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GpsCoordinatesSchema(BaseModel):
    """GPS coordinates for API responses."""

    latitude: float
    longitude: float
    altitude: Optional[float] = None
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

    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    f_stop: Optional[float] = None
    exposure_time: Optional[str] = None
    iso: Optional[int] = None
    focal_length: Optional[str] = None
    captured_at: Optional[datetime] = None
    camera_profile: str = "unknown"
    location: Optional[GpsCoordinatesSchema] = None
    flash_fired: Optional[bool] = None
    focal_length_35mm: Optional[str] = None
    white_balance_mode: Optional[str] = None
    exposure_program: Optional[str] = None
    metering_mode: Optional[str] = None
    orientation: Optional[int] = None
    raw_tags: Dict[str, Any] = Field(default_factory=dict)


class PhotoMetadataResponse(BaseModel):
    """Full photo metadata response schema."""

    file_hash: str
    file_info: FileInfoSchema
    dimensions: DimensionsSchema
    exif: ExifDataSchema
    labels: List[str] = Field(default_factory=list)
    rating: Optional[int] = None
    flagged: bool = False
    added_at: datetime


class PaginatedPhotosResponse(BaseModel):
    """Paginated list of photo metadata."""

    items: List[PhotoMetadataResponse]
    total_count: int
    page: int
    page_size: int
    total_pages: int


class SearchRequest(BaseModel):
    """Advanced search request body schema."""

    search_term: Optional[str] = None
    date_start: Optional[datetime] = None
    date_end: Optional[datetime] = None
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    radius_km: Optional[float] = None
    tags: Optional[List[str]] = None
    city: Optional[str] = None
    rating: Optional[int] = None
    flagged: Optional[bool] = None
    sort_by: str = "captured_at"
    sort_order: str = "asc"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)


class PatchPhotoRequest(BaseModel):
    """Request schema for updating metadata of a single photo."""

    rating: Optional[int] = Field(default=None, ge=1, le=5)
    flagged: Optional[bool] = None
    labels: Optional[List[str]] = None
    add_tags: Optional[List[str]] = None
    remove_tags: Optional[List[str]] = None


class BatchPhotoRequest(BaseModel):
    """Request schema for atomic batch operations across photos."""

    photo_hashes: List[str]
    action: str = Field(description="Action to perform: add_tag, remove_tag, set_rating, set_flag, delete")
    value: Optional[Any] = None


class BatchPhotoResponse(BaseModel):
    """Response schema for batch operations."""

    updated_count: int
    action: str
    message: str


class CollectionCreateRequest(BaseModel):
    """Request schema for creating or updating a collection."""

    name: str
    description: str = ""
    photo_hashes: List[str] = Field(default_factory=list)


class CollectionResponse(BaseModel):
    """Response schema for collection data."""

    name: str
    description: str
    photo_hashes: List[str]
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


class IndexFolderResponse(BaseModel):
    """Response schema for folder indexing operation."""

    indexed_count: int
    folder_path: str
    message: str

