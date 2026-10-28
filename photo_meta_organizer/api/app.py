"""FastAPI application factory for Photo Meta Organizer.

Usage:
    # Production: settings from explicit values, then PMO_* environment variables
    app = create_app(settings=Settings.from_env())  # the per-user library (see settings)
    uvicorn.run(app, host="127.0.0.1", port=8000)  # loopback only; see security notes below

    # uvicorn factory: create_app() with no arguments reads the environment (PMO_DB, ...)

    # Testing: an in-memory SQLite database; pass cache_dir so thumbnails stay out of the CWD
    from fastapi.testclient import TestClient
    app = create_app(db_path=":memory:", cache_dir=tmp_path / "thumbs")
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
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from photo_meta_organizer import __version__
from photo_meta_organizer.api.auth import TokenCookieMiddleware, is_authenticated
from photo_meta_organizer.api.dependencies import Services
from photo_meta_organizer.api.job_factory import scan_work_factory, work_for
from photo_meta_organizer.api.routes.analysis_router import ai_tags_router, analysis_router
from photo_meta_organizer.api.routes.config_router import config_router
from photo_meta_organizer.api.routes.duplicates_router import duplicates_router, files_router
from photo_meta_organizer.api.routes.events_router import (
    changes_library,
    events_router,
    job_event_handler,
)
from photo_meta_organizer.api.routes.export_router import export_router
from photo_meta_organizer.api.routes.photos_router import (
    collections_router,
    index_router,
    jobs_router,
    photos_router,
    search_router,
    sync_router,
)
from photo_meta_organizer.api.routes.removed_router import removed_router
from photo_meta_organizer.api.routes.roots_router import roots_router
from photo_meta_organizer.application import composition
from photo_meta_organizer.application.activity import ActivityTracker
from photo_meta_organizer.application.composition import (
    build_collection_repository,
    build_repository,
)
from photo_meta_organizer.application.events import LIBRARY_CHANGED, EventBus
from photo_meta_organizer.application.interfaces.image_embedder import ImageEmbedder
from photo_meta_organizer.application.jobs import JobManager
from photo_meta_organizer.application.keep_analysed import ANALYZE_PARAMS, KeepAnalysed
from photo_meta_organizer.application.ranking import RankSnapshots
from photo_meta_organizer.application.root_watcher import RootWatcher
from photo_meta_organizer.application.roots import scan_roots
from photo_meta_organizer.application.settings import (  # noqa: F401 (re-exported)
    DEFAULT_ALLOWED_HOSTS,
    DEFAULT_CORS_ORIGINS,
    Settings,
)
from photo_meta_organizer.application.trash import TrashPurger
from photo_meta_organizer.infrastructure import power
from photo_meta_organizer.infrastructure.analysis import runtime
from photo_meta_organizer.infrastructure.analysis.model_store import ModelStore
from photo_meta_organizer.infrastructure.geo.offline_place_namer import OfflinePlaceNamer
from photo_meta_organizer.infrastructure.thumbnail_service import ThumbnailService

# Requests that are the app talking to itself, not the user doing something.
_NOT_ACTIVITY = frozenset({"/api/roots/recheck"})


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
    model_store: "ModelStore | None" = None,
    embedder: "ImageEmbedder | None" = None,
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
        cache_dir: Thumbnail cache directory (default: ``Settings.thumbnail_dir``).
        frontend_dist: The built UI to serve at ``/``. Defaults to
                 :func:`default_frontend_dist`.
        model_store: The AI model's home (default: built from the settings). A seam for tests.
        embedder: The AI embedder (default: CLIP over ``model_store``). A seam for tests.

    Returns:
        A fully configured FastAPI application instance with all routes mounted.
    """
    base = settings or Settings.from_env()
    overrides: dict[str, Any] = {
        "db_path": Path(db_path) if db_path is not None else None,
        "cache_dir": Path(cache_dir) if cache_dir is not None else None,
        "allowed_hosts": tuple(allowed_hosts) if allowed_hosts is not None else None,
        "cors_origins": tuple(cors_origins) if cors_origins is not None else None,
    }
    settings = dataclasses.replace(base, **{k: v for k, v in overrides.items() if v is not None})

    # Built below, once the library is open: the job history lives in it (ADR-003 R5a).
    job_manager: JobManager | None = None
    bus = EventBus()
    activity = ActivityTracker()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # The one automatic piece of work: rescan the library's roots (ADR-003 R5a, R11).
        services = _app.state.services
        if settings.scan_on_start:
            scan_roots(services.roots, services.jobs, scan_work_factory(services))
        if services.root_watcher is not None:
            services.root_watcher.start()
        services.keep_analysed.start()
        services.trash.purge_all()  # whatever was removed before the last stop is final now
        services.trash.start()
        yield
        services.trash.stop()
        services.keep_analysed.stop()
        if services.root_watcher is not None:
            services.root_watcher.stop()
        # Stop background jobs cleanly so none is killed mid-write at exit; they are
        # stored as interrupted and offered for resuming next time.
        if job_manager is not None:
            job_manager.shutdown()
        bus.close()  # release the event streams so the server can stop

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
    # Desktop launch token (PMO-26): only the shell's own session has the cookie.
    if settings.api_token:
        app.add_middleware(TokenCookieMiddleware, token=settings.api_token)
    # Added last so it runs first: reject unexpected Host headers before anything else.
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(settings.allowed_hosts),
    )

    @app.middleware("http")
    async def track_activity(request: Request, call_next: Callable[..., Any]) -> Any:
        """Note that someone is using the app, so background analysis waits for quiet (ticket 11).

        Only requests that change something count; reading (thumbnails, polling) does not, and
        neither do the app's own housekeeping calls.
        """
        if request.method != "GET" and request.url.path not in _NOT_ACTIVITY:
            activity.touch()
        return await call_next(request)

    @app.middleware("http")
    async def announce_library_changes(request: Request, call_next: Callable[..., Any]) -> Any:
        """Tell event listeners when a request has edited the library (ADR-003 R5b)."""
        response = await call_next(request)
        if changes_library(request.method, request.url.path, response.status_code):
            bus.publish(LIBRARY_CHANGED, {"reason": "edit"})
        return response

    # The composition root: build the services once; routes reach them through
    # api.dependencies (typed as the application Protocols).
    db = str(settings.db_path)
    if db != ":memory:":
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    repository = build_repository(db)
    job_manager = JobManager(
        store=composition.build_job_store(repository), on_event=job_event_handler(bus)
    )
    roots = composition.build_root_store(repository)
    root_watcher = (
        RootWatcher(
            roots,
            job_manager,
            lambda folder, params: scan_work_factory(app.state.services)(folder, params),
            composition.build_folder_watcher(),
        )
        if settings.watch_folders
        else None
    )
    store = model_store or composition.build_model_store(settings)
    ai_embedder = embedder or composition.build_embedder(store)
    keep_analysed = KeepAnalysed(
        composition.build_state_store(repository),
        repository,
        composition.build_analysis_repository(repository),
        job_manager,
        model_id=ai_embedder.model_id,
        folder=str(settings.models_dir),
        make_work=lambda: work_for(
            "analyze", str(settings.models_dir), ANALYZE_PARAMS, app.state.services
        ),
        model_ready=lambda: runtime.ai_runtime_installed() and store.is_installed(),
        activity=activity,
        on_battery=power.on_battery if settings.ac_power_only else None,
        threshold=settings.keep_analysed_max,
    )
    app.state.services = Services(
        settings=settings,
        repository=repository,
        collections=build_collection_repository(repository),
        jobs=job_manager,
        events=bus,
        roots=roots,
        root_watcher=root_watcher,
        keep_analysed=keep_analysed,
        trash=TrashPurger(repository),
        thumbnails=ThumbnailService(
            str(settings.thumbnail_dir),
            max_bytes=settings.thumbnail_cache_mb * 1024 * 1024,
        ),
        places=OfflinePlaceNamer(),
        analysis=composition.build_analysis_repository(repository),
        model_store=store,
        embedder=ai_embedder,
        tagger=composition.build_tagger(settings, ai_embedder),
        rankings=RankSnapshots(),
    )

    # Mount routers
    app.include_router(photos_router)
    app.include_router(collections_router)
    app.include_router(search_router)
    app.include_router(index_router)
    app.include_router(sync_router)
    app.include_router(jobs_router)
    app.include_router(events_router)
    app.include_router(roots_router)
    app.include_router(removed_router)
    app.include_router(duplicates_router)
    app.include_router(files_router)
    app.include_router(export_router)
    app.include_router(config_router)
    app.include_router(analysis_router)
    app.include_router(ai_tags_router)

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

            def _make_static_route(file_path: str, file_name: str) -> Callable[[str], FileResponse]:
                @app.get(f"/{file_name}", tags=["frontend"], include_in_schema=False)
                def _static_route(fp: str = file_path) -> FileResponse:
                    return FileResponse(fp)

                return _static_route

            _make_static_route(_captured_path, _captured_name)

    @app.get("/health", tags=["health"])
    def health_check(request: Request) -> dict[str, Any]:
        """Health check endpoint (open even with a launch token; then the photo count
        is reported only to requests that carry the token cookie)."""
        if settings.api_token and not is_authenticated(request.scope, settings.api_token):
            return {"status": "ok"}
        return {"status": "ok", "photo_count": repository.count()}

    @app.get("/", tags=["frontend"], response_class=HTMLResponse)
    def serve_frontend() -> HTMLResponse:
        """Serve Phase 4 Production React Frontend application."""
        index_html = frontend_dist / "index.html"
        if index_html.exists():
            return HTMLResponse(content=index_html.read_text(encoding="utf-8"))
        return HTMLResponse(
            content="<h1>Frontend not built. Run 'npm run build' in frontend/</h1>",
            status_code=404,
        )

    return app
