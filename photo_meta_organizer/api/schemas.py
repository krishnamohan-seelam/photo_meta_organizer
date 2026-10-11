"""Pydantic schemas for API request/response models."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from photo_meta_organizer.domain.curation import (
    MAX_RATING,
    MIN_RATING,
    validate_rating,
    validate_tag,
)


class ResponseModel(BaseModel):
    """Base for what the API returns. A field with a default is still always present in a
    response, so the OpenAPI schema marks it required and the generated TypeScript type
    (PMO-30) does not make it optional."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class GpsCoordinatesSchema(ResponseModel):
    """GPS coordinates for API responses."""

    latitude: float
    longitude: float
    altitude: float | None = None
    datum: str = "WGS84"


class FileInfoSchema(ResponseModel):
    """File-level metadata schema for API responses."""

    name: str
    path: str
    size_bytes: int
    mime_type: str


class DimensionsSchema(ResponseModel):
    """Image dimensions schema."""

    width: int
    height: int


class ExifDataSchema(ResponseModel):
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


class PhotoMetadataResponse(ResponseModel):
    """Full photo metadata response schema."""

    file_hash: str
    file_info: FileInfoSchema
    dimensions: DimensionsSchema
    exif: ExifDataSchema
    labels: list[str] = Field(default_factory=list)
    rating: int | None = None
    flagged: bool = False
    added_at: datetime


class PaginatedPhotosResponse(ResponseModel):
    """Paginated list of photo metadata."""

    items: list[PhotoMetadataResponse]
    total_count: int
    page: int
    page_size: int
    total_pages: int


class BoundingBoxSchema(BaseModel):
    """A map area. ``west > east`` means it crosses the 180° meridian."""

    south: float = Field(ge=-90, le=90)
    west: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)


class SearchRequest(BaseModel):
    """Advanced search request body schema."""

    search_term: str | None = None
    date_start: datetime | None = None
    date_end: datetime | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    camera_makes: list[str] | None = Field(
        default=None, description="Any of these makes, matched exactly (camera checkboxes)"
    )
    has_capture_date: bool | None = Field(
        default=None, description="false: only photos with an unknown capture date"
    )
    has_location: bool | None = Field(default=None, description="Only (un)geotagged photos")
    within: BoundingBoxSchema | None = Field(
        default=None, description="Only photos inside this map area"
    )
    collection: str | None = Field(default=None, description="Members of this collection")
    ai_tag: str | None = Field(
        default=None, description="Photos with an open AI suggestion of this label"
    )
    location_lat: float | None = None
    location_lon: float | None = None
    radius_km: float | None = None
    tags: list[str] | None = None
    rating: int | None = None
    flagged: bool | None = None
    sort_by: Literal["captured_at", "size_bytes", "camera_model", "file_name"] = "captured_at"
    sort_order: Literal["asc", "desc"] = "asc"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)


class GeoClustersRequest(SearchRequest):
    """Search filters plus the map viewport: clusters of the geotagged photos that match."""

    bbox: BoundingBoxSchema | None = Field(default=None, description="Visible map area")
    zoom: int = Field(default=2, ge=0, le=20, description="Web-Mercator zoom level")


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


class BatchPhotoResponse(ResponseModel):
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


class CollectionResponse(ResponseModel):
    """Response schema for collection data."""

    name: str
    description: str
    photo_hashes: list[str]
    updated_at: str


class DeleteResponse(ResponseModel):
    """Response for delete operations."""

    deleted: bool
    file_hash: str
    message: str


class IndexFolderRequest(BaseModel):
    """Request schema for indexing photos from a local directory."""

    folder_path: str = Field(description="Absolute path to directory containing photos")
    num_workers: int = Field(default=4, ge=1, le=32, description="Concurrent extraction threads")


class SyncFolderRequest(BaseModel):
    """Request schema for an incremental sync of one folder (PMO-19).

    Only records under ``folder_path`` take part, so syncing one folder never
    touches photos indexed from another.
    """

    folder_path: str = Field(description="Absolute path to the directory to re-scan")
    cleanup_deleted: bool = Field(
        default=False, description="Remove records whose file is gone (off by default)"
    )
    reprocess_modified: bool = Field(default=True, description="Re-extract changed files")
    index_new: bool = Field(default=True, description="Index files not yet in the library")
    dry_run: bool = Field(default=False, description="Report what would change; write nothing")
    rehash: bool = Field(
        default=False, description="Hash every file instead of trusting size+mtime (slow)"
    )
    reextract: bool = Field(
        default=False,
        description=(
            "Re-extract every file already in the library, keeping curation (slow). "
            "Repairs records written by older versions"
        ),
    )


