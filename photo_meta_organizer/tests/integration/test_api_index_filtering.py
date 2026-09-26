"""PMO-04: POST /api/index and the CLI must only ever index image files (flaw B-05)."""

import sys

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from photo_meta_organizer.api.app import create_app
from tests.conftest import wait_for_job
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import (
    SqliteRepository,
)


@pytest.fixture
def mixed_folder(tmp_path):
    folder = tmp_path / "mixed"
    folder.mkdir()
    Image.new("RGB", (20, 20), "red").save(folder / "photo.jpg")
    Image.new("RGB", (20, 20), "blue").save(folder / "UPPER.PNG")
    (folder / "notes.txt").write_text("not a photo")
    (folder / "clip.mp4").write_bytes(b"\x00" * 64)
    (folder / "Thumbs.db").write_bytes(b"\x01" * 16)
    return str(folder)


def test_api_index_skips_non_image_files(tmp_path, mixed_folder):
    client = TestClient(create_app(db_path=str(tmp_path / "api.db")))
    resp = client.post(
        "/api/index", json={"folder_path": mixed_folder, "num_workers": 2}
    )
    assert resp.status_code == 202
    assert wait_for_job(client, resp.json())["counts"]["indexed"] == 2

    names = sorted(
        p["file_info"]["name"] for p in client.get("/api/photos").json()["items"]
    )
    assert names == ["UPPER.PNG", "photo.jpg"]


def test_cli_index_and_api_index_agree(tmp_path, mixed_folder, monkeypatch):
    from photo_meta_organizer.main import main

    db = str(tmp_path / "cli.db")
    monkeypatch.setattr(
        sys,
        "argv",
        ["prog", "index", "--path", mixed_folder, "--db", db, "--workers", "1"],
    )
    assert main() == 0
    repo = SqliteRepository(db)
    assert sorted(m.file_info.name for m in repo.list_all()) == [
        "UPPER.PNG",
        "photo.jpg",
    ]
    repo.close()


class TestPruneCommand:
    @pytest.fixture
    def polluted_db(self, tmp_path, mixed_folder):
        """A DB that already contains non-image records, as left by the old API."""
        from photo_meta_organizer.application.use_cases import (
            ParallelIndexPhotosUseCase,
        )
        from photo_meta_organizer.infrastructure.extractors.disk_metadata_extractor import (
            DiskMetaDataExtractor,
        )
        from photo_meta_organizer.infrastructure.retriever.local_disk_retriever import (
            LocalDiskRetriever,
        )

        db = str(tmp_path / "polluted.db")
        repo = SqliteRepository(db)
        # Deliberately the old, unfiltered retriever.
        ParallelIndexPhotosUseCase(
            LocalDiskRetriever(mixed_folder), DiskMetaDataExtractor(), repo, 1
        ).execute()
        assert repo.count() == 5
        repo.close()
        return db

    def _count(self, db):
        repo = SqliteRepository(db)
        try:
            return repo.count()
        finally:
            repo.close()

    def test_default_is_a_dry_run(self, polluted_db, monkeypatch, capsys):
        from photo_meta_organizer.main import main

        monkeypatch.setattr(sys, "argv", ["prog", "prune", "--db", polluted_db])
        assert main() == 0
        out = capsys.readouterr().out
        assert "notes.txt" in out and "dry run" in out.lower()
        assert self._count(polluted_db) == 5

    def test_apply_removes_only_non_images(self, polluted_db, monkeypatch):
        from photo_meta_organizer.main import main

        monkeypatch.setattr(
            sys, "argv", ["prog", "prune", "--db", polluted_db, "--apply"]
        )
        assert main() == 0
        repo = SqliteRepository(polluted_db)
        assert sorted(m.file_info.name for m in repo.list_all()) == [
            "UPPER.PNG",
            "photo.jpg",
        ]
        repo.close()
