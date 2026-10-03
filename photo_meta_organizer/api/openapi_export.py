"""The OpenAPI document the frontend's types are generated from (PMO-30).

``python -m scripts.export_openapi`` writes it to ``frontend/openapi.json``;
``npm run gen:api`` (in ``frontend/``) turns that into ``src/api/schema.ts``. A test
on each side fails when the committed file no longer matches its source.
"""

import json
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = REPO_ROOT / "frontend" / "openapi.json"


def openapi_document() -> str:
    """The API's OpenAPI schema as stable, pretty-printed JSON (independent of PMO_* env)."""
    from photo_meta_organizer.api.app import create_app
    from photo_meta_organizer.application.settings import Settings

    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(db_path=Path(":memory:"), cache_dir=Path(tmp) / "thumbnails")
        schema = create_app(settings=settings, frontend_dist=Path(tmp) / "no-dist").openapi()
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
