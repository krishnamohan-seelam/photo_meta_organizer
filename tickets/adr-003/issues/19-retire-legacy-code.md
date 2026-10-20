# 19: Retire legacy code (R7)

**What to build:** Dead compatibility code is gone.

**Blocked by:** 02 Split the model into assets, files and curation (R3 storage)

**Status:** ready-for-agent

- [ ] TinyDBRepository shrinks to a read-only loader inside the legacy importer; the tinydb runtime dependency is dropped after one release
- [ ] The dict-based update_metadata and batch_update are deleted once every caller uses curation commands
