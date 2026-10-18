"""Runtime settings shared by the CLI, the REST API and the desktop backend (PMO-21).

One frozen object says where the database, the thumbnail cache and the logs live, and
which hosts/origins the API accepts. Each front door builds it the same way:

    explicit value (CLI flag, create_app argument)  >  environment variable  >  default

Environment variables:
    PMO_DATA_DIR       one folder for everything: <dir>/photos.db, <dir>/thumbnails,
                       <dir>/models, <dir>/logs (e.g. ``PMO_DATA_DIR=.`` for a scratch library)
    PMO_DB             database file (beats PMO_DATA_DIR)
    PMO_CACHE_DIR      thumbnail cache directory
    PMO_THUMBNAIL_CACHE_MB  size budget of the thumbnail cache (default 1024); least
                       recently used thumbnails are evicted beyond it
    PMO_LOG_DIR        log directory
    PMO_MODEL_DIR      where the downloaded AI model lives
    PMO_ALLOWED_HOSTS  comma-separated Host header names the API accepts
    PMO_CORS_ORIGINS   comma-separated origins granted CORS
    PMO_MAP_TILES_URL  opt-in online map tiles, a template with {z}/{x}/{y}. Unset: the Map
                       view draws the bundled world outline and contacts no one.
    PMO_MAP_TILES_ATTRIBUTION  credit line shown on the map for that tile server
    PMO_API_TOKEN      per-launch token the desktop shell sets; when present the API
                       requires it as a cookie (api/auth.py). Never logged or repr'd.

With nothing set, everything lives in the OS per-user folders, split by kind (see
:func:`user_dirs`), so the CLI, the API and the desktop app share one library:

    data (photos.db, models/)  Windows: %LOCALAPPDATA%/PhotoMetaOrganizer
                               macOS:   ~/Library/Application Support/PhotoMetaOrganizer
                               Linux:   ~/.local/share/PhotoMetaOrganizer ($XDG_DATA_HOME)
    cache (thumbnails/)        Windows: %LOCALAPPDATA%/PhotoMetaOrganizer/Cache
                               macOS:   ~/Library/Caches/PhotoMetaOrganizer
                               Linux:   ~/.cache/PhotoMetaOrganizer ($XDG_CACHE_HOME)
    logs (only when on)        Windows: %LOCALAPPDATA%/PhotoMetaOrganizer/Logs
                               macOS:   ~/Library/Logs/PhotoMetaOrganizer
                               Linux:   ~/.local/state/PhotoMetaOrganizer/log

The model sits with the data, not the cache: an OS cleanup must not cost a 305 MB
re-download. No log file is written unless logging to a file is turned on.
"""

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

APP_NAME = "PhotoMetaOrganizer"


@dataclass(frozen=True)
class UserDirs:
    """This user's folders for the app, one per kind of file."""

    data: Path  # the database and the AI model: keep, back up
    cache: Path  # thumbnails: safe to delete, rebuilt on demand
    log: Path


def user_dirs() -> UserDirs:
    """The OS conventions for this user (platformdirs); nothing is created here."""
    import platformdirs

    return UserDirs(
        data=Path(platformdirs.user_data_dir(APP_NAME, appauthor=False)),
        cache=Path(platformdirs.user_cache_dir(APP_NAME, appauthor=False)),
        log=Path(platformdirs.user_log_dir(APP_NAME, appauthor=False)),
    )


# "testserver" is the host name Starlette's TestClient uses; it is not resolvable from
# the public internet, so it does not weaken the DNS-rebinding defence.
DEFAULT_ALLOWED_HOSTS: tuple[str, ...] = ("localhost", "127.0.0.1", "testserver")
DEFAULT_CORS_ORIGINS: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")


def _env_list(env: Mapping[str, str], name: str) -> tuple[str, ...] | None:
    items = tuple(item.strip() for item in env.get(name, "").split(",") if item.strip())
    return items or None


def _env_path(env: Mapping[str, str], name: str) -> Path | None:
    value = env.get(name, "").strip()
    return Path(value) if value else None


def _env_int(env: Mapping[str, str], name: str) -> int | None:
    value = env.get(name, "").strip()
    return int(value) if value else None


