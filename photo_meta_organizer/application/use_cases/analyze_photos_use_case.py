"""Analyze Photos use case: embed what has no embedding yet and suggest tags (Phase 5, ADR-002).

For every photo with no embedding from the current model it opens the file, asks the
``ImageEmbedder`` for a vector, stores it, and (with a tagger) stores suggested tags. It is
incremental by construction: "what is left to do" is the repository's ``pending_photos``, so a
second run does nothing, an interrupted run resumes, a modified file (new content hash) is picked
up again and a new model re-analyses everything next to the old results.

Embedding runs on a small thread pool (the model's native code releases the GIL), in batches:
all of a batch's photos are embedded concurrently, then the main thread stores the batch and its
tags in one place, so the repository only ever sees one writer. Cancellation is checked between
photos; what was stored stays stored. A file that cannot be opened or decoded is reported and
skipped, and (having no embedding) is tried again by the next run.
"""

import logging
import os
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import BinaryIO

from photo_meta_organizer.application.interfaces.analysis_repository import (
    AnalysisRepository,
    PendingPhoto,
)
from photo_meta_organizer.application.interfaces.image_embedder import ImageEmbedder
from photo_meta_organizer.application.zero_shot_tagger import (
    DEFAULT_LIMIT,
    DEFAULT_THRESHOLD,
    ZeroShotTagger,
)
from photo_meta_organizer.domain.analysis import Embedding

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnalyzeProgress:
    """A progress snapshot: ``processed`` counts successes and failures alike."""

    total: int
    processed: int
    failed: int


@dataclass
class AnalyzeReport:
    total: int = 0
    analyzed: int = 0
    tagged: int = 0  # photos that got at least one suggested tag
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False


def _open_local(path: str) -> BinaryIO:
    return open(path, "rb")


class AnalyzePhotosUseCase:
    def __init__(
        self,
        analysis: AnalysisRepository,
        embedder: ImageEmbedder,
        tagger: ZeroShotTagger | None = None,
        *,
        open_stream: Callable[[str], BinaryIO] = _open_local,
        workers: int = 2,
        batch_size: int = 16,
        tag_limit: int = DEFAULT_LIMIT,
        tag_threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        self._analysis = analysis
        self._embedder = embedder
        self._tagger = tagger
        self._open = open_stream
        self._workers = max(1, workers)
        self._batch_size = max(1, batch_size)
        self._tag_limit = tag_limit
        self._tag_threshold = tag_threshold

    def run(
        self,
        *,
        reanalyze: bool = False,
        limit: int | None = None,
        progress: Callable[[AnalyzeProgress], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> AnalyzeReport:
        """Analyse the pending photos (all of them again with ``reanalyze``), at most ``limit``."""
        model_id = self._embedder.model_id
        if reanalyze:
            self._analysis.clear_embeddings(model_id)
        pending = self._analysis.pending_photos(model_id, limit)
        report = AnalyzeReport(total=len(pending))
        processed = 0

        def tick() -> None:
            nonlocal processed
            processed += 1
            if progress:
                progress(AnalyzeProgress(report.total, processed, len(report.errors)))

        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            for start in range(0, len(pending), self._batch_size):
                if should_cancel and should_cancel():
                    report.cancelled = True
                    break
                batch = pending[start : start + self._batch_size]
                futures = [pool.submit(self._embed, photo) for photo in batch]
                results: list[tuple[PendingPhoto, Sequence[float]]] = []
                for photo, future in zip(batch, futures, strict=True):
                    outcome = self._collect(photo, future, report)
                    if outcome is not None:
                        results.append((photo, outcome))
                    tick()
                    if should_cancel and should_cancel():
                        report.cancelled = True
                        for rest in futures:
                            rest.cancel()
                        break
                self._store(results, report)
                if report.cancelled:
                    break
        return report

    def retag(
        self,
        *,
        progress: Callable[[AnalyzeProgress], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> AnalyzeReport:
        """Recompute the suggested tags of every embedded photo from its stored vector.

        No photo is opened and no model runs over pixels: this is for a new threshold or a new
        vocabulary. Accepted and rejected suggestions are kept (the repository never overwrites
        them); still-open ones are replaced.
        """
        if self._tagger is None:
            raise ValueError("retag needs a tagger")
        hashes = self._analysis.embedded_hashes(self._embedder.model_id)
        report = AnalyzeReport(total=len(hashes))
        for done, file_hash in enumerate(hashes, start=1):
            if should_cancel and should_cancel():
                report.cancelled = True
                break
            embedding = self._analysis.get_embedding(file_hash, self._embedder.model_id)
            if embedding is not None:
                tags = self._tagger.suggest(
                    embedding.vector, limit=self._tag_limit, threshold=self._tag_threshold
                )
                self._analysis.save_ai_tags(file_hash, tags)
                report.analyzed += 1
                report.tagged += 1 if tags else 0
            if progress:
                progress(AnalyzeProgress(report.total, done, 0))
        return report

    # ---- internals

    def _embed(self, photo: PendingPhoto) -> Sequence[float]:
        with self._open(photo.path) as stream:
            return self._embedder.embed_image(stream, os.path.basename(photo.path))

    @staticmethod
    def _collect(
        photo: PendingPhoto, future: "Future[Sequence[float]]", report: AnalyzeReport
    ) -> Sequence[float] | None:
        try:
            return future.result()
        except Exception as err:  # noqa: BLE001 - any failure of one file is that file's error
            logger.warning("Could not analyse %s: %s", photo.path, err)
            report.errors.append(f"{photo.path}: {err}")
            return None

    def _store(
        self, results: list[tuple[PendingPhoto, Sequence[float]]], report: AnalyzeReport
    ) -> None:
        if not results:
            return
        model_id = self._embedder.model_id
        embeddings: list[tuple[PendingPhoto, Embedding]] = []
        for photo, vector in results:
            try:
                embeddings.append((photo, Embedding(photo.file_hash, model_id, tuple(vector))))
            except ValueError as err:  # a model that returned an unusable vector
                report.errors.append(f"{photo.path}: {err}")
        self._analysis.save_embeddings([e for _, e in embeddings])
        report.analyzed += len(embeddings)
        if self._tagger is None:
            return
        for photo, embedding in embeddings:
            tags = self._tagger.suggest(
                embedding.vector, limit=self._tag_limit, threshold=self._tag_threshold
            )
            if tags:
                self._analysis.save_ai_tags(photo.file_hash, tags)
                report.tagged += 1
