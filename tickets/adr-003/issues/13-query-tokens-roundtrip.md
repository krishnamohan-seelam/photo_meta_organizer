# 13: Query tokens for every filter

**What to build:** Every search filter can be written in the query bar, so any view can later be reproduced from text.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Tokens exist for every SearchRequest field, including within and ai_tag
- [ ] A test round-trips every field of the OpenAPI SearchRequest through q and fails when a new field has no token
