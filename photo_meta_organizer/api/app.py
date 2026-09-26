"""FastAPI application factory for Photo Meta Organizer.

Usage:
    # Production: settings from explicit values, then PMO_* environment variables
    app = create_app(settings=Settings.from_env(db_path="photos.db"))
    uvicorn.run(app, host="127.0.0.1", port=8000)  # loopback only; see security notes below

    # uvicorn factory: create_app() with no arguments reads the environment (PMO_DB, ...)

    # Testing
    from fastapi.testclient import TestClient
    app = create_app(db_path=":memory:")
    client = TestClient(app)

Security model (local application):
    The API has no authentication, so it must only be reachable by the local user's own
    front end. Two defences enforce that: CORS allows only the Vite dev origins (the
    production UI is served same-origin and needs no CORS), and the Host header must be
    a local name (blocks DNS-rebinding). Bind to 127.0.0.1 only. To deliberately expose
    the API on a LAN name, set ``PMO_ALLOWED_HOSTS`` (comma-separated) and accept that
    anyone on that network can read and change the library.
"""

import dataclasses
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from photo_meta_organizer import __version__
from photo_meta_organizer.api.dependencies import Services
from photo_meta_organizer.api.routes.photos_router import (
    collections_router,
    index_router,
    jobs_router,
    photos_router,
    search_router,
    sync_router,
)
from photo_meta_organizer.application.composition import (
    build_collection_repository,
    build_repository,
)
from photo_meta_organizer.application.jobs import JobManager
from photo_meta_organizer.application.settings import (  # noqa: F401 (re-exported)
    DEFAULT_ALLOWED_HOSTS,
    DEFAULT_CORS_ORIGINS,
    Settings,
)
from photo_meta_organizer.infrastructure.thumbnail_service import ThumbnailService


def default_frontend_dist() -> Path:
    """Where the built UI lives: inside the PyInstaller bundle when frozen (the build
    adds ``frontend/dist`` as ``frontend_dist``), else ``frontend/dist`` in the checkout."""
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and bundle_dir:
        return Path(bundle_dir) / "frontend_dist"
    return Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def create_app(
    db_path: "str | Path | None" = None,
    allowed_hosts: "list[str] | None" = None,
    cors_origins: "list[str] | None" = None,
    *,
    settings: "Settings | None" = None,
    cache_dir: "str | Path | None" = None,
    frontend_dist: "str | Path | None" = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        db_path: SQLite database file (ADR-001); ``:memory:`` for tests. A path to an
                 existing legacy TinyDB ``.json`` file is imported once into a sibling
                 ``.db`` file; see ``application.composition.build_repository``.
        allowed_hosts: Accepted Host header names (port ignored).
        cors_origins: Origins granted CORS access. Never a wildcard.
        settings: The full configuration. When omitted it is read from the ``PMO_*``
                 environment variables (see ``application.settings``); the arguments
                 above override single fields either way.
        cache_dir: Thumbnail cache directory (default ``.cache/thumbnails``).
        frontend_dist: The built UI to serve at ``/``. Defaults to
                 :func:`default_frontend_dist`.

    Returns:
        A fully configured FastAPI application instance with all routes mounted.
    """
    base = settings or Settings.from_env()
    overrides = {
        "db_path": Path(db_path) if db_path is not None else None,
        "cache_dir": Path(cache_dir) if cache_dir is not None else None,
        "allowed_hosts": tuple(allowed_hosts) if allowed_hosts is not None else None,
        "cors_origins": tuple(cors_origins) if cors_origins is not None else None,
    }
    settings = dataclasses.replace(base, **{k: v for k, v in overrides.items() if v is not None})

    job_manager = JobManager()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        # Stop background jobs cleanly so none is killed mid-write at exit.
        job_manager.shutdown()

    app = FastAPI(
        lifespan=lifespan,
        title="Photo Meta Organizer API",
        description=(
            "REST API for querying, searching, and managing photo metadata "
            "indexed by the Photo Meta Organizer."
        ),
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS: only the dev front end at a different origin needs it (the built UI and the
    # Electron shell are same-origin). No wildcard, no credentials.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    # Added last so it runs first: reject unexpected Host headers before anything else.
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(settings.allowed_hosts),
    )

    # The composition root: build the services once; routes reach them through
    # api.dependencies (typed as the application Protocols).
    db = str(settings.db_path)
    if db != ":memory:":
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    repository = build_repository(db)
    app.state.services = Services(
        settings=settings,
        repository=repository,
        collections=build_collection_repository(repository),
        jobs=job_manager,
        thumbnails=ThumbnailService(str(settings.thumbnail_dir)),
    )

    # Mount routers
    app.include_router(photos_router)
    app.include_router(collections_router)
    app.include_router(search_router)
    app.include_router(index_router)
    app.include_router(sync_router)
    app.include_router(jobs_router)

    frontend_dist = Path(frontend_dist) if frontend_dist is not None else default_frontend_dist()
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        from fastapi.staticfiles import StaticFiles

        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # Serve root-level static files produced by Vite (favicon, icons, etc.)
    for _static_file in ("favicon.svg", "icons.svg"):
        _path = frontend_dist / _static_file
        if _path.exists():
            _captured_path = str(_path)  # capture for closure
            _captured_name = _static_file

            def _make_static_route(file_path: str, file_name: str):
                @app.get(f"/{file_name}", tags=["frontend"], include_in_schema=False)
                def _static_route(fp=file_path):
                    return FileResponse(fp)

                return _static_route

            _make_static_route(_captured_path, _captured_name)

    @app.get("/health", tags=["health"])
    def health_check():
        """Health check endpoint."""
        return {"status": "ok", "photo_count": repository.count()}

    @app.get("/", tags=["frontend"], response_class=HTMLResponse)
    def serve_frontend():
        """Serve Phase 4 Production React Frontend application."""
        index_html = frontend_dist / "index.html"
        if index_html.exists():
            return HTMLResponse(content=index_html.read_text(encoding="utf-8"))
        return HTMLResponse(
            content="<h1>Frontend not built. Run 'npm run build' in frontend/</h1>",
            status_code=404,
        )

    return app
