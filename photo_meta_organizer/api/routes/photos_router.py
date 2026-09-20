"""Photo metadata REST API router.

Endpoints:
    GET   /api/photos                 - List all photos with optional filters/pagination
    GET   /api/photos/{file_hash}     - Get single photo metadata by SHA-256 hash
    GET   /api/photos/{file_hash}/thumbnail - Stream cached WebP thumbnail
    GET   /api/photos/{file_hash}/raw - Stream full-resolution source image
    PATCH /api/photos/{file_hash}     - Update rating, flag, or labels for a photo
    POST  /api/photos/batch           - Atomic batch operations across photos
    GET   /api/collections            - List all curated collections
    POST  /api/collections            - Create or update a curated collection
    POST  /api/search                 - Advanced search with SearchRequest body
    DELETE /api/photos/{file_hash}    - Remove photo from index
"""

import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse

from photo_meta_organizer.api.schemas import (
    BatchPhotoRequest,
    BatchPhotoResponse,
    CollectionCreateRequest,
    CollectionResponse,
    DeleteResponse,
    DimensionsSchema,
    ExifDataSchema,
    FileInfoSchema,
    GpsCoordinatesSchema,
    IndexFolderRequest,
    IndexFolderResponse,
    PaginatedPhotosResponse,
    PatchPhotoRequest,
    PhotoMetadataResponse,
    SearchRequest,
)
from photo_meta_organizer.application.use_cases.parallel_index_photos_use_case import (
    ParallelIndexPhotosUseCase,
)
from photo_meta_organizer.application.use_cases.search_photos_use_case import (
    PaginatedResult,
    SearchPhotosQuery,
    SearchPhotosUseCase,
)
from photo_meta_organizer.domain.models import ImageMetadata
from photo_meta_organizer.infrastructure.extractors.disk_metadata_extractor import (
    DiskMetaDataExtractor,
)
from photo_meta_organizer.infrastructure.repositories.tinydb_repository import (
    TinyDBRepository,
)
from photo_meta_organizer.infrastructure.retriever.local_disk_retriever import (
    LocalDiskRetriever,
)
from photo_meta_organizer.infrastructure.thumbnail_service import ThumbnailService

photos_router = APIRouter(prefix="/api/photos", tags=["photos"])
collections_router = APIRouter(prefix="/api/collections", tags=["collections"])
search_router = APIRouter(prefix="/api", tags=["search"])
index_router = APIRouter(prefix="/api/index", tags=["indexing"])

_thumbnail_service = ThumbnailService()


