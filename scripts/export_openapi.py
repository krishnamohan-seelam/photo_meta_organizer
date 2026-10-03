"""Write the API's OpenAPI schema to frontend/openapi.json (PMO-30).

python -m scripts.export_openapi        # from the repo root
npm --prefix frontend run gen:api       # then regenerate src/api/schema.ts
"""

from photo_meta_organizer.api.openapi_export import OPENAPI_PATH, openapi_document

if __name__ == "__main__":
    OPENAPI_PATH.write_text(openapi_document(), encoding="utf-8", newline="\n")
    print(f"Wrote {OPENAPI_PATH}")