def _tiles_url(value: str | None) -> str | None:
    """An http(s) tile template, or ``None``; anything else is a configuration error."""
    url = (value or "").strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")) or not all(
        part in url for part in ("{z}", "{x}", "{y}")
    ):
        raise ValueError(
            "PMO_MAP_TILES_URL must be an http(s) URL containing {z}, {x} and {y}; got " + repr(url)
        )
    return url


def _path(value: Any) -> Path | None:
    return None if value is None else Path(value)


def _default_db_path() -> Path:
    return user_dirs().data / "photos.db"


@dataclass(frozen=True)
class Settings:
    db_path: Path = field(default_factory=_default_db_path)
    cache_dir: Path | None = None
    log_dir: Path | None = None
    model_dir: Path | None = None
    thumbnail_cache_mb: int = 1024
    allowed_hosts: tuple[str, ...] = DEFAULT_ALLOWED_HOSTS
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    api_token: str | None = field(default=None, repr=False)
    map_tiles_url: str | None = None
    map_tiles_attribution: str | None = None

    @property
    def thumbnail_dir(self) -> Path:
        """Where thumbnails are cached (default: the OS cache folder)."""
        return self.cache_dir if self.cache_dir is not None else user_dirs().cache / "thumbnails"

    @property
    def models_dir(self) -> Path:
        """Where the AI model is stored (default: the OS data folder)."""
        return self.model_dir if self.model_dir is not None else user_dirs().data / "models"

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        data_dir: "str | Path | None" = None,
        db_path: "str | Path | None" = None,
        cache_dir: "str | Path | None" = None,
        log_dir: "str | Path | None" = None,
        model_dir: "str | Path | None" = None,
        thumbnail_cache_mb: int | None = None,
        log_to_file: bool = False,
        allowed_hosts: Iterable[str] | None = None,
        cors_origins: Iterable[str] | None = None,
        api_token: str | None = None,
        map_tiles_url: str | None = None,
        map_tiles_attribution: str | None = None,
    ) -> "Settings":
        """Build settings from explicit values, then ``env`` (default ``os.environ``).

        ``None`` for an explicit value means "not given", so the environment or the
        default applies. A specific path (db, cache, log) beats a data directory,
        whichever source the data directory came from, and both beat the OS folders.
        ``log_to_file`` turns the log file on where no log folder is given (the OS one).
        """
        env = os.environ if env is None else env
        base = _path(data_dir) or _env_path(env, "PMO_DATA_DIR")
        dirs = user_dirs()

        def pick(explicit: Any, var: str, under_base: Path | None) -> Path | None:
            return _path(explicit) or _env_path(env, var) or under_base

        return cls(
            db_path=pick(db_path, "PMO_DB", base / "photos.db" if base else None)
            or dirs.data / "photos.db",
            cache_dir=pick(cache_dir, "PMO_CACHE_DIR", base / "thumbnails" if base else None)
            or dirs.cache / "thumbnails",
            log_dir=pick(log_dir, "PMO_LOG_DIR", base / "logs" if base else None)
            or (dirs.log if log_to_file else None),
            model_dir=pick(model_dir, "PMO_MODEL_DIR", base / "models" if base else None)
            or dirs.data / "models",
            thumbnail_cache_mb=(
                thumbnail_cache_mb
                if thumbnail_cache_mb is not None
                else _env_int(env, "PMO_THUMBNAIL_CACHE_MB") or 1024
            ),
            allowed_hosts=(
                tuple(allowed_hosts)
                if allowed_hosts is not None
                else _env_list(env, "PMO_ALLOWED_HOSTS") or DEFAULT_ALLOWED_HOSTS
            ),
            cors_origins=(
                tuple(cors_origins)
                if cors_origins is not None
                else _env_list(env, "PMO_CORS_ORIGINS") or DEFAULT_CORS_ORIGINS
            ),
            api_token=api_token or env.get("PMO_API_TOKEN", "").strip() or None,
            map_tiles_url=_tiles_url(map_tiles_url or env.get("PMO_MAP_TILES_URL")),
            map_tiles_attribution=(
                map_tiles_attribution or env.get("PMO_MAP_TILES_ATTRIBUTION", "").strip() or None
            ),
        )
