"""Application use cases for photo metadata management.

Use cases represent specific application workflows that coordinate
domain services, orchestrators, and repositories to fulfill
user-facing operations.
"""

from photo_meta_organizer.application.use_cases.index_photos_use_case import (
    IndexPhotosUseCase,
)
from photo_meta_organizer.application.use_cases.synchronize_metadata_use_case import (
    SynchronizeMetadataUseCase,
)
from photo_meta_organizer.application.use_cases.parallel_index_photos_use_case import (
    ParallelIndexPhotosUseCase,
)
from photo_meta_organizer.application.use_cases.prune_non_images_use_case import (
    PruneNonImagesUseCase,
    PruneResult,
)
from photo_meta_organizer.application.use_cases.dedupe_paths_use_case import (
    DedupePathsUseCase,
    DedupeResult,
    DuplicatePathGroup,
)
from photo_meta_organizer.application.use_cases.search_photos_use_case import (
    SearchPhotosUseCase,
    SearchPhotosQuery,
    PaginatedResult,
)

__all__ = [
    "IndexPhotosUseCase",
    "SynchronizeMetadataUseCase",
    "ParallelIndexPhotosUseCase",
    "SearchPhotosUseCase",
    "SearchPhotosQuery",
    "PaginatedResult",
    "PruneNonImagesUseCase",
    "PruneResult",
    "DedupePathsUseCase",
    "DedupeResult",
    "DuplicatePathGroup",
]

