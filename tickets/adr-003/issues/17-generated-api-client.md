# 17: Generated API client (R10)

**What to build:** Request and response types come from one generated source.

**Blocked by:** 15 Semantic search as a ranking mode (R9)

**Status:** ready-for-agent

- [ ] openapi-fetch replaces the hand-written wrappers one endpoint group at a time
- [ ] A middleware converts every non-2xx response into ApiError carrying FastAPI's detail (string or 422 list); toasts and onError are unchanged
- [ ] The old wrappers are deleted last; existing contract tests pass
