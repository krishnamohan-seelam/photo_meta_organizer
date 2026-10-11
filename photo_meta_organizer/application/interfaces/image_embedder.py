"""Port for the model that turns images and text into vectors (Phase 5, ADR-002).

A CLIP-style model embeds images and text into one space, so a text query can be ranked
against photo vectors (semantic search) and a label can be scored against a photo (zero-shot
tagging). The use cases depend only on this Protocol; the ONNX adapter and a deterministic test
double both implement it.
"""

from collections.abc import Sequence
from typing import BinaryIO, Protocol, runtime_checkable


@runtime_checkable
class ImageEmbedder(Protocol):
    @property
    def model_id(self) -> str:
        """Stable id of the model and its preprocessing, stored with every result.

        Two embedders with the same id must give comparable vectors; changing the model
        must change the id, which is how stale results are recognised.
        """
        ...

    @property
    def dimension(self) -> int:
        """Length of the vectors this model produces."""
        ...

    def embed_image(self, stream: BinaryIO, filename: str) -> Sequence[float]:
        """Vector for the image in ``stream`` (any indexed format, HEIC and RAW included).

        ``filename`` is needed because the format (RAW above all) is told by the extension.

        Raises on an image it cannot decode; callers treat that as a per-file error.
        """
        ...

    def embed_text(self, text: str) -> Sequence[float]:
        """Vector for ``text`` in the same space as the image vectors."""
        ...
