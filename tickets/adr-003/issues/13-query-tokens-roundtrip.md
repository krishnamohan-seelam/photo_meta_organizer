# 13: Query tokens for every filter

**What to build:** Every search filter can be written in the query bar, so any view can later be reproduced from text.

**Blocked by:** None (can start immediately)

**Status:** done (2026-10-25). New tokens `near:lat,lon,km`, `within:south,west,north,east` and `ai:label`; `QueryFilters` now carries `filterArea`, `filterAiTag` and `filterNear` (so the bar shows and edits them), `toSearchRequest` sends `location_lat/lon` and `radius_km`. `src/utils/queryRoundtrip.test.ts` reads `openapi.json` and fails for a `SearchRequest` field with no token. Not tokens, by decision: `page`, `page_size`, `sort_by`, `sort_order` (ticket 14 keeps sorting in its own URL parameters) and the older `camera_make` (the UI sends `camera_makes`).

- [x] Tokens exist for every SearchRequest field, including within and ai_tag
- [x] A test round-trips every field of the OpenAPI SearchRequest through q and fails when a new field has no token
