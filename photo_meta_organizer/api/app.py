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

from fastapi import FastAPI

from photo_meta_organizer.api.routes.photos_router import photos_router, search_router
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
        version="3.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Build shared repository
    repository = TinyDBRepository(db_path=db_path)

    # Override dependency to inject repository
    def get_repository() -> TinyDBRepository:
        return repository

    app.dependency_overrides[TinyDBRepository] = get_repository

    # Mount routers
    app.include_router(photos_router)
    app.include_router(search_router)

    @app.get("/health", tags=["health"])
    def health_check():
        """Health check endpoint."""
        return {"status": "ok", "photo_count": repository.count()}

    return app
