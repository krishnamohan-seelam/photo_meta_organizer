"""PMO-23 (B-11): HEIC/HEIF and camera RAW decode to real pixels and dimensions."""

import io
from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest
import rawpy
from PIL import Image

from photo_meta_organizer.domain.formats import image_mime_type, is_image_filename
from photo_meta_organizer.infrastructure import image_decoding
from photo_meta_organizer.infrastructure.image_decoding import image_size, open_image
from tests.conftest import make_heic


def _jpeg_bytes(size, orientation: int | None = None) -> bytes:
    buffer = io.BytesIO()
    exif = Image.Exif()
    if orientation is not None:
        exif[0x0112] = orientation
    Image.new("RGB", size, "white").save(buffer, "JPEG", exif=exif.tobytes())
    return buffer.getvalue()


class FakeRaw:
    """Stands in for rawpy.RawPy: sensor size, flip, and a configurable preview."""

    def __init__(self, width=6000, height=4000, flip=0, thumb=None, thumb_error=None):
        self.sizes = SimpleNamespace(width=width, height=height, flip=flip)
        self._thumb = thumb
        self._thumb_error = thumb_error
        self.postprocessed = False

    def extract_thumb(self):
        if self._thumb_error is not None:
            raise self._thumb_error
        return self._thumb

    def postprocess(self, **_kwargs):
        self.postprocessed = True
        return np.zeros((20, 30, 3), dtype=np.uint8)


@pytest.fixture
def fake_raw(monkeypatch):
    holder = {}

    def use(raw: FakeRaw) -> FakeRaw:
        @contextmanager
        def imread(_source):
            yield raw

        monkeypatch.setattr(image_decoding.rawpy, "imread", imread)
        holder["raw"] = raw
        return raw

    return use


class TestFormats:
    @pytest.mark.parametrize("name", ["a.CR3", "b.arw", "c.NEF", "d.dng", "e.heic", "f.RAF"])
    def test_raw_and_heif_are_indexable(self, name):
        assert is_image_filename(name)

    def test_mime_types(self):
        assert image_mime_type("x.HEIC") == "image/heic"
        assert image_mime_type("x.arw") == "image/x-sony-arw"
        assert image_mime_type("x.jpg") is None


class TestHeif:
    def test_heic_opens_with_real_size(self, tmp_path):
        path = make_heic(tmp_path / "p.heic")
        assert image_size(path, "p.heic") == (64, 48)
        with open(path, "rb") as stream:
            assert image_size(stream, "p.heic") == (64, 48)
        assert open_image(path, "p.heic").size == (64, 48)


class TestRaw:
    def test_size_is_the_sensor_size(self, fake_raw):
        fake_raw(FakeRaw(width=6000, height=4000, flip=6))
        assert image_size(io.BytesIO(b"raw"), "a.arw") == (6000, 4000)

    def test_embedded_jpeg_preview_is_used_and_rotated_by_flip(self, fake_raw):
        thumb = SimpleNamespace(format=rawpy.ThumbFormat.JPEG, data=_jpeg_bytes((60, 40)))
        raw = fake_raw(FakeRaw(flip=6, thumb=thumb))
        img = open_image("a.cr3", "a.cr3")
        assert img.size == (40, 60)  # portrait: rotated 90° clockwise
        assert not raw.postprocessed

    def test_preview_orientation_tag_wins_over_flip(self, fake_raw):
        thumb = SimpleNamespace(
            format=rawpy.ThumbFormat.JPEG, data=_jpeg_bytes((60, 40), orientation=6)
        )
        fake_raw(FakeRaw(flip=6, thumb=thumb))
        assert open_image("a.nef", "a.nef").size == (40, 60)  # rotated once, not twice

    def test_bitmap_preview(self, fake_raw):
        bitmap = np.zeros((10, 16, 3), dtype=np.uint8)
        fake_raw(FakeRaw(thumb=SimpleNamespace(format=rawpy.ThumbFormat.BITMAP, data=bitmap)))
        assert open_image("a.dng", "a.dng").size == (16, 10)

    def test_no_preview_falls_back_to_demosaic(self, fake_raw):
        raw = fake_raw(FakeRaw(thumb_error=rawpy.LibRawNoThumbnailError()))
        assert open_image("a.arw", "a.arw").size == (30, 20)
        assert raw.postprocessed

    def test_undecodable_raw_raises(self, tmp_path):
        path = tmp_path / "broken.arw"
        path.write_bytes(b"not a raw file")
        with pytest.raises(rawpy.LibRawError):
            open_image(str(path), "broken.arw")
