"""Application use cases for photo metadata management.

Use cases represent specific application workflows that coordinate
domain services and repositories to fulfill
user-facing operations.
"""

from photo_meta_organizer.application.use_cases.prune_non_images_use_case import (
    PruneNonImagesUseCase,
    PruneResult,
)
from photo_meta_organizer.application.use_cases.scan_library import (
    RootUnavailableError,
    ScanLibrary,
    ScanOptions,
)
from photo_meta_organizer.application.use_cases.search_photos_use_case import (
    PaginatedResult,
    SearchPhotosQuery,
    SearchPhotosUseCase,
)

__all__ = [
    "RootUnavailableError",
    "ScanLibrary",
    "ScanOptions",
    "SearchPhotosUseCase",
    "SearchPhotosQuery",
    "PaginatedResult",
    "PruneNonImagesUseCase",
    "PruneResult",
]
