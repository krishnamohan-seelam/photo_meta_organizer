"""Zero-shot tag suggestions: score a photo's vector against a fixed vocabulary (ADR-002).

Each label is turned into a text vector (``"a photo of <label>"``) by the same model that embedded
the photo. A photo's confidence in a label is a softmax over all labels of ``logit_scale * cosine``,
CLIP's own way of reading its similarities as probabilities, so the confidences of a photo's labels
sum to 1: when several labels fit (beach, sea, sand) they share the probability, and a threshold
therefore means "at least this much of the model's belief".

The label vectors are computed once per process on first use and cached on disk under a key made
of the model id, the prompt template and the vocabulary, so a changed model, prompt or label list
never reuses stale vectors.
"""

import hashlib
import logging
import threading
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from photo_meta_organizer.application.interfaces.image_embedder import ImageEmbedder
from photo_meta_organizer.application.tag_vocabulary import VOCABULARY
from photo_meta_organizer.domain.analysis import AiTag, normalize

logger = logging.getLogger(__name__)

# CLIP's learned temperature (exp of its trained logit scale, about 100).
LOGIT_SCALE = 100.0
DEFAULT_TEMPLATE = "a photo of a {}"  # the prompt of the CLIP paper
# Calibrated on 65 real photos with the shipped vocabulary: about 3 tags a photo, none left bare.
DEFAULT_LIMIT = 8
DEFAULT_THRESHOLD = 0.05


class ZeroShotTagger:
    def __init__(
        self,
        embedder: ImageEmbedder,
        labels: Sequence[str] = VOCABULARY,
        *,
        template: str = DEFAULT_TEMPLATE,
        cache_dir: Path | None = None,
        logit_scale: float = LOGIT_SCALE,
    ) -> None:
        self._embedder = embedder
        self._labels = tuple(labels)
        self._template = template
        self._cache_dir = cache_dir
        self._scale = logit_scale
        self._matrix: np.ndarray | None = None
        self._lock = threading.Lock()

    def suggest(
        self, image_vector: Sequence[float], *, limit: int, threshold: float
    ) -> list[AiTag]:
        """Up to ``limit`` labels whose confidence reaches ``threshold``, most confident first."""
        matrix = self._label_matrix()
        if len(image_vector) != matrix.shape[1]:
            raise ValueError(
                f"image vector dimension {len(image_vector)} does not match "
                f"the label vectors' {matrix.shape[1]}"
            )
        unit = np.asarray(normalize(image_vector), dtype=np.float32)
        logits = self._scale * (matrix @ unit)
        probabilities = np.exp(logits - logits.max())
        probabilities /= probabilities.sum()
        # Stable sort: equally likely labels keep vocabulary order, so output is deterministic.
        order = np.argsort(-probabilities, kind="stable")[: max(0, limit)]
        return [
            AiTag(
                label=self._labels[i],
                confidence=min(1.0, float(probabilities[i])),
                model_id=self._embedder.model_id,
            )
            for i in order
            if probabilities[i] >= threshold
        ]

    # ---- label vectors

    def _label_matrix(self) -> np.ndarray:
        with self._lock:
            if self._matrix is None:
                cached = self._load_cached()
                self._matrix = cached if cached is not None else self._compute()
            return self._matrix

    def _cache_path(self) -> Path | None:
        if self._cache_dir is None:
            return None
        key = "\n".join([self._embedder.model_id, self._template, *self._labels])
        return (
            self._cache_dir / f"label-vectors-{hashlib.sha256(key.encode()).hexdigest()[:20]}.npy"
        )

    def _load_cached(self) -> np.ndarray | None:
        path = self._cache_path()
        if path is None or not path.is_file():
            return None
        try:
            matrix = np.load(path, allow_pickle=False)
        except (OSError, ValueError):
            logger.warning("Ignoring an unreadable label-vector cache %s", path)
            return None
        if (
            matrix.shape != (len(self._labels), self._embedder.dimension)
            or not np.isfinite(matrix).all()
        ):
            return None
        return np.asarray(matrix, dtype=np.float32)

    def _compute(self) -> np.ndarray:
        logger.info("Embedding %d tag labels (once; cached afterwards)", len(self._labels))
        vectors = [
            normalize(self._embedder.embed_text(self._template.format(label)))
            for label in self._labels
        ]
        matrix = np.asarray(vectors, dtype=np.float32)
        path = self._cache_path()
        if path is not None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                temp = path.with_name(path.name + ".tmp.npy")
                np.save(temp, matrix)
                temp.replace(path)
            except OSError:
                logger.warning("Could not write the label-vector cache %s", path, exc_info=True)
        return matrix
