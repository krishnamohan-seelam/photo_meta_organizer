"""Duplicates: photos kept at more than one path (ADR-003 R11, ticket 03).

The view reports and hides only. Hiding a copy takes it out of the duplicates count and
the reclaimable total; the File stays recorded and nothing on disk is touched or deleted.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from photo_meta_organizer.api.dependencies import get_repository
from photo_meta_organizer.api.routes.photos_router import path_schema
from photo_meta_organizer.api.schemas import (
    DuplicateGroupSchema,
    DuplicatesResponse,
    HideFileRequest,
)
from photo_meta_organizer.application.interfaces.image_repository import (
    ImageMetadataRepository,
)

duplicates_router = APIRouter(prefix="/api/duplicates", tags=["duplicates"])
files_router = APIRouter(prefix="/api/files", tags=["duplicates"])


@duplicates_router.get("", response_model=DuplicatesResponse, summary="List duplicate photos")
def list_duplicates(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    repository: ImageMetadataRepository = Depends(get_repository),
) -> DuplicatesResponse:
    """Photos kept at more than one path, the biggest saving first.

    A copy counts when its file is on disk and not hidden. ``reclaimable_bytes`` is what all
    but one copy take, per group and in total (over every group, not just this page). A group
    whose extra copies are all hidden is still listed, with one copy and nothing to reclaim,
    and its hidden files can be shown again.
    """
    page = repository.duplicate_groups(limit, offset)
    return DuplicatesResponse(
        groups=[
            DuplicateGroupSchema(
                file_hash=g.file_hash,
                size_bytes=g.size_bytes,
                reclaimable_bytes=g.reclaimable_bytes,
                copies=g.copies,
                files=[path_schema(f) for f in g.files],
            )
            for g in page.groups
        ],
        total_groups=page.total_groups,
        total_listed=page.total_listed,
        reclaimable_bytes=page.reclaimable_bytes,
    )


@files_router.post("/hide", status_code=204, summary="Hide a copy, or show it again")
def hide_file(
    request: HideFileRequest,
    repository: ImageMetadataRepository = Depends(get_repository),
) -> Response:
    """Hide one copy from the duplicates view (``hidden`` true), or show it again.

    Only the library's record changes: the file on disk is never touched. 404 if the path
    is not a recorded file.
    """
    if not repository.set_file_hidden(request.path, request.hidden):
        raise HTTPException(status_code=404, detail=f"'{request.path}' is not in the library.")
    return Response(status_code=204)
