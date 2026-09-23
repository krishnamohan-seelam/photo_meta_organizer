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
from photo_meta_organizer.application.composition import build_local_retriever
from photo_meta_organizer.application.interfaces.collection_repository import (
    CollectionRepository,
)
from photo_meta_organizer.application.interfaces.image_repository import (
    ImageMetadataRepository,
)
from photo_meta_organizer.application.use_cases.parallel_index_photos_use_case import (
    ParallelIndexPhotosUseCase,
)
from photo_meta_organizer.application.use_cases.search_photos_use_case import (
    SearchPhotosQuery,
    SearchPhotosUseCase,
)
from photo_meta_organizer.domain.curation import (
    AddTag,
    CurationCommand,
    RemoveTag,
    SetFlag,
    SetLabels,
    SetRating,
    is_valid_rating,
)
from photo_meta_organizer.domain.models import ImageMetadata
from photo_meta_organizer.infrastructure.extractors.disk_metadata_extractor import (
    DiskMetaDataExtractor,
)
from photo_meta_organizer.infrastructure.thumbnail_service import ThumbnailService

photos_router = APIRouter(prefix="/api/photos", tags=["photos"])
collections_router = APIRouter(prefix="/api/collections", tags=["collections"])
search_router = APIRouter(prefix="/api", tags=["search"])
index_router = APIRouter(prefix="/api/index", tags=["indexing"])

_thumbnail_service = ThumbnailService()


def get_repository() -> ImageMetadataRepository:
    """Placeholder dependency; ``create_app`` overrides this with the shared instance.

    A plain function dependency (rather than the concrete repository class as its
    own dependency) keeps this router from having to know which storage engine is
    behind the ``ImageMetadataRepository`` protocol.
    """
    raise RuntimeError("Repository dependency not configured")


def get_collection_repository() -> CollectionRepository:
    """Placeholder dependency; ``create_app`` overrides this with the shared instance."""
    raise RuntimeError("Collection repository dependency not configured")


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
        # A rating damaged on disk by an older version must not fail the whole listing.
        rating=metadata.rating if is_valid_rating(metadata.rating) else None,
        flagged=metadata.flagged,
        added_at=metadata.added_at,
    )


@photos_router.get("", response_model=PaginatedPhotosResponse, summary="List all photos")
def list_photos(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=50, ge=1, le=500, description="Results per page"),
    sort_by: str = Query(
        default="captured_at",
        description="Sort field: captured_at, size_bytes, camera_model, file_name",
    ),
    sort_order: str = Query(default="asc", description="Sort order: asc or desc"),
    repository: ImageMetadataRepository = Depends(get_repository),
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


_BATCH_ACTION_COMMANDS = {
    "add_tag": AddTag,
    "remove_tag": RemoveTag,
    "set_rating": SetRating,
    "set_flag": SetFlag,
}


@photos_router.post("/batch", response_model=BatchPhotoResponse, summary="Batch update photos")
def batch_update_photos(
    request: BatchPhotoRequest,
    repository: ImageMetadataRepository = Depends(get_repository),
) -> BatchPhotoResponse:
    """Apply one validated curation action to many photos."""
    try:
        if request.action == "delete":
            count = repository.batch_delete(request.photo_hashes)
        else:
            command = _BATCH_ACTION_COMMANDS[request.action](request.value)
            count = repository.apply_batch(request.photo_hashes, command)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    deleting = request.action == "delete"
    return BatchPhotoResponse(
        updated_count=0 if deleting else count,
        deleted_count=count if deleting else 0,
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
    repository: ImageMetadataRepository = Depends(get_repository),
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
    repository: ImageMetadataRepository = Depends(get_repository),
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
        raise HTTPException(
            status_code=404,
            detail="Thumbnail could not be generated (source file missing).",
        )

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
    repository: ImageMetadataRepository = Depends(get_repository),
):
    """Stream the full-resolution original image from storage."""
    metadata = repository.get_by_filehash(file_hash)
    if metadata is None:
        raise HTTPException(status_code=404, detail=f"Photo with hash '{file_hash}' not found.")

    file_path = metadata.file_info.path
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404, detail=f"Source file '{file_path}' does not exist on disk."
        )

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
    repository: ImageMetadataRepository = Depends(get_repository),
) -> PhotoMetadataResponse:
    """Update user ratings, flags, or tags for a single photo."""
    existing = repository.get_by_filehash(file_hash)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Photo with hash '{file_hash}' not found.")

    # An explicit null means "clear" only for the rating; for the other fields it means "no change".
    updates = {
        key: value
        for key, value in request.model_dump(exclude_unset=True).items()
        if value is not None or key == "rating"
    }
    commands: list[CurationCommand] = []
    if "rating" in updates:
        commands.append(SetRating(updates["rating"]))
    if "flagged" in updates:
        commands.append(SetFlag(updates["flagged"]))
    if "labels" in updates:
        commands.append(SetLabels(updates["labels"]))
    for tag in updates.get("add_tags", []):
        commands.append(AddTag(tag))
    for tag in updates.get("remove_tags", []):
        commands.append(RemoveTag(tag))

    updated = existing
    try:
        for command in commands:
            updated = repository.apply(file_hash, command)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(updated)


