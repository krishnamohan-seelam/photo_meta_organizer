"""Photo metadata REST API router.

Endpoints:
    GET   /api/photos                 - List all photos with optional filters/pagination
    GET   /api/photos/{file_hash}     - Get single photo metadata by SHA-256 hash
    GET   /api/photos/{file_hash}/thumbnail - Stream cached WebP thumbnail
    GET   /api/photos/{file_hash}/preview   - Large WebP for the viewer (any format)
    GET   /api/photos/{file_hash}/raw - Stream full-resolution source image
    PATCH /api/photos/{file_hash}     - Update rating, flag, or labels for a photo
    POST  /api/photos/batch           - Atomic batch operations across photos
    GET   /api/collections            - List all curated collections
    POST  /api/collections            - Create or update a curated collection
    POST  /api/search/ids             - Hash and size of every match (select all)
    POST  /api/search                 - Advanced search with SearchRequest body
    GET   /api/facets                 - Aggregate camera/tag/year counts and GPS bounds
    DELETE /api/photos/{file_hash}    - Remove photo from index
    POST  /api/index                  - Start a background index job (202 + job)
    POST  /api/sync                   - Start a background incremental sync job (202 + job)
    GET   /api/jobs                   - Recent background jobs, newest first
    GET   /api/jobs/{job_id}          - One job's progress and result
    POST  /api/jobs/{job_id}/cancel   - Ask a running job to stop
    POST  /api/jobs/{job_id}/resume   - Run an interrupted job again
    POST  /api/jobs/{job_id}/dismiss  - Give up on an interrupted job
"""

import math
import os
from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse

