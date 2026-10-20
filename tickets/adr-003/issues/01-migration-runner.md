# 01: Migration runner and baseline (R1)

**What to build:** A library's schema is versioned. Existing databases are recognised and stamped as the baseline without data change, later migrations apply in order, and an older build can never open a newer library.

**Blocked by:** None (can start immediately)

**Status:** done (2026-10-20). Note: an unversioned database runs the idempotent baseline and is then stamped 1, so pre-Phase-5 libraries still gain the AI tables.

- [x] Today's schema becomes migration 0001; an existing database with tables and version 0 is brought to the baseline and stamped 1
- [x] Pending migrations run once, each in its own transaction, before any other repository work
- [x] Before a table-rebuilding migration, the database is copied with the SQLite backup API (safe under WAL)
- [x] A database with a newer version than the code knows is refused with an 'update the app' error (no read-only mode)
- [x] Tests: fresh database, existing unversioned database, newer-version database, backup created
- [ ] Follow-up: make the CLI and the desktop shell show the refusal message cleanly (today it surfaces as an exception on open)
