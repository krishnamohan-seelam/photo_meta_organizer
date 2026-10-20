# 05: One scan pipeline (R4)

**What to build:** Indexing and syncing are one Scan, run the same way from the CLI and the API.

**Blocked by:** 04 Missing files and orphans

**Status:** ready-for-agent

- [ ] A single ScanLibrary use case: discover, classify by (size, mtime), hash and extract on the thread pool, batch-write from one writer thread
- [ ] Options: remove_missing, rehash, reextract, dry_run, workers
- [ ] index remains as an alias for a scan without remove_missing; sync stays the user-facing name
- [ ] The extractor, retriever and use case are built only in the composition root; API routes and the CLI just call it
- [ ] The three old ingest use cases and the router-level wiring are removed; behaviour and exit codes unchanged
- [ ] Tests first; coverage not lower
