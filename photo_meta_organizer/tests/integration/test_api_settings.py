"""PMO-21: create_app is the composition root, configured by Settings."""

import sys

from fastapi.testclient import TestClient

from photo_meta_organizer.api.app import create_app
from photo_meta_organizer.application.settings import Settings


def test_no_dependency_overrides_in_production_wiring(tmp_path):
    app = create_app(str(tmp_path / "a.db"))
    assert app.dependency_overrides == {}
    assert TestClient(app).get("/api/photos").status_code == 200


def test_factory_without_arguments_reads_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("PMO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PMO_ALLOWED_HOSTS", "photos.example")
    app = create_app()

    settings = app.state.services.settings
    assert settings.db_path == tmp_path / "data" / "photos.db"
    assert (tmp_path / "data" / "photos.db").exists()
    assert settings.thumbnail_dir == tmp_path / "data" / "cache" / "thumbnails"
    # The Host allow-list came from the environment too.
    assert TestClient(app).get("/health").status_code == 400
    assert TestClient(app, base_url="http://photos.example").get("/health").status_code == 200


def test_arguments_override_a_settings_object(tmp_path):
    base = Settings(db_path=tmp_path / "base.db", allowed_hosts=("only.this",))
    app = create_app(str(tmp_path / "arg.db"), settings=base)
    settings = app.state.services.settings
    assert settings.db_path == tmp_path / "arg.db"
    assert settings.allowed_hosts == ("only.this",)


def test_cli_db_defaults_to_the_environment(tmp_path, monkeypatch, capsys):
    from photo_meta_organizer.main import main

    monkeypatch.setenv("PMO_DB", str(tmp_path / "env.db"))
    monkeypatch.setattr(sys, "argv", ["prog", "stats"])
    assert main() == 0
    assert str(tmp_path / "env.db") in capsys.readouterr().out