class JobResponse(ResponseModel):
    """A background job (PMO-18): poll ``GET /api/jobs/{id}`` until ``status`` is final.

    ``processed`` counts successes and failures; ``failed_count`` is the failures so
    far. ``counts`` holds the kind-specific final numbers (index: ``total``,
    ``indexed``, ``failed``; sync: ``new``, ``modified``, ``deleted``, ``unchanged``,
    ``fingerprints_refreshed``, ``failed``). ``errors`` lists per-file messages, capped.
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


class FacetCountSchema(ResponseModel):
    """One value of a facet and how many records carry it."""

    name: str
    count: int


class AppConfigResponse(ResponseModel):
    """Deployment settings the UI needs."""

    map_tiles_url: str | None = Field(
        description="Online tile template the user opted into, or null for the offline map"
    )
    map_tiles_attribution: str | None


class AnalysisStatusResponse(ResponseModel):
    """What the AI features need and how far along they are (Phase 5)."""

    runtime_installed: bool = Field(description="The optional 'ai' extra can be imported")
    model_installed: bool
    model_id: str
    model_source: str
    model_licence: str
    download_bytes: int = Field(description="Bytes still to download (0 once installed)")
    total_photos: int
    analyzed_photos: int = Field(description="Photos with an embedding from this model")
    pending_photos: int
    active_job_id: str | None = Field(description="A running model download or analysis")
    active_job_kind: str | None


class ModelDownloadRequest(BaseModel):
    """The explicit consent the download needs: the UI sends it after showing what is fetched."""

    accept: Literal[True] = Field(description="Must be true: you agree to download the model")


class AnalyzeRequest(BaseModel):
    reanalyze: bool = Field(default=False, description="Redo every photo, not only new ones")
    limit: int | None = Field(default=None, ge=1, description="Analyze at most this many photos")
    tags: bool = Field(default=True, description="Also suggest tags")
    retag: bool = Field(
        default=False,
        description="Only recompute suggested tags from the stored embeddings (no photo is opened)",
    )


class SemanticSearchRequest(SearchRequest):
    """Search by meaning: free text, or "photos like this one", plus the usual filters.

    Exactly one of ``text`` and ``like_hash``. Sorting and paging fields are ignored: the
    result is the ``k`` best matches, best first.
    """

    text: str | None = Field(default=None, max_length=500)
    like_hash: str | None = None
    k: int = Field(default=50, ge=1, le=200)

    @model_validator(mode="after")
    def _exactly_one_query(self) -> "SemanticSearchRequest":
        if self.text is not None:
            self.text = self.text.strip()
        if (self.text or None) is None and self.like_hash is None:
            raise ValueError("give either a non-empty text or a like_hash")
        if self.text and self.like_hash is not None:
            raise ValueError("give text or like_hash, not both")
        return self


class SemanticHitSchema(ResponseModel):
    photo: PhotoMetadataResponse
    score: float = Field(description="Cosine similarity, -1 to 1; higher is closer")


class SemanticSearchResponse(ResponseModel):
    items: list[SemanticHitSchema]
    model_id: str


class AiTagSchema(ResponseModel):
    """A label the model suggests for a photo."""

    label: str
    confidence: float
    model_id: str
    status: Literal["suggested", "accepted", "rejected"]


class ResolveAiTagRequest(BaseModel):
    label: str = Field(min_length=1)
    action: Literal["accept", "reject", "reset"] = Field(
        description="accept adds the label to the photo; reject hides the suggestion; "
        "reset reopens a decided one. None of them removes a label."
    )


class AiTagBatchRequest(BaseModel):
    photo_hashes: list[str] = Field(min_length=1)
    labels: list[str] | None = Field(
        default=None, description="Only these labels; omit for every open suggestion"
    )
    action: Literal["accept", "reject"]

    @model_validator(mode="after")
    def _labels_are_real(self) -> "AiTagBatchRequest":
        if self.labels is not None:
            self.labels = [validate_tag(label) for label in self.labels]
        return self


class AiTagBatchResponse(ResponseModel):
    photos_changed: int
    tags_changed: int


class GeoClusterSchema(ResponseModel):
    """Geotagged photos in one map grid cell."""

    latitude: float
    longitude: float
    count: int
    representative_hash: str = Field(description="Most recently captured member (thumbnail)")
    label: str | None = Field(default=None, description="Nearest place, e.g. 'Tokyo, Japan'")


class GeoClustersResponse(ResponseModel):
    clusters: list[GeoClusterSchema]
    total_count: int = Field(description="Geotagged photos represented by the clusters")


class GpsBoundsSchema(ResponseModel):
    """The bounding box of every geotagged record."""

    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


class LibraryStatsSchema(ResponseModel):
    """Whole-library totals (PMO-27)."""

    total_count: int
    flagged_count: int
    geotagged_count: int
    undated_count: int
    total_bytes: int
    avg_megapixels: float


class PhotoIdSchema(ResponseModel):
    """One search match, reduced to what a selection needs."""

    file_hash: str
    size_bytes: int


class FacetsResponse(ResponseModel):
    """Aggregate counts used to populate filter UIs (PMO-10)."""

    cameras: list[FacetCountSchema] = Field(default_factory=list)
    tags: list[FacetCountSchema] = Field(default_factory=list)
    years: list[FacetCountSchema] = Field(default_factory=list)
    gps_bounds: GpsBoundsSchema | None = None
    isos: list[FacetCountSchema] = Field(default_factory=list)
    stats: LibraryStatsSchema


class ExportZipRequest(BaseModel):
    """Photos to bundle as a ZIP of their original files (PMO-28)."""

    photo_hashes: list[str] = Field(min_length=1, max_length=100_000)


class ExportJsonRequest(BaseModel):
    """Photos whose metadata to export; omitted or null means the whole library (PMO-28)."""

    photo_hashes: list[str] | None = Field(default=None, max_length=100_000)
