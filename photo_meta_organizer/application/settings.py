"""Runtime settings shared by the CLI, the REST API and the desktop backend (PMO-21).

One frozen object says where the database, the thumbnail cache and the logs live, and
which hosts/origins the API accepts. Each front door builds it the same way:

    explicit value (CLI flag, create_app argument)  >  environment variable  >  default

Environment variables:
    PMO_DATA_DIR       base directory: <dir>/photos.db, <dir>/cache/thumbnails, <dir>/logs
    PMO_DB             database file (beats PMO_DATA_DIR)
    PMO_CACHE_DIR      thumbnail cache directory
    PMO_LOG_DIR        log directory
    PMO_ALLOWED_HOSTS  comma-separated Host header names the API accepts
    PMO_CORS_ORIGINS   comma-separated origins granted CORS
    PMO_API_TOKEN      per-launch token the desktop shell sets; when present the API
                       requires it as a cookie (api/auth.py). Never logged or repr'd.

With nothing set the development layout applies: ``photos.db`` and ``.cache/thumbnails``
relative to the working directory, and no log file.
"""

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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


def _path(value: Any) -> Path | None:
    return None if value is None else Path(value)


@dataclass(frozen=True)
class Settings:
    db_path: Path = Path("photos.db")
    cache_dir: Path | None = None
    log_dir: Path | None = None
    allowed_hosts: tuple[str, ...] = DEFAULT_ALLOWED_HOSTS
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    api_token: str | None = field(default=None, repr=False)

    @property
    def thumbnail_dir(self) -> Path:
        """Where thumbnails are cached (``.cache/thumbnails`` in the dev layout)."""
        return self.cache_dir if self.cache_dir is not None else Path(".cache") / "thumbnails"

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        data_dir: "str | Path | None" = None,
        db_path: "str | Path | None" = None,
        cache_dir: "str | Path | None" = None,
        log_dir: "str | Path | None" = None,
        allowed_hosts: Iterable[str] | None = None,
        cors_origins: Iterable[str] | None = None,
        api_token: str | None = None,
    ) -> "Settings":
        """Build settings from explicit values, then ``env`` (default ``os.environ``).

        ``None`` for an explicit value means "not given", so the environment or the
        default applies. A specific path (db, cache, log) beats a data directory,
        whichever source the data directory came from.
        """
        env = os.environ if env is None else env
        base = _path(data_dir) or _env_path(env, "PMO_DATA_DIR")

        def pick(explicit: Any, var: str, under_base: Path | None) -> Path | None:
            return _path(explicit) or _env_path(env, var) or under_base

        return cls(
            db_path=pick(db_path, "PMO_DB", base / "photos.db" if base else None)
            or Path("photos.db"),
            cache_dir=pick(
                cache_dir, "PMO_CACHE_DIR", base / "thumbnails" if base else None
            ),
            log_dir=pick(log_dir, "PMO_LOG_DIR", base / "logs" if base else None),
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
        )
