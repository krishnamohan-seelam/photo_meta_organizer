"""PMO-21: one Settings object for the CLI, the API and the desktop backend."""

from pathlib import Path

import pytest

from photo_meta_organizer.application.settings import (
    DEFAULT_ALLOWED_HOSTS,
    DEFAULT_CORS_ORIGINS,
    Settings,
)


@pytest.mark.unit
class TestSettings:
    def test_defaults_are_the_dev_layout(self) -> None:
        s = Settings.from_env({})
        assert s.db_path == Path("photos.db")
        assert s.cache_dir is None and s.log_dir is None
        assert s.thumbnail_dir == Path(".cache") / "thumbnails"
        assert s.allowed_hosts == DEFAULT_ALLOWED_HOSTS
        assert s.cors_origins == DEFAULT_CORS_ORIGINS

    def test_environment(self, tmp_path) -> None:
        s = Settings.from_env(
            {
                "PMO_DB": str(tmp_path / "lib.db"),
                "PMO_CACHE_DIR": str(tmp_path / "c"),
                "PMO_LOG_DIR": str(tmp_path / "l"),
                "PMO_ALLOWED_HOSTS": "photos.lan, localhost",
                "PMO_CORS_ORIGINS": " ",
            }
        )
        assert s.db_path == tmp_path / "lib.db"
        assert s.cache_dir == tmp_path / "c" and s.thumbnail_dir == tmp_path / "c"
        assert s.log_dir == tmp_path / "l"
        assert s.allowed_hosts == ("photos.lan", "localhost")
        assert s.cors_origins == DEFAULT_CORS_ORIGINS  # blank means unset

    def test_data_dir_supplies_every_path(self, tmp_path) -> None:
        s = Settings.from_env({"PMO_DATA_DIR": str(tmp_path)})
        assert s.db_path == tmp_path / "photos.db"
        assert s.cache_dir == tmp_path / "thumbnails"
        assert s.log_dir == tmp_path / "logs"

    def test_specific_variable_beats_data_dir(self, tmp_path) -> None:
        s = Settings.from_env({"PMO_DATA_DIR": str(tmp_path), "PMO_DB": "other.db"})
        assert s.db_path == Path("other.db")
        assert s.log_dir == tmp_path / "logs"

    def test_explicit_values_beat_the_environment(self, tmp_path) -> None:
        s = Settings.from_env(
            {"PMO_DB": "env.db", "PMO_ALLOWED_HOSTS": "env.host"},
            db_path="arg.db",
            allowed_hosts=["arg.host"],
            cache_dir=None,  # None means "not given", not "clear it"
        )
        assert s.db_path == Path("arg.db")
        assert s.allowed_hosts == ("arg.host",)

    def test_explicit_data_dir(self, tmp_path) -> None:
        s = Settings.from_env({"PMO_DB": "env.db"}, data_dir=tmp_path)
        assert s.db_path == Path("env.db")  # a specific setting still beats a data dir
        assert s.cache_dir == tmp_path / "thumbnails"

    def test_is_immutable(self) -> None:
        with pytest.raises(AttributeError):
            Settings().db_path = Path("x")  # type: ignore[misc]
