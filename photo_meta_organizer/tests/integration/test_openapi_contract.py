"""PMO-30: the frontend's generated types must match the API (X-01)."""

from photo_meta_organizer.api.openapi_export import OPENAPI_PATH, openapi_document


def _committed() -> str:
    # Git may check the file out with CRLF line endings on Windows.
    if not OPENAPI_PATH.exists():
        return ""
    return OPENAPI_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_committed_openapi_matches_the_api():
    assert _committed() == openapi_document(), (
        "frontend/openapi.json is out of date. From the repo root run "
        "`python -m scripts.export_openapi` and then `npm --prefix frontend run gen:api`, "
        "and commit both files."
    )


def test_the_document_does_not_depend_on_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("PMO_API_TOKEN", "secret")
    monkeypatch.setenv("PMO_DATA_DIR", str(tmp_path))
    assert openapi_document() == _committed()
    assert list(tmp_path.iterdir()) == []
