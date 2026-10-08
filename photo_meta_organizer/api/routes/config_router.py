"""Deployment settings the UI needs (GET /api/config)."""

from fastapi import APIRouter, Depends

from photo_meta_organizer.api.dependencies import Services, get_services
from photo_meta_organizer.api.schemas import AppConfigResponse

config_router = APIRouter(prefix="/api/config", tags=["config"])


@config_router.get("", response_model=AppConfigResponse, summary="UI-relevant settings")
def get_config(services: Services = Depends(get_services)) -> AppConfigResponse:
    """The Map view draws the bundled world outline unless a tile server is configured."""
    settings = services.settings
    return AppConfigResponse(
        map_tiles_url=settings.map_tiles_url,
        map_tiles_attribution=settings.map_tiles_attribution,
    )
