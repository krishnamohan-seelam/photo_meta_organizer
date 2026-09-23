"""Dedupe use case: collapse records that describe the same file path.

Before PMO-05, re-indexing an edited file saved the new content under its new hash
and left the old record behind, so one path could own several records. Content is
the primary key (an edit changes it), so this cannot be fixed by an upsert: the
extra records have to be found by path and merged.

Per path the newest record (by ``added_at``) is kept and the user's curation from the
older ones is merged into it. Written against the repository port only
(``list_all`` / ``save`` / ``delete``). Dry-run is the default.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from photo_meta_organizer.application.interfaces import ImageMetadataRepository
from photo_meta_organizer.domain.curation import carry_over_curation
from photo_meta_organizer.domain.models import ImageMetadata


@dataclass
class DuplicatePathGroup:
    """Records sharing one resolved path: which to keep and which to drop."""

    path: str
    keep: ImageMetadata
    drop: List[ImageMetadata]  # newest first


@dataclass
class DedupeResult:
    """Outcome of a dedupe run."""

    groups: List[DuplicatePathGroup] = field(default_factory=list)
    removed: int = 0


def _path_key(path: str) -> str:
    """Resolve and case-normalise a path the way the sync analyzer identifies files."""
    return os.path.normcase(str(Path(path).resolve()))


class DedupePathsUseCase:
    """Find (and optionally merge) records that share a file path."""

    def __init__(self, repository: ImageMetadataRepository) -> None:
        self._repository = repository

    def execute(self, apply: bool = False) -> DedupeResult:
        by_path: Dict[str, List[ImageMetadata]] = {}
        for record in self._repository.list_all():
            by_path.setdefault(_path_key(record.file_info.path), []).append(record)

        result = DedupeResult()
        for key, records in by_path.items():
            if len(records) < 2:
                continue
            # Newest first; among equal timestamps the record listed later wins.
            ranked = sorted(enumerate(records), key=lambda ir: (ir[1].added_at, ir[0]), reverse=True)
            ordered = [record for _, record in ranked]
            result.groups.append(
                DuplicatePathGroup(path=key, keep=ordered[0], drop=ordered[1:])
            )

        if apply:
            for group in result.groups:
                # Save the merged survivor first so a crash never loses curation.
                self._repository.save(carry_over_curation(group.keep, *group.drop))
                for stale in group.drop:
                    if self._repository.delete(stale.file_hash):
                        result.removed += 1
        return result