def _to_response(metadata: ImageMetadata) -> PhotoMetadataResponse:
    """Convert domain ImageMetadata to PhotoMetadataResponse schema."""
    exif = metadata.exif
    location_schema = None
    if exif.location:
        location_schema = GpsCoordinatesSchema(
            latitude=exif.location.latitude,
            longitude=exif.location.longitude,
            altitude=exif.location.altitude,
            datum=exif.location.datum,
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
        rating=metadata.rating,
        flagged=metadata.flagged,
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


@photos_router.post("/batch", response_model=BatchPhotoResponse, summary="Batch update photos")
def batch_update_photos(
    request: BatchPhotoRequest,
    repository: TinyDBRepository = Depends(),
) -> BatchPhotoResponse:
    """Apply batch actions across multiple photos atomically."""
    count = repository.batch_update(
        request.photo_hashes,
        {"action": request.action, "value": request.value},
    )
    return BatchPhotoResponse(
        updated_count=count,
        action=request.action,
        message=f"Successfully applied '{request.action}' to {count} photo(s).",
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


@photos_router.get(
    "/{file_hash}/thumbnail",
    summary="Stream WebP thumbnail",
)
def get_photo_thumbnail(
    file_hash: str,
    w: int = Query(default=320, ge=64, le=1200, description="Thumbnail width in pixels"),
    h: int = Query(default=320, ge=64, le=1200, description="Thumbnail height in pixels"),
    repository: TinyDBRepository = Depends(),
):
    """Stream an optimized WebP thumbnail for the specified photo."""
    metadata = repository.get_by_filehash(file_hash)
    if metadata is None:
        raise HTTPException(status_code=404, detail=f"Photo with hash '{file_hash}' not found.")

    thumb_bytes = _thumbnail_service.generate_thumbnail(
        source_path=metadata.file_info.path,
        file_hash=file_hash,
        width=w,
        height=h,
    )
    if not thumb_bytes:
        raise HTTPException(status_code=404, detail="Thumbnail could not be generated (source file missing).")

    return Response(
        content=thumb_bytes,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@photos_router.get(
    "/{file_hash}/raw",
    summary="Stream full-resolution image",
)
def get_photo_raw(
    file_hash: str,
    repository: TinyDBRepository = Depends(),
):
    """Stream the full-resolution original image from storage."""
    metadata = repository.get_by_filehash(file_hash)
    if metadata is None:
        raise HTTPException(status_code=404, detail=f"Photo with hash '{file_hash}' not found.")

    file_path = metadata.file_info.path
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Source file '{file_path}' does not exist on disk.")

    return FileResponse(
        path=file_path,
        media_type=metadata.file_info.mime_type,
        filename=metadata.file_info.name,
    )


@photos_router.patch(
    "/{file_hash}",
    response_model=PhotoMetadataResponse,
    summary="Update photo metadata",
)
def patch_photo(
    file_hash: str,
    request: PatchPhotoRequest,
    repository: TinyDBRepository = Depends(),
) -> PhotoMetadataResponse:
    """Update user ratings, flags, or tags for a single photo."""
    updates = request.model_dump(exclude_unset=True)
    updated = repository.update_metadata(file_hash, updates)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Photo with hash '{file_hash}' not found.")
    return _to_response(updated)


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


@collections_router.get("", response_model=List[CollectionResponse], summary="List all collections")
def list_collections(
    repository: TinyDBRepository = Depends(),
) -> List[CollectionResponse]:
    """Retrieve all curated photo collections."""
    cols = repository.get_collections()
    return [
        CollectionResponse(
            name=c.get("name", ""),
            description=c.get("description", ""),
            photo_hashes=c.get("photo_hashes", []),
            updated_at=c.get("updated_at", ""),
        )
        for c in cols
    ]


@collections_router.post("", response_model=CollectionResponse, summary="Create or update collection")
def create_collection(
    request: CollectionCreateRequest,
    repository: TinyDBRepository = Depends(),
) -> CollectionResponse:
    """Create or update a named photo collection."""
    saved = repository.save_collection(
        name=request.name,
        photo_hashes=request.photo_hashes,
        description=request.description,
    )
    return CollectionResponse(
        name=saved["name"],
        description=saved["description"],
        photo_hashes=saved["photo_hashes"],
        updated_at=saved["updated_at"],
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


@index_router.post("", response_model=IndexFolderResponse, summary="Index local photo directory")
def index_directory(
    request: IndexFolderRequest,
    repository: TinyDBRepository = Depends(),
) -> IndexFolderResponse:
    """Index image files from a local directory into the metadata repository."""
    folder_path = os.path.abspath(request.folder_path)
    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        raise HTTPException(
            status_code=400,
            detail=f"Directory '{request.folder_path}' does not exist or is not a directory.",
        )

    retriever = LocalDiskRetriever(base_path=folder_path)
    extractor = DiskMetaDataExtractor()
    use_case = ParallelIndexPhotosUseCase(
        retriever=retriever,
        extractor=extractor,
        repository=repository,
        num_workers=request.num_workers,
    )
    results = use_case.execute()
    return IndexFolderResponse(
        indexed_count=len(results),
        folder_path=folder_path,
        message=f"Successfully indexed {len(results)} photo(s) from '{folder_path}'.",
    )

