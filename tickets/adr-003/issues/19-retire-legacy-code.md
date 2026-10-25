# 19: Retire legacy code (R7)

**What to build:** Dead compatibility code is gone.

**Blocked by:** 02 Split the model into assets, files and curation (R3 storage)

**Status:** done (2026-10-25). `TinyDBRepository`/`TinyDBCollectionRepository` (about 1,000 lines) are deleted; `infrastructure/importers/legacy_json_reader.LegacyJsonReader` reads a legacy file (photos and collections) and nothing else. Tests that need a legacy file build one with `tests/legacy_json.LegacyJsonWriter`. `update_metadata` and `batch_update` are gone from the port and `SqliteRepository` (their last callers, in `test_sync_end_to_end`, use `apply`). The TinyDB-only tests and the TinyDB leg of the repository contract test were removed; the datetime tests now run on SQLite. The `tinydb` dependency stays for one release (the reader needs it); dropping it is a one-line change in `pyproject.toml` and `scripts/build_backend.py` after that.

- [x] TinyDBRepository shrinks to a read-only loader inside the legacy importer; the tinydb runtime dependency is dropped after one release
- [x] The dict-based update_metadata and batch_update are deleted once every caller uses curation commands
