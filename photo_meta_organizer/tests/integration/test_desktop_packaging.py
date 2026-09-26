"""PMO-12: the packaged backend serves the UI and keeps its data out of the install dir."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from tests.conftest import wait_for_job

from photo_meta_organizer.api.app import create_app, default_frontend_dist
from photo_meta_organizer.api.desktop import (
    adopt_legacy_database,
    parse_args,
    resolve_settings,
)
from photo_meta_organizer.application.settings import Settings
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import (
    SqliteRepository,
)


@pytest.fixture
def dist(tmp_path) -> Path:
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><div id=root>studio</div>", encoding="utf-8")
    (d / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")
    (d / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    return d


class TestFrontendServing:
    def test_serves_index_assets_and_root_files_from_frontend_dist(self, tmp_path, dist):
        client = TestClient(create_app(str(tmp_path / "a.db"), frontend_dist=dist))
        root = client.get("/")
        assert root.status_code == 200 and "studio" in root.text
        assert client.get("/assets/app.js").text == "console.log('ok')"
        assert client.get("/favicon.svg").status_code == 200

    def test_missing_build_says_so(self, tmp_path):
        client = TestClient(create_app(str(tmp_path / "a.db"), frontend_dist=tmp_path / "nope"))
        resp = client.get("/")
        assert resp.status_code == 404 and "not built" in resp.text

    def test_frozen_app_looks_inside_the_bundle(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        assert default_frontend_dist() == tmp_path / "frontend_dist"

    def test_source_checkout_uses_frontend_dist(self, monkeypatch):
        monkeypatch.delattr(sys, "frozen", raising=False)
        assert default_frontend_dist().parts[-2:] == ("frontend", "dist")


class TestCacheDir:
    def test_thumbnails_go_to_the_configured_cache_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)  # nothing may land in the working directory
        photos = tmp_path / "photos"
        photos.mkdir()
        Image.new("RGB", (40, 30), "red").save(photos / "a.jpg")
        cache = tmp_path / "data" / "thumbs"
        with TestClient(
            create_app(str(tmp_path / "data" / "p.db"), cache_dir=str(cache))
        ) as client:
            wait_for_job(
                client, client.post("/api/index", json={"folder_path": str(photos)}).json()
            )
            file_hash = client.get("/api/photos").json()["items"][0]["file_hash"]
            assert client.get(f"/api/photos/{file_hash}/thumbnail").status_code == 200
        assert list(cache.glob("*.webp"))
        assert not (tmp_path / ".cache").exists()

    def test_database_parent_directory_is_created(self, tmp_path):
        create_app(str(tmp_path / "fresh" / "nested" / "p.db"))
        assert (tmp_path / "fresh" / "nested" / "p.db").exists()


class TestDesktopSettings:
    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        for var in ("PMO_DATA_DIR", "PMO_DB", "PMO_CACHE_DIR", "PMO_LOG_DIR"):
            monkeypatch.delenv(var, raising=False)

    def test_explicit_paths_win(self, tmp_path):
        args = parse_args(
            [
                "--db",
                str(tmp_path / "x.db"),
                "--cache-dir",
                str(tmp_path / "c"),
                "--log-dir",
                str(tmp_path / "l"),
                "--port",
                "9001",
            ]
        )
        s = resolve_settings(args)
        assert (s.db_path, s.cache_dir, s.log_dir) == (
            tmp_path / "x.db",
            tmp_path / "c",
            tmp_path / "l",
        )
        assert args.port == 9001

    def test_data_dir_supplies_the_defaults(self, tmp_path):
        s = resolve_settings(parse_args(["--data-dir", str(tmp_path)]))
        assert s == Settings(
            db_path=tmp_path / "photos.db",
            cache_dir=tmp_path / "cache" / "thumbnails",
            log_dir=tmp_path / "logs",
        )

    def test_environment_applies_when_no_flag_is_given(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PMO_DATA_DIR", str(tmp_path))
        s = resolve_settings(parse_args(["--db", str(tmp_path / "flag.db")]))
        assert s.db_path == tmp_path / "flag.db"
        assert s.log_dir == tmp_path / "logs"

    def test_no_arguments_keeps_the_dev_layout(self):
        s = resolve_settings(parse_args([]))
        assert s.db_path == Path("photos.db") and s.cache_dir is None and s.log_dir is None


class TestAdoptLegacyDatabase:
    def _seed_sqlite(self, path: Path) -> None:
        from photo_meta_organizer.domain.models import (
            ImageDimensions,
            ImageExifData,
            ImageFileInfo,
            ImageMetadata,
        )

        repo = SqliteRepository(str(path))
        repo.save(
            ImageMetadata(
                file_hash="a" * 64,
                file_info=ImageFileInfo("a.jpg", "/p/a.jpg", 10, "image/jpeg"),
                dimensions=ImageDimensions(1, 1),
                exif=ImageExifData(),
                rating=4,
            )
        )
        repo.close()

    def test_copies_an_old_sqlite_db_and_leaves_it_in_place(self, tmp_path):
        legacy = tmp_path / "install"
        legacy.mkdir()
        self._seed_sqlite(legacy / "photos.db")
        target = tmp_path / "userdata" / "photos.db"

        adopted = adopt_legacy_database(target, [legacy / "photos.db", legacy / "metadata.json"])

        assert adopted == legacy / "photos.db"
        assert (legacy / "photos.db").exists()
        repo = SqliteRepository(str(target))
        assert repo.count() == 1 and repo.list_all()[0].rating == 4
        repo.close()

    def test_imports_an_old_json_db_without_touching_it(self, tmp_path):
        legacy = tmp_path / "install"
        legacy.mkdir()
        legacy_json = legacy / "metadata.json"
        from photo_meta_organizer.domain.models import (
            ImageDimensions,
            ImageExifData,
            ImageFileInfo,
            ImageMetadata,
        )
        from photo_meta_organizer.infrastructure.repositories.tinydb_repository import (
            TinyDBRepository,
        )

        old = TinyDBRepository(db_path=str(legacy_json))
        old.save(
            ImageMetadata(
                file_hash="b" * 64,
                file_info=ImageFileInfo("b.jpg", "/p/b.jpg", 5, "image/jpeg"),
                dimensions=ImageDimensions(1, 1),
                exif=ImageExifData(),
                rating=2,
            )
        )
        old._db.close()
        before = legacy_json.read_bytes()
        target = tmp_path / "userdata" / "photos.db"

        adopted = adopt_legacy_database(target, [legacy / "photos.db", legacy_json])

        assert adopted == legacy_json
        assert legacy_json.read_bytes() == before
        assert not (legacy / "metadata.db").exists()  # nothing written next to the original
        repo = SqliteRepository(str(target))
        assert repo.count() == 1
        repo.close()

    def test_existing_target_is_never_overwritten(self, tmp_path):
        legacy = tmp_path / "install"
        legacy.mkdir()
        self._seed_sqlite(legacy / "photos.db")
        target = tmp_path / "userdata" / "photos.db"
        target.parent.mkdir()
        SqliteRepository(str(target)).close()

        assert adopt_legacy_database(target, [legacy / "photos.db"]) is None
        repo = SqliteRepository(str(target))
        assert repo.count() == 0
        repo.close()

    def test_nothing_to_adopt(self, tmp_path):
        assert adopt_legacy_database(tmp_path / "t.db", [tmp_path / "missing.db"]) is None
        assert not (tmp_path / "t.db").exists()


def test_importing_the_api_has_no_side_effects(tmp_path):
    """Importing the router used to create .cache/thumbnails in the working directory."""
    import subprocess

    subprocess.run(
        [sys.executable, "-c", "import photo_meta_organizer.api.app"], cwd=tmp_path, check=True
    )
    assert not (tmp_path / ".cache").exists()
