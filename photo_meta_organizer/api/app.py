"""FastAPI application factory for Photo Meta Organizer.

Usage:
    # Production
    app = create_app(db_path="metadata.json")
    uvicorn.run(app, host="0.0.0.0", port=8000)

    # Testing
    from fastapi.testclient import TestClient
    app = create_app(db_path=":memory:")
    client = TestClient(app)
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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


def create_app(db_path: str = "metadata.json") -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        db_path: Path to the TinyDB JSON database file.
                 Created automatically if it does not exist.

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

    # Enable CORS for desktop/local environments
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
        # Fallback to prototype if React dist has not been built
        prototype_path = Path(__file__).resolve().parent.parent.parent / "frontend_prototype.html"
        if prototype_path.exists():
            return HTMLResponse(content=prototype_path.read_text(encoding="utf-8"))
        return HTMLResponse(content="<h1>Frontend not built. Run 'npm run build' in frontend/</h1>", status_code=404)

    @app.get("/prototype", tags=["prototype"], response_class=HTMLResponse)
    def serve_prototype():
        """Serve Phase 4 Standalone HTML Prototype."""
        prototype_path = Path(__file__).resolve().parent.parent.parent / "frontend_prototype.html"
        if prototype_path.exists():
            return HTMLResponse(content=prototype_path.read_text(encoding="utf-8"))
        return HTMLResponse(content="<h1>Prototype file not found.</h1>", status_code=404)

    return app