from photo_meta_organizer.api.dependencies import (
    Services,
    get_collection_repository,
    get_job_manager,
    get_place_namer,
    get_repository,
    get_services,
    get_thumbnail_service,
)
from photo_meta_organizer.api.job_factory import require_model, require_runtime, work_for
from photo_meta_organizer.api.schemas import (
    BatchPhotoRequest,
    BatchPhotoResponse,
    BoundingBoxSchema,
    CollectionCreateRequest,
    CollectionResponse,
    DeleteResponse,
    DimensionsSchema,
    ExifDataSchema,
    FacetCountSchema,
    FacetsResponse,
    FileInfoSchema,
    GeoClusterSchema,
    GeoClustersRequest,
    GeoClustersResponse,
    GpsBoundsSchema,
    GpsCoordinatesSchema,
    IndexFolderRequest,
    JobResponse,
    LibraryStatsSchema,
    PaginatedPhotosResponse,
    PatchPhotoRequest,
    PhotoIdSchema,
    PhotoMetadataResponse,
    PhotoPathSchema,
    RestorePhotosRequest,
    RestorePhotosResponse,
    SearchRequest,
    SyncFolderRequest,
)
from photo_meta_organizer.application.geo import cell_degrees_for_zoom, place_scope_for_zoom
from photo_meta_organizer.application.interfaces.collection_repository import (
    CollectionRepository,
)
from photo_meta_organizer.application.interfaces.image_embedder import EmbedderUnavailableError
from photo_meta_organizer.application.interfaces.image_repository import (
    ImageMetadataRepository,
)
from photo_meta_organizer.application.interfaces.place_namer import PlaceNamer
from photo_meta_organizer.application.interfaces.search_types import BoundingBox
from photo_meta_organizer.application.jobs import (
    Job,
    JobConflictError,
    JobManager,
    JobStateError,
    Work,
)
from photo_meta_organizer.application.ranking import RankedHit
from photo_meta_organizer.application.trash import UNDO_SECONDS
from photo_meta_organizer.application.use_cases.search_photos_use_case import (
    SearchPhotosQuery,
    SearchPhotosUseCase,
)
from photo_meta_organizer.application.use_cases.semantic_search_use_case import (
    AnalysisNotReadyError,
    SemanticSearchUseCase,
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
from photo_meta_organizer.domain.models import ImageMetadata, StoredFile
from photo_meta_organizer.infrastructure.thumbnail_service import ThumbnailService

photos_router = APIRouter(prefix="/api/photos", tags=["photos"])
collections_router = APIRouter(prefix="/api/collections", tags=["collections"])
search_router = APIRouter(prefix="/api", tags=["search"])
index_router = APIRouter(prefix="/api/index", tags=["indexing"])
jobs_router = APIRouter(prefix="/api/jobs", tags=["jobs"])
sync_router = APIRouter(prefix="/api/sync", tags=["indexing"])


def path_schema(file: StoredFile) -> PhotoPathSchema:
    """One recorded File as the API shows it."""
    return PhotoPathSchema(
        path=file.path,
        name=os.path.basename(file.path),
        size_bytes=file.size_bytes,
        missing=file.missing_since is not None,
        hidden=file.hidden_at is not None,
    )


def to_responses(
    items: Sequence[ImageMetadata], repository: ImageMetadataRepository
) -> list[PhotoMetadataResponse]:
    """Responses for ``items`` with every photo's paths, from one query for the lot."""
    files = repository.files_of([m.file_hash for m in items])
    return [_to_response(m, files.get(m.file_hash, [])) for m in items]


def _to_response(
    metadata: ImageMetadata, files: Sequence[StoredFile] = ()
) -> PhotoMetadataResponse:
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
            missing_since=metadata.file_info.missing_since,
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
        paths=[path_schema(f) for f in files],
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
        items=to_responses(result.items, repository),
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
            count = repository.remove_assets(request.photo_hashes)
        else:
            command = _BATCH_ACTION_COMMANDS[request.action](request.value)
            count = repository.apply_batch(request.photo_hashes, command)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    deleting = request.action == "delete"
    return BatchPhotoResponse(
        updated_count=0 if deleting else count,
        deleted_count=count if deleting else 0,
        undo_seconds=UNDO_SECONDS if deleting else 0,
        action=request.action,
        message=(
            f"Removed {count} photo(s) from the library (files on disk are untouched)."
            if deleting
            else f"Successfully applied '{request.action}' to {count} photo(s)."
        ),
    )


@photos_router.post(
    "/restore", response_model=RestorePhotosResponse, summary="Undo removing photos"
)
def restore_photos(
    request: RestorePhotosRequest,
    repository: ImageMetadataRepository = Depends(get_repository),
) -> RestorePhotosResponse:
    """Bring back photos removed less than ``undo_seconds`` ago, with their ratings, labels and
    collections. Ones already purged are gone for good and are not counted."""
    return RestorePhotosResponse(restored_count=repository.restore_assets(request.photo_hashes))


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
    return to_responses([metadata], repository)[0]


@photos_router.get(
    "/{file_hash}/thumbnail",
    summary="Stream WebP thumbnail",
)
def get_photo_thumbnail(
    file_hash: str,
    w: int = Query(default=320, ge=64, le=1200, description="Thumbnail width in pixels"),
    h: int = Query(default=320, ge=64, le=1200, description="Thumbnail height in pixels"),
    repository: ImageMetadataRepository = Depends(get_repository),
    thumbnails: ThumbnailService = Depends(get_thumbnail_service),
) -> Response:
    """Stream an optimized WebP thumbnail for the specified photo."""
    metadata = repository.get_by_filehash(file_hash)
    if metadata is None:
        raise HTTPException(status_code=404, detail=f"Photo with hash '{file_hash}' not found.")

    return _webp_response(thumbnails, metadata.file_info.path, file_hash, w, h)


# Long edge of the viewer image: sharp on a large screen, far smaller than a RAW.
PREVIEW_SIZE = 2048


@photos_router.get(
    "/{file_hash}/preview",
    summary="Stream a large WebP preview for the viewer",
)
def get_photo_preview(
    file_hash: str,
    repository: ImageMetadataRepository = Depends(get_repository),
    thumbnails: ThumbnailService = Depends(get_thumbnail_service),
) -> Response:
    """A browser-renderable image of any indexed format (HEIC and RAW included, PMO-23).

    Up to 2048 px on the long edge, upright, cached like thumbnails. ``/raw`` returns
    the original bytes, which a browser cannot show for HEIC or RAW.
    """
    metadata = repository.get_by_filehash(file_hash)
    if metadata is None:
        raise HTTPException(status_code=404, detail=f"Photo with hash '{file_hash}' not found.")
    return _webp_response(
        thumbnails, metadata.file_info.path, file_hash, PREVIEW_SIZE, PREVIEW_SIZE
    )


def _webp_response(
    thumbnails: ThumbnailService, source_path: str, file_hash: str, width: int, height: int
) -> Response:
    thumb_bytes = thumbnails.generate_thumbnail(
        source_path=source_path,
        file_hash=file_hash,
        width=width,
        height=height,
    )
    if not thumb_bytes:
        raise HTTPException(
            status_code=404,
            detail="Image could not be generated (source file missing or not decodable).",
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
) -> Response:
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

    updated: ImageMetadata | None = existing
    try:
        for command in commands:
            updated = repository.apply(file_hash, command)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Photo with hash '{file_hash}' not found.")
    return to_responses([updated], repository)[0]


@photos_router.delete(
    "/{file_hash}",
    response_model=DeleteResponse,
    summary="Remove a photo from the library",
)
def delete_photo(
    file_hash: str,
    repository: ImageMetadataRepository = Depends(get_repository),
) -> DeleteResponse:
    """Remove a photo from the library by its SHA-256 file hash. The file on disk is untouched.

    The photo can be brought back with ``POST /api/photos/restore`` for ``undo_seconds``; after
    that it is gone for good (and scans leave the file alone).
    """
    if repository.get_by_filehash(file_hash) is None or not repository.remove_assets([file_hash]):
        raise HTTPException(
            status_code=404,
            detail=f"Photo with hash '{file_hash}' not found.",
        )
    return DeleteResponse(
        deleted=True,
        file_hash=file_hash,
        undo_seconds=UNDO_SECONDS,
        message=f"Photo '{file_hash}' removed from the library.",
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


@search_router.get(
    "/facets",
    response_model=FacetsResponse,
    summary="Aggregate counts for filter UIs",
)
def get_facets(
    repository: ImageMetadataRepository = Depends(get_repository),
) -> FacetsResponse:
    """Camera, tag, and year counts (plus GPS bounds) over the whole library."""
    facets = repository.facets()
    gps_bounds = (
        GpsBoundsSchema(
            min_lat=facets.gps_bounds.min_lat,
            max_lat=facets.gps_bounds.max_lat,
            min_lon=facets.gps_bounds.min_lon,
            max_lon=facets.gps_bounds.max_lon,
        )
        if facets.gps_bounds
        else None
    )
    return FacetsResponse(
        cameras=[FacetCountSchema(name=f.name, count=f.count) for f in facets.cameras],
        tags=[FacetCountSchema(name=f.name, count=f.count) for f in facets.tags],
        years=[FacetCountSchema(name=f.name, count=f.count) for f in facets.years],
        gps_bounds=gps_bounds,
        isos=[FacetCountSchema(name=f.name, count=f.count) for f in facets.isos],
        stats=LibraryStatsSchema(**vars(facets.stats)),
    )


@search_router.post(
    "/search",
    response_model=PaginatedPhotosResponse,
    summary="Advanced photo search",
)
def search_photos(
    request: SearchRequest,
    services: Services = Depends(get_services),
) -> PaginatedPhotosResponse:
    """Advanced multi-criteria photo search with filtering, sorting, and pagination.

    With ``rank``, the photos that pass the filters are ranked by meaning instead of sorted:
    page 1 returns a ``rank_token`` and each item's score, later pages send the token back
    (410 once it has expired: search again from page 1).
    """
    repository = services.repository
    if request.rank is None:
        result = SearchPhotosUseCase(repository=repository).execute(_search_query(request))
        return PaginatedPhotosResponse(
            items=to_responses(result.items, repository),
            total_count=result.total_count,
            page=result.page,
            page_size=result.page_size,
            total_pages=result.total_pages,
        )
    token, hits = _ranking(request, services)
    start = (request.page - 1) * request.page_size
    page_hits = hits[start : start + request.page_size]
    found = [(repository.get_by_filehash(h.file_hash), h.score) for h in page_hits]
    kept = [(photo, score) for photo, score in found if photo is not None]  # removed meanwhile
    return PaginatedPhotosResponse(
        items=to_responses([photo for photo, _ in kept], repository),
        total_count=len(hits),
        page=request.page,
        page_size=request.page_size,
        total_pages=_page_count(len(hits), request.page_size),
        scores=[score for _, score in kept],
        rank_token=token,
    )


def _page_count(total: int, page_size: int) -> int:
    return max(1, math.ceil(total / page_size))


def _ranking_key(request: SearchRequest) -> str:
    """What a ranking depends on: the filters and the rank, not the page asked for."""
    return request.model_dump_json(exclude={"page", "page_size", "rank_token"})


def _ranking(request: SearchRequest, services: Services) -> tuple[str | None, list[RankedHit]]:
    """The ranked list ``request`` names: its snapshot, or a new ranking.

    A ranking that fits on the page asked for is not kept (there is no later page to serve), so
    small lookups such as the inspector's similar photos do not push out the Library's.
    """
    key = _ranking_key(request)
    if request.rank_token is not None:
        hits = services.rankings.get(request.rank_token, key)
        if hits is None:
            raise HTTPException(
                status_code=410, detail="This search has expired. Search again from page 1."
            )
        return request.rank_token, hits
    hits = _rank(request, services)
    if request.page == 1 and len(hits) <= request.page_size:
        return None, hits
    return services.rankings.put(key, hits), hits


def _rank(request: SearchRequest, services: Services) -> list[RankedHit]:
    rank = request.rank
    if rank is None:
        raise ValueError("not a ranked search")
    require_runtime()
    require_model(services)
    settings = services.settings
    use_case = SemanticSearchUseCase(services.analysis, services.embedder, services.repository)
    try:
        return use_case.rank(
            text=rank.text,
            like_hash=rank.like_hash,
            query=_search_query(request),
            top_n=settings.semantic_top_n,
            margin=settings.semantic_margin,
            everything=rank.everything,
            limit=rank.limit,
        )
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Photo '{rank.like_hash}' not found."
        ) from None
    except AnalysisNotReadyError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    except EmbedderUnavailableError as err:
        raise HTTPException(status_code=503, detail=str(err)) from err


@search_router.post(
    "/search/ids",
    response_model=list[PhotoIdSchema],
    summary="Every photo matching a search (hash and size only)",
)
def search_photo_ids(
    request: SearchRequest,
    services: Services = Depends(get_services),
) -> list[PhotoIdSchema]:
    """All matches of the search, ignoring paging: "select all" across every page (PMO-27).

    A ranked search returns its ranked list, best first.
    """
    repository = services.repository
    query = _search_query(request)
    query.page, query.page_size = 1, max(1, repository.count())
    result = SearchPhotosUseCase(repository=repository).execute(query)
    sizes = {m.file_hash: m.file_info.size_bytes for m in result.items}
    if request.rank is None:
        return [PhotoIdSchema(file_hash=h, size_bytes=size) for h, size in sizes.items()]
    # Ranked afresh (or from the token) without keeping a new snapshot.
    hits = (
        _ranking(request, services)[1]
        if request.rank_token is not None
        else _rank(request, services)
    )
    return [
        PhotoIdSchema(file_hash=h.file_hash, size_bytes=sizes[h.file_hash])
        for h in hits
        if h.file_hash in sizes
    ]


@search_router.post(
    "/geo/clusters",
    response_model=GeoClustersResponse,
    summary="Map clusters of the geotagged photos matching a search",
)
def geo_clusters(
    request: GeoClustersRequest,
    repository: ImageMetadataRepository = Depends(get_repository),
    places: PlaceNamer = Depends(get_place_namer),
) -> GeoClustersResponse:
    """Grid clusters sized for the map's zoom level, each labelled with its nearest place."""
    clusters = repository.geo_clusters(
        _search_query(request), _to_box(request.bbox), cell_degrees_for_zoom(request.zoom)
    )
    scope = place_scope_for_zoom(request.zoom)
    return GeoClustersResponse(
        clusters=[
            GeoClusterSchema(
                latitude=c.latitude,
                longitude=c.longitude,
                count=c.count,
                representative_hash=c.representative_hash,
                label=places.name(c.latitude, c.longitude, scope),
            )
            for c in clusters
        ],
        total_count=sum(c.count for c in clusters),
    )


def _to_box(box: BoundingBoxSchema | None) -> BoundingBox | None:
    if box is None:
        return None
    return BoundingBox(south=box.south, west=box.west, north=box.north, east=box.east)


def _search_query(request: SearchRequest) -> SearchPhotosQuery:
    return SearchPhotosQuery(
        search_term=request.search_term,
        date_start=request.date_start,
        date_end=request.date_end,
        camera_make=request.camera_make,
        camera_model=request.camera_model,
        camera_makes=request.camera_makes,
        has_capture_date=request.has_capture_date,
        has_location=request.has_location,
        within=_to_box(request.within),
        collection=request.collection,
        ai_tag=request.ai_tag,
        duplicates=request.duplicates,
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


def job_response(job: Job) -> JobResponse:
    return JobResponse(
        id=job.id,
        kind=job.kind,
        status=job.status.value,
        folder_path=job.folder_path,
        total=job.total,
        processed=job.processed,
        failed_count=job.failed_count,
        counts=job.counts,
        errors=job.errors,
        message=job.message,
        cancel_requested=job.cancel_requested,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def _job_not_found(job_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")


def _existing_directory(folder_path: str) -> str:
    """Absolute path of ``folder_path``, or 400 if it is not an existing directory."""
    absolute = os.path.abspath(folder_path)
    if not os.path.isdir(absolute):
        raise HTTPException(
            status_code=400,
            detail=f"Directory '{folder_path}' does not exist or is not a directory.",
        )
    return absolute


def _submit(
    jobs: JobManager, kind: str, folder_path: str, work: Work, params: dict[str, Any]
) -> JobResponse:
    """Start a job, storing ``params`` so it can be resumed (409 if its folder is busy)."""
    try:
        return job_response(jobs.submit(kind, folder_path, work, params=params))
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@index_router.post(
    "",
    response_model=JobResponse,
    status_code=202,
    summary="Start indexing a local photo directory",
)
def index_directory(
    request: IndexFolderRequest, services: Services = Depends(get_services)
) -> JobResponse:
    """Start a background index job and return it at once (202).

    An index is a scan that adds new and changed files and never removes any; files
    it already knows unchanged are skipped.

    Poll ``GET /api/jobs/{id}`` for progress and the final counts, including
    per-file errors. A second job on the same (or an overlapping) folder while
    one is running is refused with 409.
    """
    folder_path = _existing_directory(request.folder_path)
    # An index is a scan that never removes anything (ADR-003 R4).
    params: dict[str, Any] = {"workers": request.num_workers}
    work = work_for("index", folder_path, params, services)
    return _submit(services.jobs, "index", folder_path, work, params)


@sync_router.post(
    "",
    response_model=JobResponse,
    status_code=202,
    summary="Start an incremental sync of a local photo directory",
)
def sync_directory(
    request: SyncFolderRequest, services: Services = Depends(get_services)
) -> JobResponse:
    """Re-scan a folder and apply only what changed (NEW / MODIFIED / DELETED).

    Returns a job at once (202); its final ``counts`` report ``new``, ``modified``,
    ``deleted``, ``missing``, ``found_again`` and ``unchanged``. Files the scan did not
    find are flagged missing, and removed only with ``cleanup_deleted``; ``dry_run``
    reports the counts and writes nothing. Only files under ``folder_path`` are
    considered, so photos indexed from other folders are never affected.
    """
    folder_path = _existing_directory(request.folder_path)
    params: dict[str, Any] = {
        "remove_missing": request.cleanup_deleted,
        "reprocess_modified": request.reprocess_modified,
        "index_new": request.index_new,
        "dry_run": request.dry_run,
        "rehash": request.rehash,
        "reextract": request.reextract,
    }
    work = work_for("sync", folder_path, params, services)
    return _submit(services.jobs, "sync", folder_path, work, params)


@jobs_router.get("", response_model=list[JobResponse], summary="List recent jobs")
def list_jobs(jobs: JobManager = Depends(get_job_manager)) -> list[JobResponse]:
    """Recent background jobs, newest first. They are stored in the library, so they
    survive a restart; one that was running then is listed as ``interrupted``."""
    return [job_response(j) for j in jobs.list()]


@jobs_router.get("/{job_id}", response_model=JobResponse, summary="Get a job")
def get_job(job_id: str, jobs: JobManager = Depends(get_job_manager)) -> JobResponse:
    """Progress and, once finished, the result of one job."""
    try:
        return job_response(jobs.get(job_id))
    except KeyError:
        raise _job_not_found(job_id) from None


@jobs_router.post(
    "/{job_id}/cancel", response_model=JobResponse, status_code=202, summary="Cancel a job"
)
def cancel_job(job_id: str, jobs: JobManager = Depends(get_job_manager)) -> JobResponse:
    """Ask a running job to stop. It finishes the files in hand, then reports ``cancelled``.

    Cancelling a job that already finished is a no-op that returns it unchanged.
    """
    try:
        return job_response(jobs.cancel(job_id))
    except KeyError:
        raise _job_not_found(job_id) from None


@jobs_router.post(
    "/{job_id}/pause", response_model=JobResponse, status_code=202, summary="Pause a job"
)
def pause_job(job_id: str, jobs: JobManager = Depends(get_job_manager)) -> JobResponse:
    """Ask a running job to stop and wait. It finishes the file in hand, then shows as
    ``interrupted``, and ``POST /api/jobs/{id}/resume`` carries on where it left off.

    404 for an unknown job, 409 if it is not running.
    """
    try:
        return job_response(jobs.pause(job_id))
    except KeyError:
        raise _job_not_found(job_id) from None
    except JobStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@jobs_router.post(
    "/{job_id}/resume", response_model=JobResponse, status_code=202, summary="Resume a job"
)
def resume_job(job_id: str, services: Services = Depends(get_services)) -> JobResponse:
    """Run an interrupted job again with the options it was started with (202).

    Cheap because the work is idempotent: a scan skips files it already has unchanged,
    an analysis takes only the photos still pending (all of them again for a
    ``reanalyze``). 404 for an unknown job, 400 if a scan's folder no longer exists, 409
    if the job is not interrupted or another job holds its folder.
    """
    try:
        job = services.jobs.get(job_id)
        if job.kind in ("index", "sync"):
            _existing_directory(job.folder_path)
        work = work_for(job.kind, job.folder_path, job.params, services)
        return job_response(services.jobs.resume(job_id, work))
    except KeyError:
        raise _job_not_found(job_id) from None
    except (JobStateError, JobConflictError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@jobs_router.post("/{job_id}/dismiss", response_model=JobResponse, summary="Dismiss a job")
def dismiss_job(job_id: str, jobs: JobManager = Depends(get_job_manager)) -> JobResponse:
    """Give up on an interrupted job: it ends ``cancelled`` and is not offered again.

    404 for an unknown job, 409 if it is not interrupted.
    """
    try:
        return job_response(jobs.dismiss(job_id))
    except KeyError:
        raise _job_not_found(job_id) from None
    except JobStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
