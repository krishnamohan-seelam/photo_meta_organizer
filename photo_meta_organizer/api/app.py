"""FastAPI application factory for Photo Meta Organizer.

Usage:
    # Production
    app = create_app(db_path="metadata.json")
    uvicorn.run(app, host="127.0.0.1", port=8000)  # loopback only; see security notes below

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

import os

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from photo_meta_organizer.api.routes.photos_router import (
    collections_router,
    index_router,
    photos_router,
    search_router,
)
from photo_meta_organizer.infrastructure.repositories.tinydb_repository import (
    TinyDBRepository,
)


# "testserver" is the host name Starlette's TestClient uses; it is not resolvable
# from the public internet, so it does not weaken the rebinding defence.
DEFAULT_ALLOWED_HOSTS = ("localhost", "127.0.0.1", "testserver")
DEFAULT_CORS_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


def _env_list(name: str) -> "list[str] | None":
    """Comma-separated environment variable as a list, or None if unset/blank."""
    raw = os.environ.get(name, "")
    items = [item.strip() for item in raw.split(",") if item.strip()]
    return items or None


def create_app(
    db_path: str = "metadata.json",
    allowed_hosts: "list[str] | None" = None,
    cors_origins: "list[str] | None" = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        db_path: Path to the TinyDB JSON database file.
                 Created automatically if it does not exist.
        allowed_hosts: Accepted Host header names (port ignored). Defaults to
                 ``PMO_ALLOWED_HOSTS`` or the local names.
        cors_origins: Origins granted CORS access. Defaults to ``PMO_CORS_ORIGINS`` or
                 the Vite dev origins. Never a wildcard.

    Returns:
        A fully configured FastAPI application instance with all routes mounted.
    """
    app = FastAPI(
        title="Photo Meta Organizer API",
        description=(
            "REST API for querying, searching, and managing photo metadata "
            "indexed by the Photo Meta Organizer."
        ),
        version="4.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS: only the dev front end at a different origin needs it (the built UI and the
    # Electron shell are same-origin). No wildcard, no credentials.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins or _env_list("PMO_CORS_ORIGINS") or DEFAULT_CORS_ORIGINS),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    # Added last so it runs first: reject unexpected Host headers before anything else.
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(allowed_hosts or _env_list("PMO_ALLOWED_HOSTS") or DEFAULT_ALLOWED_HOSTS),
    )

    # Build shared repository
    repository = TinyDBRepository(db_path=db_path)

    # Override dependency to inject repository
    def get_repository() -> TinyDBRepository:
        return repository

    app.dependency_overrides[TinyDBRepository] = get_repository

    # Mount routers
    app.include_router(photos_router)
    app.include_router(collections_router)
    app.include_router(search_router)
    app.include_router(index_router)

    frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
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
        return HTMLResponse(content="<h1>Frontend not built. Run 'npm run build' in frontend/</h1>", status_code=404)

    return app
