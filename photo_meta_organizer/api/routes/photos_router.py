"""Photo metadata REST API router.

Endpoints:
    GET  /api/photos             - List all photos with optional filters/pagination
    GET  /api/photos/{file_hash} - Get single photo metadata by SHA-256 hash
    POST /api/search             - Advanced search with SearchRequest body
    DELETE /api/photos/{file_hash} - Remove photo from index
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from photo_meta_organizer.api.schemas import (
    DeleteResponse,
    PaginatedPhotosResponse,
    PhotoMetadataResponse,
    SearchRequest,
)
from photo_meta_organizer.application.use_cases.search_photos_use_case import (
    PaginatedResult,
    SearchPhotosQuery,
    SearchPhotosUseCase,
)
from photo_meta_organizer.domain.models import ImageMetadata
from photo_meta_organizer.infrastructure.repositories.tinydb_repository import (
    TinyDBRepository,
)

photos_router = APIRouter(prefix="/api/photos", tags=["photos"])
search_router = APIRouter(prefix="/api", tags=["search"])


def _to_response(metadata: ImageMetadata) -> PhotoMetadataResponse:
    """Convert domain ImageMetadata to PhotoMetadataResponse schema."""
    exif = metadata.exif
    location_schema = None
    if exif.location:
        from photo_meta_organizer.api.schemas import GpsCoordinatesSchema
        location_schema = GpsCoordinatesSchema(
            latitude=exif.location.latitude,
            longitude=exif.location.longitude,
            altitude=exif.location.altitude,
            datum=exif.location.datum,
        )

    from photo_meta_organizer.api.schemas import (
        DimensionsSchema,
        ExifDataSchema,
        FileInfoSchema,
    )

    return PhotoMetadataResponse(
        file_hash=metadata.file_hash,
        file_info=FileInfoSchema(
            name=metadata.file_info.name,
            path=metadata.file_info.path,
            size_bytes=metadata.file_info.size_bytes,
            mime_type=metadata.file_info.mime_type,
        ),
        dimensions=DimensionsSchema(
            width=metadata.dimensions.width,
            height=metadata.dimensions.height,
        ),
        exif=ExifDataSchema(
            camera_make=exif.camera_make,
            camera_model=exif.camera_model,
            f_stop=exif.f_stop,
            exposure_time=exif.exposure_time,
            iso=exif.iso,
            focal_length=exif.focal_length,
            captured_at=exif.captured_at,
            camera_profile=exif.camera_profile.value,
            location=location_schema,
            flash_fired=exif.flash_fired,
            focal_length_35mm=exif.focal_length_35mm,
            white_balance_mode=exif.white_balance_mode,
            exposure_program=exif.exposure_program,
            metering_mode=exif.metering_mode,
            orientation=exif.orientation,
            raw_tags=dict(exif.raw_tags) if exif.raw_tags else {},
        ),
        labels=list(metadata.labels),
        added_at=metadata.added_at,
    )


@photos_router.get("", response_model=PaginatedPhotosResponse, summary="List all photos")
def list_photos(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=50, ge=1, le=500, description="Results per page"),
    sort_by: str = Query(default="captured_at", description="Sort field: captured_at, size_bytes, camera_model, file_name"),
    sort_order: str = Query(default="asc", description="Sort order: asc or desc"),
    repository: TinyDBRepository = Depends(),
) -> PaginatedPhotosResponse:
    """List all indexed photos with optional sorting and pagination."""
    query = SearchPhotosQuery(
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    use_case = SearchPhotosUseCase(repository=repository)
    result = use_case.execute(query)
    return PaginatedPhotosResponse(
        items=[_to_response(m) for m in result.items],
        total_count=result.total_count,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
    )


@photos_router.get(
    "/{file_hash}",
    response_model=PhotoMetadataResponse,
    summary="Get photo by SHA-256 hash",
)
def get_photo(
    file_hash: str,
    repository: TinyDBRepository = Depends(),
) -> PhotoMetadataResponse:
    """Retrieve a single photo's metadata by its SHA-256 file hash."""
    metadata = repository.get_by_filehash(file_hash)
    if metadata is None:
        raise HTTPException(
            status_code=404,
            detail=f"Photo with hash '{file_hash}' not found.",
        )
    return _to_response(metadata)


@photos_router.delete(
    "/{file_hash}",
    response_model=DeleteResponse,
    summary="Delete photo from index",
)
def delete_photo(
    file_hash: str,
    repository: TinyDBRepository = Depends(),
) -> DeleteResponse:
    """Remove a photo from the metadata index by its SHA-256 file hash."""
    deleted = repository.delete(file_hash)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Photo with hash '{file_hash}' not found.",
        )
    return DeleteResponse(
        deleted=True,
        file_hash=file_hash,
        message=f"Photo '{file_hash}' removed from index.",
    )


@search_router.post(
    "/search",
    response_model=PaginatedPhotosResponse,
    summary="Advanced photo search",
)
def search_photos(
    request: SearchRequest,
    repository: TinyDBRepository = Depends(),
) -> PaginatedPhotosResponse:
    """Advanced multi-criteria photo search with filtering, sorting, and pagination."""
    query = SearchPhotosQuery(
        date_start=request.date_start,
        date_end=request.date_end,
        camera_make=request.camera_make,
        camera_model=request.camera_model,
        location_lat=request.location_lat,
        location_lon=request.location_lon,
        radius_km=request.radius_km,
        tags=request.tags,
        sort_by=request.sort_by,
        sort_order=request.sort_order,
        page=request.page,
        page_size=request.page_size,
    )
    use_case = SearchPhotosUseCase(repository=repository)
    result = use_case.execute(query)
    return PaginatedPhotosResponse(
        items=[_to_response(m) for m in result.items],
        total_count=result.total_count,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
    )
