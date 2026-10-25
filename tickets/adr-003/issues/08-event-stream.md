# 08: Event stream (R5b)

**What to build:** The UI updates from a push stream instead of polling, and recovers cleanly from a dropped connection.

**Blocked by:** 07 Persisted jobs (R5a)

**Status:** done (2026-10-25). `application/events.EventBus` (thread-safe, ids only grow, ring buffer of 200, `read_after` blocks for news and returns `None` for a gap or an id from another run); `api/routes/events_router.py` serves it (`job_progress`, `job_finished`, `library_changed`, `resync`; a keepalive comment every 15 s; the lifespan closes the bus so streams end at shutdown). `JobManager(on_event=...)` announces a new job, its progress (at most four times a second), a cancel request and its end; a job ending also publishes `library_changed`. An HTTP middleware publishes `library_changed` after a successful edit under `/api/photos`, `/api/collections` or `/api/ai-tags` (searches are POSTs too and do not). Frontend: `hooks/useEventStream.ts` (mounted in `App`), `upsertJob` keeps a job's place in the list, and `useJobs` polls only while the stream is down (3 failed reconnects).

- [x] GET /api/events streams job progress, job finished and library_changed with monotonically increasing event ids
- [x] Reconnect with Last-Event-ID replays from a ring buffer of the last 200 events; an older gap yields a resync event
- [x] The frontend uses one EventSource, invalidates photos and facets on library_changed and resync, and falls back to polling only if reconnects keep failing
- [x] Works with the pmo_token cookie; no auth change

**Known limits:** `library_changed` carries a reason, not the affected hashes (the ADR allowed either); the client reloads the whole photo cache. Mutation hooks still invalidate on their own, so an edit may reload twice.
