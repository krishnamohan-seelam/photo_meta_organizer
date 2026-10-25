"""Files the user removed from the library for good, and bringing them back (ticket 12).

Removing a photo is undoable for a short while (``POST /api/photos/restore``). After that the
photo is gone and its files are remembered here, so a scan does not add them again. Restoring
one forgets it and scans its folder; nothing on disk was ever touched.
"""

import os

from fastapi import APIRouter, Depends

from photo_meta_organizer.api.dependencies import Services, get_repository, get_services
from photo_meta_organizer.api.job_factory import scan_work_factory
from photo_meta_organizer.api.schemas import (
    RemovedFileSchema,
    RestoreRemovedRequest,
    RestoreRemovedResponse,
)
from photo_meta_organizer.application.interfaces.image_repository import ImageMetadataRepository
from photo_meta_organizer.application.roots import start_scan

removed_router = APIRouter(prefix="/api/removed", tags=["removed"])


@removed_router.get(
    "", response_model=list[RemovedFileSchema], summary="Files removed from the library"
)
def list_removed(
    repository: ImageMetadataRepository = Depends(get_repository),
) -> list[RemovedFileSchema]:
    """Files removed for good, newest first. Scans skip them while they are unchanged on disk."""
    return [
        RemovedFileSchema(
            path=i.path,
            name=os.path.basename(i.path),
            size_bytes=i.size_bytes,
            removed_at=i.removed_at,
        )
        for i in repository.list_ignored()
    ]


@removed_router.post(
    "/restore", response_model=RestoreRemovedResponse, summary="Bring removed files back"
)
def restore_removed(
    request: RestoreRemovedRequest,
    services: Services = Depends(get_services),
) -> RestoreRemovedResponse:
    """Stop ignoring these files and scan their folders so they are recorded again.

    A folder that is already being scanned is left to that scan; the file is picked up by it
    or by the next one.
    """
    restored = services.repository.forget_ignored(request.paths)
    folders = dict.fromkeys(os.path.dirname(p) for p in request.paths)
    make_work = scan_work_factory(services)
    started = [
        job_id
        for folder in folders
        if os.path.isdir(folder)
        for job_id in [start_scan(services.jobs, make_work, folder)]
        if job_id is not None
    ]
    return RestoreRemovedResponse(restored_count=restored, job_ids=started)
