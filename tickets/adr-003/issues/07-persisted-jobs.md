# 07: Persisted jobs (R5a)

**What to build:** Job history and progress survive a restart, and an interrupted job can be resumed or dismissed.

**Blocked by:** 05 One scan pipeline (R4)

**Status:** done (2026-10-24). Migration 0004 adds `jobs`; `JobStore` port (`application/interfaces/job_store.py`), `SqliteJobStore`, `composition.build_job_store`; `JobManager(store=...)` writes through (progress throttled to once a second), loads the last 50 jobs at startup and marks active ones `interrupted`. A job stopped by the app's own `shutdown()` (not by the user) also ends `interrupted`, so a clean quit offers Resume too. `POST /api/jobs/{id}/resume` and `/dismiss`; `api/job_factory.work_for` builds a job's work from its stored `params` for both the starting routes and resume. The model download is resumable as well (its consent was given when it started). The pill shows 'Interrupted: <what>' with Resume / Dismiss.

- [x] A jobs table stores kind, folder, status, counts, errors, params and timestamps; the in-memory history is replaced
- [x] At startup, jobs still marked running become interrupted
- [x] The job pill shows 'Interrupted - Resume / Dismiss'; jobs are never resumed automatically
- [x] Resuming a scan or analysis continues idempotently (unchanged files skipped, pending photos only)

**Known limits (not fixed):** a second API process on the same library (say the dev server and the desktop app) marks the first one's live jobs `interrupted` at its startup; a job's `params` are an untyped dict and its `kind` a plain string, so a new kind must be added to `job_factory.work_for` by hand.
