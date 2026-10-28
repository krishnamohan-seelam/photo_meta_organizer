# 17: Generated API client (R10)

**What to build:** Request and response types come from one generated source.

**Blocked by:** 15 Semantic search as a ranking mode (R9)

**Status:** done (2026-10-28). `openapi-fetch` 0.17 (`createClient<paths>`) is the only way `api/client.ts` reaches the JSON API; the hand-written `request<T>`/`jsonInit` and the unused `fetchPhotos` are gone. `errorMiddleware` (`onResponse`/`onError`) raises `ApiError` with FastAPI's detail (string or 422 list) or, with no detail, a message worded by the call's action ('Loading photos failed (502 Bad Gateway)'); an unreachable server is `ApiError(…, null)`, so toasts and `onError` are unchanged. The exported function names stay, each now one typed call, so no caller changed; done in one pass rather than group by group since the types matched throughout. The client's `fetch` passes a relative URL and a plain init to `globalThis.fetch`, so the existing fetch-stubbing tests run unchanged. The ZIP/JSON exports keep plain `fetch` (streamed downloads with progress) with the same error convention. Existing contract tests (`schema.test.ts`, `test_openapi_contract.py`) pass.

- [x] openapi-fetch replaces the hand-written wrappers one endpoint group at a time
- [x] A middleware converts every non-2xx response into ApiError carrying FastAPI's detail (string or 422 list); toasts and onError are unchanged
- [x] The old wrappers are deleted last; existing contract tests pass
