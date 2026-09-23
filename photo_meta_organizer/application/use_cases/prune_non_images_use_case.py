"""Prune use case: remove records for files that are not images.

Older versions of ``POST /api/index`` indexed every file in a folder, so libraries
built through the UI may contain records for ``.txt``, ``.mp4``, ``Thumbs.db`` and so
on. ``sync --cleanup-deleted`` cannot remove them because the files still exist.

Written against the repository port only (``list_all`` / ``delete``), so it works on
any storage engine. Dry-run is the default: nothing is deleted unless ``apply=True``.
"""

from dataclasses import dataclass, field
from typing import List

from photo_meta_organizer.application.interfaces import ImageMetadataRepository
from photo_meta_organizer.domain.formats import is_image_filename
from photo_meta_organizer.domain.models import ImageMetadata


@dataclass
class PruneResult:
    """Outcome of a prune run."""

    candidates: List[ImageMetadata] = field(default_factory=list)
    removed: int = 0


class PruneNonImagesUseCase:
    """Find (and optionally delete) records whose file name is not an image."""

    def __init__(self, repository: ImageMetadataRepository) -> None:
        self._repository = repository

    def execute(self, apply: bool = False) -> PruneResult:
        candidates = [
            record
            for record in self._repository.list_all()
            if not is_image_filename(record.file_info.name)
        ]
        result = PruneResult(candidates=candidates)
        if apply:
            for record in candidates:
                if self._repository.delete(record.file_hash):
                    result.removed += 1
        return result
