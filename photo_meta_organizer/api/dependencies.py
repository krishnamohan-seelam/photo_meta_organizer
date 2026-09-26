"""Request-scoped access to the services ``create_app`` built (PMO-21).

``create_app`` puts one :class:`Services` on ``app.state``; route dependencies read it
from the request. Routes are typed against the application Protocols, so they never
learn which storage engine is behind them, and there is no ``dependency_overrides``
wiring in production (tests may still use overrides the normal FastAPI way).
"""

from dataclasses import dataclass

from fastapi import Request

from photo_meta_organizer.application.interfaces.collection_repository import (
    CollectionRepository,
)
from photo_meta_organizer.application.interfaces.image_repository import (
    ImageMetadataRepository,
)
from photo_meta_organizer.application.jobs import JobManager
from photo_meta_organizer.application.settings import Settings
from photo_meta_organizer.infrastructure.thumbnail_service import ThumbnailService


@dataclass(frozen=True)
class Services:
    settings: Settings
    repository: ImageMetadataRepository
    collections: CollectionRepository
    jobs: JobManager
    thumbnails: ThumbnailService


def get_services(request: Request) -> Services:
    services = getattr(request.app.state, "services", None)
    if not isinstance(services, Services):
        raise RuntimeError("create_app did not configure app.state.services")
    return services


def get_repository(request: Request) -> ImageMetadataRepository:
    return get_services(request).repository


def get_collection_repository(request: Request) -> CollectionRepository:
    return get_services(request).collections


def get_job_manager(request: Request) -> JobManager:
    return get_services(request).jobs


def get_thumbnail_service(request: Request) -> ThumbnailService:
    return get_services(request).thumbnails
