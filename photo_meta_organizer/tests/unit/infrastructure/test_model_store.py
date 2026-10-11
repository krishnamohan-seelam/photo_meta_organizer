"""ModelStore: consent-driven download of the model files, verified and atomic."""

import hashlib
from pathlib import Path

import pytest

from photo_meta_organizer.infrastructure.analysis.model_manifest import (
    CLIP_VIT_B32_FP16,
    ModelFile,
    ModelManifest,
)
from photo_meta_organizer.infrastructure.analysis.model_store import (
    DownloadCancelled,
    ModelStore,
    ModelUnavailableError,
)


def _manifest(tmp_path: Path, contents: dict[str, bytes]) -> ModelManifest:
    """A manifest whose 'remote' files are local ``file://`` URLs."""
    remote = tmp_path / "remote"
    files = []
    for name, data in contents.items():
        path = remote / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files.append(
            ModelFile(
                name=name,
                url=path.as_uri(),
                size=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
            )
        )
    return ModelManifest(model_id="test-model", files=tuple(files), licence="MIT", source="test")


@pytest.fixture
def manifest(tmp_path):
    return _manifest(tmp_path, {"onnx/vision.onnx": b"v" * 5000, "tokenizer.json": b"{}"})


@pytest.fixture
def store(tmp_path, manifest):
    return ModelStore(tmp_path / "models", manifest)


class TestTheRealManifest:
    def test_pins_an_exact_revision_over_https(self):
        for f in CLIP_VIT_B32_FP16.files:
            assert f.url.startswith("https://huggingface.co/")
            assert "/resolve/d15189d7028b43f1d3e65039190477f6af591c2a/" in f.url
            assert len(f.sha256) == 64
            assert f.size > 0

    def test_describes_what_will_be_downloaded(self):
        names = {f.name for f in CLIP_VIT_B32_FP16.files}
        assert names == {"vision_model_fp16.onnx", "text_model_fp16.onnx", "tokenizer.json"}
        assert 300_000_000 < CLIP_VIT_B32_FP16.total_bytes < 310_000_000
        assert CLIP_VIT_B32_FP16.licence == "MIT"
        assert "fp16" in CLIP_VIT_B32_FP16.model_id


class TestStatus:
    def test_nothing_installed_at_first(self, store, manifest):
        assert not store.is_installed()
        assert store.missing_bytes() == manifest.total_bytes
        assert len(store.missing_files()) == 2

    def test_path_of_a_file_inside_the_model_directory(self, store, tmp_path):
        assert (
            store.path("onnx/vision.onnx")
            == tmp_path / "models" / "test-model" / "onnx/vision.onnx"
        )

    def test_a_file_of_the_wrong_size_counts_as_missing(self, store):
        store.download()
        store.path("tokenizer.json").write_bytes(b"truncated-somehow-and-longer")
        assert not store.is_installed()
        assert [f.name for f in store.missing_files()] == ["tokenizer.json"]

    def test_requiring_an_absent_model_says_how_to_get_it(self, store):
        with pytest.raises(ModelUnavailableError, match="analyze --download"):
            store.require_installed()


class TestDownload:
    def test_downloads_and_verifies_every_file(self, store):
        store.download()
        assert store.is_installed()
        assert store.path("onnx/vision.onnx").read_bytes() == b"v" * 5000
        store.require_installed()  # does not raise

    def test_reports_progress_in_bytes(self, store, manifest):
        seen = []
        store.download(progress=lambda done, total: seen.append((done, total)))
        assert seen[-1] == (manifest.total_bytes, manifest.total_bytes)
        assert [d for d, _ in seen] == sorted(d for d, _ in seen)

    def test_skips_files_that_are_already_there(self, store, tmp_path):
        store.download()
        # Remove the remote copies: a second run must not need them.
        for f in (tmp_path / "remote").rglob("*"):
            if f.is_file():
                f.unlink()
        store.download()
        assert store.is_installed()

    def test_a_corrupt_download_is_rejected_and_leaves_nothing_behind(self, tmp_path):
        manifest = _manifest(tmp_path, {"model.onnx": b"good-bytes"})
        # The remote now serves different bytes of the same length.
        Path(manifest.files[0].url.removeprefix("file:///")).write_bytes(b"evil-bytes")
        store = ModelStore(tmp_path / "models", manifest)
        with pytest.raises(ModelUnavailableError, match="checksum"):
            store.download()
        assert not store.path("model.onnx").exists()
        assert not list((tmp_path / "models").rglob("*.part"))

    def test_an_unreachable_file_is_a_clear_error(self, tmp_path):
        manifest = _manifest(tmp_path, {"model.onnx": b"x"})
        Path(manifest.files[0].url.removeprefix("file:///")).unlink()
        with pytest.raises(ModelUnavailableError, match="model.onnx"):
            ModelStore(tmp_path / "models", manifest).download()

    def test_cancelling_stops_and_cleans_up(self, store):
        with pytest.raises(DownloadCancelled):
            store.download(should_cancel=lambda: True)
        assert not store.is_installed()
        assert not list(store.directory.rglob("*.part"))

    def test_files_land_atomically(self, store):
        """No final-named file exists until it has been verified."""
        seen_final = []
        original = store.path("onnx/vision.onnx")

        def watch(done, total):
            seen_final.append(original.exists())

        store.download(progress=watch)
        # Every progress report during the first file happens before it is renamed into place.
        assert seen_final[0] is False