@photos_router.delete(
    "/{file_hash}",
    response_model=DeleteResponse,
    summary="Delete photo from index",
)
def delete_photo(
    file_hash: str,
    repository: ImageMetadataRepository = Depends(get_repository),
    collection_repository: CollectionRepository = Depends(get_collection_repository),
) -> DeleteResponse:
    """Remove a photo from the metadata index by its SHA-256 file hash."""
    deleted = repository.delete(file_hash)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Photo with hash '{file_hash}' not found.",
        )
    collection_repository.remove_photo_from_all(file_hash)
    return DeleteResponse(
        deleted=True,
        file_hash=file_hash,
        message=f"Photo '{file_hash}' removed from index.",
    )


@collections_router.get("", response_model=list[CollectionResponse], summary="List all collections")
def list_collections(
    collection_repository: CollectionRepository = Depends(get_collection_repository),
) -> list[CollectionResponse]:
    """Retrieve all curated photo collections."""
    return [
        CollectionResponse(
            name=c.name,
            description=c.description,
            photo_hashes=c.photo_hashes,
            updated_at=c.updated_at,
        )
        for c in collection_repository.list_all()
    ]


@collections_router.post(
    "", response_model=CollectionResponse, summary="Create or update collection"
)
def create_collection(
    request: CollectionCreateRequest,
    collection_repository: CollectionRepository = Depends(get_collection_repository),
) -> CollectionResponse:
    """Create or update a named photo collection."""
    saved = collection_repository.save(
        name=request.name,
        photo_hashes=request.photo_hashes,
        description=request.description,
    )
    return CollectionResponse(
        name=saved.name,
        description=saved.description,
        photo_hashes=saved.photo_hashes,
        updated_at=saved.updated_at,
    )


@search_router.post(
    "/search",
    response_model=PaginatedPhotosResponse,
    summary="Advanced photo search",
)
def search_photos(
    request: SearchRequest,
    repository: ImageMetadataRepository = Depends(get_repository),
) -> PaginatedPhotosResponse:
    """Advanced multi-criteria photo search with filtering, sorting, and pagination."""
    query = SearchPhotosQuery(
        search_term=request.search_term,
        date_start=request.date_start,
        date_end=request.date_end,
        camera_make=request.camera_make,
        camera_model=request.camera_model,
        location_lat=request.location_lat,
        location_lon=request.location_lon,
        radius_km=request.radius_km,
        tags=request.tags,
        rating=request.rating,
        flagged=request.flagged,
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
    repository: ImageMetadataRepository = Depends(get_repository),
) -> IndexFolderResponse:
    """Index image files from a local directory into the metadata repository."""
    folder_path = os.path.abspath(request.folder_path)
    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        raise HTTPException(
            status_code=400,
            detail=f"Directory '{request.folder_path}' does not exist or is not a directory.",
        )

    retriever = build_local_retriever(folder_path)
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
