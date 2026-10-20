# 07: Persisted jobs (R5a)

**What to build:** Job history and progress survive a restart, and an interrupted job can be resumed or dismissed.

**Blocked by:** 05 One scan pipeline (R4)

**Status:** ready-for-agent

- [ ] A jobs table stores kind, folder, status, counts, errors, params and timestamps; the in-memory history is replaced
- [ ] At startup, jobs still marked running become interrupted
- [ ] The job pill shows 'Interrupted - Resume / Dismiss'; jobs are never resumed automatically
- [ ] Resuming a scan or analysis continues idempotently (unchanged files skipped, pending photos only)
