# 08: Event stream (R5b)

**What to build:** The UI updates from a push stream instead of polling, and recovers cleanly from a dropped connection.

**Blocked by:** 07 Persisted jobs (R5a)

**Status:** ready-for-agent

- [ ] GET /api/events streams job progress, job finished and library_changed with monotonically increasing event ids
- [ ] Reconnect with Last-Event-ID replays from a ring buffer of the last 200 events; an older gap yields a resync event
- [ ] The frontend uses one EventSource, invalidates photos and facets on library_changed and resync, and falls back to polling only if reconnects keep failing
- [ ] Works with the pmo_token cookie; no auth change
