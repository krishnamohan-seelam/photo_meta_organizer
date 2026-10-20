# 01: Migration runner and baseline (R1)

**What to build:** A library's schema is versioned. Existing databases are recognised and stamped as the baseline without data change, later migrations apply in order, and an older build can never open a newer library.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Today's schema becomes migration 0001; an existing database with tables and version 0 is stamped 1 without re-running it
- [ ] Pending migrations run once, each in its own transaction, before any other repository work
- [ ] Before a table-rebuilding migration, the database is copied with the SQLite backup API (safe under WAL)
- [ ] A database with a newer version than the code knows is refused with an 'update the app' error (no read-only mode)
- [ ] Tests: fresh database, existing unversioned database, newer-version database, backup created
