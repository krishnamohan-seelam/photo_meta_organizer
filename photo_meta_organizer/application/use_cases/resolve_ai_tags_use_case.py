"""Resolve AI tag suggestions: accept, reject or take back (Phase 5, ADR-002 decision 6).

A suggestion is never a label until the user accepts it. Accepting adds the label through the
normal curation path (``AddTag``), so it obeys every rule a hand-typed tag does, then marks the
suggestion accepted. Rejecting only marks it, which keeps the label from being suggested for that
photo again; neither action removes a label (removing one is ordinary curation), and ``reset``
turns a decided suggestion back into an open one without touching the photo's labels.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from photo_meta_organizer.application.interfaces.analysis_repository import AnalysisRepository
from photo_meta_organizer.application.interfaces.image_repository import ImageMetadataRepository
from photo_meta_organizer.domain.analysis import AiTagStatus
from photo_meta_organizer.domain.curation import AddTag

TagAction = Literal["accept", "reject", "reset"]
_STATUS = {
    "accept": AiTagStatus.ACCEPTED,
    "reject": AiTagStatus.REJECTED,
    "reset": AiTagStatus.SUGGESTED,
}


@dataclass(frozen=True)
class ResolveResult:
    photos_changed: int = 0
    tags_changed: int = 0


class ResolveAiTagsUseCase:
    def __init__(self, analysis: AnalysisRepository, repository: ImageMetadataRepository) -> None:
        self._analysis = analysis
        self._repository = repository

    def resolve(self, file_hash: str, label: str, action: TagAction) -> bool:
        """Apply ``action`` to one suggestion. ``False`` if the photo or the tag does not exist."""
        status = self._status(action)
        if not any(t.label == label for t in self._analysis.list_ai_tags(file_hash)):
            return False
        if action == "accept" and self._repository.apply(file_hash, AddTag(label)) is None:
            return False
        return self._analysis.set_ai_tag_status(file_hash, label, status)

    def resolve_many(
        self,
        file_hashes: Sequence[str],
        labels: Sequence[str] | None,
        action: Literal["accept", "reject"],
    ) -> ResolveResult:
        """Accept or reject suggestions across many photos.

        Without ``labels`` it takes every suggestion still open; with them it takes exactly
        those labels (including ones decided the other way before). Unknown photos are skipped.
        """
        status = self._status(action)
        wanted = None if labels is None else set(labels)
        photos = tags = 0
        for file_hash in dict.fromkeys(file_hashes):
            changed = 0
            for tag in self._analysis.list_ai_tags(file_hash):
                if wanted is None:
                    selected = tag.status is AiTagStatus.SUGGESTED
                else:
                    selected = tag.label in wanted and tag.status is not status
                if selected and self.resolve(file_hash, tag.label, action):
                    changed += 1
            if changed:
                photos += 1
                tags += changed
        return ResolveResult(photos_changed=photos, tags_changed=tags)

    @staticmethod
    def _status(action: str) -> AiTagStatus:
        try:
            return _STATUS[action]
        except KeyError:
            raise ValueError(
                f"action must be one of {', '.join(_STATUS)}; got {action!r}"
            ) from None
