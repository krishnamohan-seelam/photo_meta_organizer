"""CLIP ViT-B/32 on ONNX Runtime: the ImageEmbedder that runs on the user's CPU (ADR-002).

Loading is lazy: building the object touches nothing, and the sessions are created on first use
under a lock, so importing this module and constructing the embedder stay cheap and the app runs
without the optional ``ai`` extra (``onnxruntime`` and ``tokenizers``) until a caller needs one.

Image preprocessing follows CLIP's published recipe (resize the short side to 224 with bicubic
resampling, centre-crop 224, scale to 0-1, normalise by CLIP's per-channel mean and standard
deviation); text goes through the model's own tokenizer, padded or truncated to its 77-token
context. ``InferenceSession.run`` is thread-safe, so workers may share one embedder.
"""

import threading
from collections.abc import Sequence
from typing import Any, BinaryIO

import numpy as np
from PIL import Image

from photo_meta_organizer.infrastructure.analysis.model_store import (
    ModelStore,
    ModelUnavailableError,
)
from photo_meta_organizer.infrastructure.image_decoding import open_image

_SIZE = 224
_CONTEXT = 77
_EOS_ID = 49407  # <|endoftext|>: also the pad id, as in the model's own tokenizer config
_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
_DIMENSION = 512

_VISION = "vision_model_fp16.onnx"
_TEXT = "text_model_fp16.onnx"
_TOKENIZER = "tokenizer.json"


def preprocess_image(image: Image.Image) -> np.ndarray:
    """A Pillow image as the vision model's input: float32, shape (1, 3, 224, 224)."""
    image = image.convert("RGB")
    width, height = image.size
    scale = _SIZE / min(width, height)
    image = image.resize(
        (max(_SIZE, round(width * scale)), max(_SIZE, round(height * scale))),
        Image.Resampling.BICUBIC,
    )
    width, height = image.size
    left, top = (width - _SIZE) // 2, (height - _SIZE) // 2
    image = image.crop((left, top, left + _SIZE, top + _SIZE))
    pixels = (np.asarray(image, dtype=np.float32) / 255.0 - _MEAN) / _STD
    return np.ascontiguousarray(pixels.transpose(2, 0, 1)[None])


class ClipOnnxEmbedder:
    def __init__(self, store: ModelStore, *, intra_op_threads: int | None = None) -> None:
        self._store = store
        self._threads = intra_op_threads
        self._lock = threading.Lock()
        self._vision: Any = None
        self._text: Any = None
        self._tokenizer: Any = None

    @property
    def model_id(self) -> str:
        return self._store.manifest.model_id

    @property
    def dimension(self) -> int:
        return _DIMENSION

    def embed_image(self, stream: BinaryIO, filename: str) -> Sequence[float]:
        vision = self._load()[0]
        pixels = preprocess_image(open_image(stream, filename))
        output = vision.run(None, {"pixel_values": pixels})[0]
        return output[0].astype(np.float32).tolist()  # type: ignore[no-any-return]

    def embed_text(self, text: str) -> Sequence[float]:
        _, text_model, tokenizer = self._load()
        ids = np.array([tokenizer.encode(text).ids], dtype=np.int64)
        output = text_model.run(None, {"input_ids": ids})[0]
        return output[0].astype(np.float32).tolist()  # type: ignore[no-any-return]

    def _load(self) -> tuple[Any, Any, Any]:
        with self._lock:
            if self._vision is None:
                self._store.require_installed()
                try:
                    import onnxruntime
                    from tokenizers import Tokenizer
                except ImportError as err:
                    raise ModelUnavailableError(
                        "The AI features need the optional 'ai' extra: "
                        "`uv sync --extra ai` (or `pip install photo-meta-organizer[ai]`)."
                    ) from err
                options = onnxruntime.SessionOptions()
                if self._threads:
                    options.intra_op_num_threads = self._threads
                providers = ["CPUExecutionProvider"]
                tokenizer = Tokenizer.from_file(str(self._store.path(_TOKENIZER)))
                tokenizer.enable_padding(length=_CONTEXT, pad_id=_EOS_ID, pad_token="<|endoftext|>")
                tokenizer.enable_truncation(_CONTEXT)
                self._tokenizer = tokenizer
                self._text = onnxruntime.InferenceSession(
                    str(self._store.path(_TEXT)), options, providers=providers
                )
                self._vision = onnxruntime.InferenceSession(
                    str(self._store.path(_VISION)), options, providers=providers
                )
            return self._vision, self._text, self._tokenizer
