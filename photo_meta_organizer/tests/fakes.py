"""Deterministic test doubles for the Phase 5 ports (no model, no download)."""

import hashlib
from collections.abc import Sequence
from typing import BinaryIO


class FakeImageEmbedder:
    """An :class:`ImageEmbedder` whose vectors come from a hash of the input.

    The same bytes (or text) always give the same vector and different ones give different,
    well-spread vectors, so tests can check ranking and plumbing without a neural network.
    ``embed_text(label)`` is *not* close to any image: tests that need a known match build the
    expected vector explicitly (``vector_for``).
    """

    def __init__(self, model_id: str = "fake-embedder-v1", dimension: int = 16) -> None:
        self._model_id = model_id
        self._dimension = dimension
        self.image_calls = 0

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        return self._dimension

    def vector_for(self, data: bytes) -> list[float]:
        digest = b""
        counter = 0
        while len(digest) < self._dimension:
            digest += hashlib.sha256(data + counter.to_bytes(2, "big")).digest()
            counter += 1
        # Bytes 0..255 centred on zero, so the vector has a direction and is never all zeros.
        return [(b - 127.5) / 127.5 for b in digest[: self._dimension]]

    def embed_image(self, stream: BinaryIO, filename: str) -> Sequence[float]:
        self.image_calls += 1
        data = stream.read()
        if not data:
            raise ValueError("cannot decode an empty image")
        return self.vector_for(data)

    def embed_text(self, text: str) -> Sequence[float]:
        return self.vector_for(text.encode("utf-8"))
