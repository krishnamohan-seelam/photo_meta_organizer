"""Jobs survive a restart of the API, and an interrupted one can be resumed or dismissed
(ADR-003 R5a, ticket 07). A restart is a second ``create_app`` on the same database."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from tests.conftest import wait_for_job

from photo_meta_organizer.api.app import create_app
from photo_meta_organizer.application.composition import build_job_store, build_repository
from photo_meta_organizer.application.jobs import Job, JobStatus


@pytest.fixture
def library(tmp_path):
    folder = tmp_path / "lib"
    folder.mkdir()
    for i in range(3):
        Image.new("RGB", (16, 16), (i * 60, 10, 10)).save(folder / f"p{i}.jpg")
    return folder


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "jobs.db")


def _stopped_mid_run(db: str, kind: str, folder: str, params: dict) -> str:
    """Leave a job in the library as if the app had died while it ran."""
    job = Job(
        id=f"{kind}-left-running",
        kind=kind,
        folder_path=folder,
        status=JobStatus.RUNNING,
        params=params,
        created_at=datetime(2026, 10, 24, 9, 0),
        started_at=datetime(2026, 10, 24, 9, 0),
    )
    build_job_store(build_repository(db)).save(job)
    return job.id


def test_finished_jobs_are_listed_after_a_restart(db, library) -> None:
    with TestClient(create_app(db_path=db)) as client:
        job = client.post("/api/index", json={"folder_path": str(library)}).json()
        wait_for_job(client, job)

    with TestClient(create_app(db_path=db)) as client:
        [kept] = client.get("/api/jobs").json()
        assert kept["id"] == job["id"]
        assert kept["status"] == "succeeded"
        assert kept["counts"]["indexed"] == 3


def test_a_job_left_running_comes_back_interrupted(db, library) -> None:
    job_id = _stopped_mid_run(db, "sync", str(library), {"rehash": False})

    with TestClient(create_app(db_path=db)) as client:
        job = client.get(f"/api/jobs/{job_id}").json()
        assert job["status"] == "interrupted"
        assert job["message"].startswith("Interrupted")


def test_resuming_an_interrupted_scan_runs_it_with_its_options(db, library) -> None:
    job_id = _stopped_mid_run(db, "index", str(library), {"workers": 2})

    with TestClient(create_app(db_path=db)) as client:
        resp = client.post(f"/api/jobs/{job_id}/resume")
        assert resp.status_code == 202, resp.text
        assert resp.json()["id"] == job_id
        done = wait_for_job(client, resp.json())
        assert done["status"] == "succeeded"
        assert done["counts"]["indexed"] == 3
        assert client.get("/api/photos").json()["total_count"] == 3


def test_resuming_an_interrupted_sync_skips_unchanged_files(db, library) -> None:
    with TestClient(create_app(db_path=db)) as client:
        wait_for_job(client, client.post("/api/index", json={"folder_path": str(library)}).json())
    job_id = _stopped_mid_run(db, "sync", str(library), {"remove_missing": True})
    (library / "p1.jpg").unlink()

    with TestClient(create_app(db_path=db)) as client:
        done = wait_for_job(client, client.post(f"/api/jobs/{job_id}/resume").json())
        assert done["status"] == "succeeded"
        assert done["counts"]["unchanged"] == 2
        assert done["counts"]["deleted"] == 1  # remove_missing came from the stored params


def test_dismissing_an_interrupted_job_cancels_it(db, library) -> None:
    job_id = _stopped_mid_run(db, "sync", str(library), {})

    with TestClient(create_app(db_path=db)) as client:
        resp = client.post(f"/api/jobs/{job_id}/dismiss")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "cancelled"

    with TestClient(create_app(db_path=db)) as client:
        assert client.get(f"/api/jobs/{job_id}").json()["status"] == "cancelled"


def test_only_an_interrupted_job_can_be_resumed_or_dismissed(db, library) -> None:
    with TestClient(create_app(db_path=db)) as client:
        job = wait_for_job(
            client, client.post("/api/index", json={"folder_path": str(library)}).json()
        )
        assert client.post(f"/api/jobs/{job['id']}/resume").status_code == 409
        assert client.post(f"/api/jobs/{job['id']}/dismiss").status_code == 409
        assert client.post("/api/jobs/nope/resume").status_code == 404
        assert client.post("/api/jobs/nope/dismiss").status_code == 404


def test_an_interrupted_job_records_when_it_ended(db, library) -> None:
    job_id = _stopped_mid_run(db, "sync", str(library), {})

    with TestClient(create_app(db_path=db)) as client:
        assert client.get(f"/api/jobs/{job_id}").json()["finished_at"] is not None
        dismissed = client.post(f"/api/jobs/{job_id}/dismiss").json()
        assert dismissed["finished_at"] is not None


def test_resuming_a_scan_whose_folder_is_gone_is_a_400(db, tmp_path) -> None:
    job_id = _stopped_mid_run(db, "sync", str(tmp_path / "gone"), {})

    with TestClient(create_app(db_path=db)) as client:
        assert client.post(f"/api/jobs/{job_id}/resume").status_code == 400
        assert client.get(f"/api/jobs/{job_id}").json()["status"] == "interrupted"
