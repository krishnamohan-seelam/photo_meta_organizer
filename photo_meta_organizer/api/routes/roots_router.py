"""Roots: the folders the library scans on its own (ADR-003 R11, ticket 09).

Adding a root remembers a folder and scans it; every start of the API scans the roots again
(:func:`~photo_meta_organizer.application.roots.scan_roots`), so users never have to know the
word "sync". A root that cannot be read
(an unplugged drive) is listed ``online: false`` and skipped without an error.
"""

import os

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from photo_meta_organizer.api.dependencies import Services, get_services
from photo_meta_organizer.api.job_factory import scan_work_factory
from photo_meta_organizer.api.schemas import (
    AddRootRequest,
    RootResponse,
    RootSuggestion,
    RootSuggestionsResponse,
)
from photo_meta_organizer.application.roots import Root, is_online, start_scan, suggest_roots

roots_router = APIRouter(prefix="/api/roots", tags=["roots"])


def _response(root: Root, job_id: str | None = None) -> RootResponse:
    return RootResponse(
        path=root.path, added_at=root.added_at, online=is_online(root.path), job_id=job_id
    )


@roots_router.get("", response_model=list[RootResponse], summary="List the library's roots")
def list_roots(services: Services = Depends(get_services)) -> list[RootResponse]:
    """The folders scanned when the app starts, oldest first, with whether each can be read."""
    return [_response(r) for r in services.roots.list_roots()]


@roots_router.post(
    "", response_model=RootResponse, status_code=201, summary="Add a root and scan it"
)
def add_root(request: AddRootRequest, services: Services = Depends(get_services)) -> RootResponse:
    """Remember a folder and, unless ``scan`` is false, start scanning it (201).

    Adding a known root again is harmless. 400 if the path is not a folder. ``job_id`` is
    null when no scan started (``scan`` false, or another job holds the folder).
    """
    folder = os.path.abspath(request.folder_path)
    if not os.path.isdir(folder):
        raise HTTPException(
            status_code=400,
            detail=f"Directory '{request.folder_path}' does not exist or is not a directory.",
        )
    root = services.roots.add_root(folder)
    return _response(
        root,
        start_scan(services.jobs, scan_work_factory(services), folder) if request.scan else None,
    )


@roots_router.delete("", status_code=204, summary="Stop watching a root")
def remove_root(
    path: str = Query(description="The root's path, as listed"),
    services: Services = Depends(get_services),
) -> Response:
    """Forget a root. Its photos stay in the library; they are just no longer rescanned."""
    if not services.roots.remove_root(path):
        raise HTTPException(status_code=404, detail=f"'{path}' is not a root.")
    return Response(status_code=204)


@roots_router.get(
    "/suggestions",
    response_model=RootSuggestionsResponse,
    summary="Folders to offer as roots",
)
def root_suggestions(services: Services = Depends(get_services)) -> RootSuggestionsResponse:
    """For a library that has photos but no roots: the folders its files lie in, to be
    offered as a checkbox list. Nothing is added until ``POST /api/roots``. Empty once there
    is a root or the user skipped the offer."""
    dismissed = services.roots.suggestions_dismissed()
    if dismissed or services.roots.list_roots():
        return RootSuggestionsResponse(dismissed=dismissed)
    found = suggest_roots(services.roots.observed_folders())
    return RootSuggestionsResponse(
        suggestions=[
            RootSuggestion(path=s.path, file_count=s.file_count, online=is_online(s.path))
            for s in found
        ]
    )


@roots_router.post("/suggestions/dismiss", status_code=204, summary="Skip the suggested roots")
def dismiss_suggestions(services: Services = Depends(get_services)) -> Response:
    """The user skipped the offer: watching stays off and it is not offered again.
    Scanning a folder by hand still works."""
    services.roots.dismiss_suggestions()
    return Response(status_code=204)
