"""ClipOnnxEmbedder: preprocessing always; the real model only when one is installed.

Set ``PMO_TEST_MODEL_DIR`` to a models directory that already holds the manifest's files
(``<dir>/<model_id>/vision_model_fp16.onnx`` ...) to run the tests that load it.
"""

import io
import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from photo_meta_organizer.application.interfaces import ImageEmbedder
from photo_meta_organizer.infrastructure.analysis.clip_onnx_embedder import (
    ClipOnnxEmbedder,
    preprocess_image,
)
from photo_meta_organizer.infrastructure.analysis.model_manifest import CLIP_VIT_B32_FP16
from photo_meta_organizer.infrastructure.analysis.model_store import (
    ModelStore,
    ModelUnavailableError,
)

MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)


class TestPreprocess:
    def test_shape_and_type(self):
        out = preprocess_image(Image.new("RGB", (640, 480), (10, 20, 30)))
        assert out.shape == (1, 3, 224, 224)
        assert out.dtype == np.float32

    def test_normalises_with_clips_mean_and_std(self):
        out = preprocess_image(Image.new("RGB", (300, 300), (255, 255, 255)))
        expected = (1.0 - MEAN) / STD
        assert out[0, :, 100, 100] == pytest.approx(expected, abs=1e-4)

    def test_resizes_the_short_side_then_crops_the_centre(self):
        # A wide white image with a black band at its far left: the band is outside the
        # centre crop, so nothing black may survive.
        image = Image.new("RGB", (600, 200), (255, 255, 255))
        image.paste((0, 0, 0), (0, 0, 100, 200))
        out = preprocess_image(image)
        expected = ((1.0 - MEAN) / STD)[:, None, None]
        assert np.allclose(out[0], np.broadcast_to(expected, (3, 224, 224)), atol=1e-3)

    @pytest.mark.parametrize("mode", ["RGBA", "L", "P", "CMYK"])
    def test_any_colour_mode_becomes_rgb(self, mode):
        out = preprocess_image(Image.new(mode, (50, 80)))
        assert out.shape == (1, 3, 224, 224)

    def test_tiny_images_are_upscaled_to_the_crop(self):
        assert preprocess_image(Image.new("RGB", (8, 8))).shape == (1, 3, 224, 224)


class TestWithoutTheModel:
    def test_satisfies_the_port_and_names_its_model(self, tmp_path):
        embedder = ClipOnnxEmbedder(ModelStore(tmp_path, CLIP_VIT_B32_FP16))
        assert isinstance(embedder, ImageEmbedder)
        assert embedder.model_id == CLIP_VIT_B32_FP16.model_id
        assert embedder.dimension == 512

    def test_using_it_before_the_model_is_installed_says_how_to_get_it(self, tmp_path):
        embedder = ClipOnnxEmbedder(ModelStore(tmp_path, CLIP_VIT_B32_FP16))
        with pytest.raises(ModelUnavailableError, match="analyze --download"):
            embedder.embed_text("hello")


_MODEL_DIR = os.environ.get("PMO_TEST_MODEL_DIR")
needs_model = pytest.mark.skipif(
    not _MODEL_DIR or not ModelStore(Path(_MODEL_DIR), CLIP_VIT_B32_FP16).is_installed(),
    reason="set PMO_TEST_MODEL_DIR to a directory with the downloaded model",
)


@pytest.fixture(scope="module")
def embedder() -> ClipOnnxEmbedder:
    return ClipOnnxEmbedder(ModelStore(Path(_MODEL_DIR or "."), CLIP_VIT_B32_FP16))


def _png(color: tuple[int, int, int], size=(120, 90)) -> io.BytesIO:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def _cos(a, b) -> float:
    a, b = np.asarray(a), np.asarray(b)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


@needs_model
class TestWithTheRealModel:
    def test_vectors_have_the_declared_dimension(self, embedder):
        assert len(embedder.embed_image(_png((200, 30, 30)), "red.png")) == 512
        assert len(embedder.embed_text("a photo of a dog")) == 512

    def test_is_deterministic(self, embedder):
        a = embedder.embed_image(_png((10, 200, 30)), "g.png")
        b = embedder.embed_image(_png((10, 200, 30)), "g.png")
        assert _cos(a, b) == pytest.approx(1.0, abs=1e-6)

    def test_different_images_differ(self, embedder):
        red = embedder.embed_image(_png((220, 20, 20)), "r.png")
        blue = embedder.embed_image(_png((20, 20, 220)), "b.png")
        assert _cos(red, blue) < 0.98

    def test_text_is_case_insensitive(self, embedder):
        assert _cos(embedder.embed_text("Sunset"), embedder.embed_text("sunset")) > 0.9999

    def test_related_text_is_closer_than_unrelated_text(self, embedder):
        cat = embedder.embed_text("a photo of a cat")
        kitten = embedder.embed_text("a photo of a kitten")
        car = embedder.embed_text("a photo of a sports car")
        assert _cos(cat, kitten) > _cos(cat, car)

    def test_text_longer_than_the_context_is_truncated_not_an_error(self, embedder):
        assert len(embedder.embed_text("word " * 500)) == 512

    def test_decodes_heic(self, embedder, tmp_path):
        from tests.conftest import make_heic

        path = make_heic(tmp_path / "x.heic")
        with open(path, "rb") as stream:
            assert len(embedder.embed_image(stream, "x.heic")) == 512

    def test_an_undecodable_file_raises(self, embedder):
        with pytest.raises(OSError):  # Pillow: UnidentifiedImageError is an OSError
            embedder.embed_image(io.BytesIO(b"not an image"), "broken.jpg")

    def test_is_safe_to_call_from_several_threads(self, embedder):
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(4) as pool:
            results = list(
                pool.map(lambda i: embedder.embed_image(_png((i * 20, 50, 50)), "t.png"), range(8))
            )
        assert all(len(r) == 512 for r in results)
