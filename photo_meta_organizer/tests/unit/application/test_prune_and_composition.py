"""PMO-04: shared retriever factory, image-format rule, and the prune use case (flaw B-05)."""

import pytest

from photo_meta_organizer.application.composition import build_local_retriever
from photo_meta_organizer.application.use_cases.prune_non_images_use_case import (
    PruneNonImagesUseCase,
)
from photo_meta_organizer.domain.formats import IMAGE_EXTENSIONS, is_image_filename
from photo_meta_organizer.domain.models import (
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)


class TestImageFormats:
    @pytest.mark.parametrize("name", ["a.jpg", "A.JPG", "b.jpeg", "c.PNG", "d.heic", "e.NEF", "x.tif"])
    def test_images(self, name):
        assert is_image_filename(name)

    @pytest.mark.parametrize("name", ["notes.txt", "clip.mp4", "Thumbs.db", "doc.pdf", "noext", ".DS_Store"])
    def test_non_images(self, name):
        assert not is_image_filename(name)

    def test_extension_set_is_lowercase_and_dotted(self):
        assert all(e.startswith(".") and e == e.lower() for e in IMAGE_EXTENSIONS)


class TestBuildLocalRetriever:
    def test_lists_only_images_case_insensitively(self, tmp_path):
        for name in ("a.jpg", "B.PNG", "notes.txt", "clip.mp4", "Thumbs.db"):
            (tmp_path / name).write_bytes(b"x")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "c.jpeg").write_bytes(b"x")

        names = sorted(h.filename for h in build_local_retriever(str(tmp_path)).list_files())
        assert names == ["B.PNG", "a.jpg", "c.jpeg"]

    def test_rejects_a_path_that_is_not_a_directory(self, tmp_path):
        with pytest.raises(NotADirectoryError):
            build_local_retriever(str(tmp_path / "missing"))


def _record(file_hash: str, name: str) -> ImageMetadata:
    return ImageMetadata(
        file_hash=file_hash,
        file_info=ImageFileInfo(name=name, path=f"/x/{name}", size_bytes=1, mime_type="x/y"),
        dimensions=ImageDimensions(width=0, height=0),
        exif=ImageExifData(),
    )


class _FakeRepo:
    def __init__(self, records):
        self.records = {r.file_hash: r for r in records}
        self.deleted = []

    def list_all(self):
        return list(self.records.values())

    def delete(self, file_hash):
        self.deleted.append(file_hash)
        return self.records.pop(file_hash, None) is not None


class TestPruneNonImages:
    def _repo(self):
        return _FakeRepo(
            [_record("h1", "a.jpg"), _record("h2", "notes.txt"), _record("h3", "clip.MP4"), _record("h4", "b.PNG")]
        )

    def test_dry_run_reports_candidates_and_deletes_nothing(self):
        repo = self._repo()
        result = PruneNonImagesUseCase(repo).execute(apply=False)
        assert {r.file_hash for r in result.candidates} == {"h2", "h3"}
        assert result.removed == 0
        assert repo.deleted == []

    def test_dry_run_is_the_default(self):
        repo = self._repo()
        PruneNonImagesUseCase(repo).execute()
        assert repo.deleted == []

    def test_apply_removes_only_non_images(self):
        repo = self._repo()
        result = PruneNonImagesUseCase(repo).execute(apply=True)
        assert sorted(repo.deleted) == ["h2", "h3"]
        assert result.removed == 2
        assert {r.file_hash for r in repo.list_all()} == {"h1", "h4"}

    def test_nothing_to_prune(self):
        repo = _FakeRepo([_record("h1", "a.jpg")])
        result = PruneNonImagesUseCase(repo).execute(apply=True)
        assert result.candidates == [] and result.removed == 0
