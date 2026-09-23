"""PMO-11: the local API must not be drivable from arbitrary web pages (flaw B-06).

Two independent defences are checked:
- CORS is an allow-list of the dev origins, never ``*``.
- The Host header is validated, which blocks DNS-rebinding (a hostile page that makes
  its own domain resolve to 127.0.0.1 would otherwise be treated as same-origin).
"""

import pytest
from fastapi.testclient import TestClient

from photo_meta_organizer.api.app import DEFAULT_CORS_ORIGINS, create_app

EVIL = "http://evil.example"
DEV = "http://localhost:5173"


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(db_path=str(tmp_path / "sec.json")))


def _preflight(client, origin, method="POST", path="/api/index"):
    return client.options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type",
        },
    )


class TestCors:
    def test_foreign_origin_gets_no_cors_grant_on_a_normal_request(self, client):
        resp = client.get("/api/photos", headers={"Origin": EVIL})
        assert "access-control-allow-origin" not in resp.headers

    @pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
    def test_foreign_origin_preflight_is_refused(self, client, method):
        resp = _preflight(client, EVIL, method)
        assert resp.status_code == 400
        assert "access-control-allow-origin" not in resp.headers

    def test_wildcard_is_never_used(self, client):
        for origin in (EVIL, DEV, "null"):
            resp = client.get("/api/photos", headers={"Origin": origin})
            assert resp.headers.get("access-control-allow-origin") != "*"

    def test_dev_origin_is_allowed(self, client):
        resp = _preflight(client, DEV)
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == DEV

    def test_credentials_are_not_granted(self, client):
        resp = _preflight(client, DEV)
        assert "access-control-allow-credentials" not in resp.headers

    def test_defaults_are_only_local_dev_origins(self):
        assert all(o.startswith(("http://localhost:", "http://127.0.0.1:")) for o in DEFAULT_CORS_ORIGINS)

    def test_origins_are_configurable(self, tmp_path):
        app = create_app(db_path=str(tmp_path / "s.json"), cors_origins=["http://myhost:9000"])
        client = TestClient(app)
        assert _preflight(client, "http://myhost:9000").status_code == 200
        assert _preflight(client, DEV).status_code == 400


class TestHostHeader:
    @pytest.mark.parametrize("host", ["localhost:8000", "127.0.0.1:53211", "localhost", "127.0.0.1"])
    def test_local_hosts_are_accepted(self, client, host):
        assert client.get("/health", headers={"Host": host}).status_code == 200

    @pytest.mark.parametrize("host", ["evil.example", "evil.example:8000", "192.168.1.20:8000", "localhost.evil.example"])
    def test_other_hosts_are_rejected(self, client, host):
        resp = client.get("/health", headers={"Host": host})
        assert resp.status_code == 400

    def test_a_rebound_domain_cannot_read_photos(self, client):
        resp = client.get("/api/photos", headers={"Host": "attacker.example:8000"})
        assert resp.status_code == 400
        assert "items" not in resp.text

    def test_hosts_are_configurable(self, tmp_path):
        app = create_app(db_path=str(tmp_path / "h.json"), allowed_hosts=["photos.lan"])
        client = TestClient(app)
        assert client.get("/health", headers={"Host": "photos.lan:8000"}).status_code == 200
        assert client.get("/health", headers={"Host": "localhost:8000"}).status_code == 400

    def test_environment_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PMO_ALLOWED_HOSTS", "a.lan, b.lan")
        client = TestClient(create_app(db_path=str(tmp_path / "e.json")))
        assert client.get("/health", headers={"Host": "b.lan"}).status_code == 200
        assert client.get("/health", headers={"Host": "localhost"}).status_code == 400
