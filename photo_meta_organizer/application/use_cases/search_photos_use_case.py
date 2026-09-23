"""Search photos use case (PMO-09).

Filtering, sorting, and paging happen entirely inside the repository
implementation now (``ImageMetadataRepository.query``), not here — this class
exists only so callers depend on a use case, not the repository port directly.
``SearchPhotosQuery``/``PaginatedResult`` are kept as names so existing callers
(the CLI, the API router) do not need to change their imports.
"""

from photo_meta_organizer.application.interfaces.image_repository import ImageMetadataRepository
from photo_meta_organizer.application.interfaces.search_types import Page, SearchQuery
from photo_meta_organizer.domain.geo import haversine_distance_km
from photo_meta_organizer.domain.models import ImageMetadata

SearchPhotosQuery = SearchQuery
PaginatedResult = Page

__all__ = [
    "PaginatedResult",
    "SearchPhotosQuery",
    "SearchPhotosUseCase",
    "haversine_distance_km",
]


class SearchPhotosUseCase:
    """Use case for filtering, sorting, and paginating photo metadata."""

    def __init__(self, repository: ImageMetadataRepository) -> None:
        self.repository = repository

    def execute(self, query: SearchQuery) -> Page[ImageMetadata]:
        """Execute the search query against the metadata repository."""
        return self.repository.query(query)
