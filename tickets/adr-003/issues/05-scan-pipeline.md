# 05: One scan pipeline (R4)

**What to build:** Indexing and syncing are one Scan, run the same way from the CLI and the API.

**Blocked by:** 04 Missing files and orphans

**Status:** done (2026-10-24). `ScanLibrary` + `ScanOptions` in `application/use_cases/scan_library.py`, built by `composition.build_scan`. One deliberate change: `index` now skips files it already knows unchanged (it re-extracted everything before); `sync --reextract` is the way to re-read them. The API and CLI keep the `cleanup_deleted` / `--cleanup-deleted` names (the CLI also accepts `--remove-missing`). As a scan, `index` now also flags missing files and records fresh fingerprints, and per-file errors use the sync wording (`extract error [NEW]: <path>: ...`) for both commands; `sync` gained `--workers` (default 4, it was serial). The readability check is `ImageRetriever.check_readable()`.

- [x] A single ScanLibrary use case: discover, classify by (size, mtime), hash and extract on the thread pool, batch-write from one writer thread
- [x] Options: remove_missing, rehash, reextract, dry_run, workers
- [x] index remains as an alias for a scan without remove_missing; sync stays the user-facing name
- [x] The extractor, retriever and use case are built only in the composition root; API routes and the CLI just call it
- [x] The three old ingest use cases and the router-level wiring are removed; behaviour and exit codes unchanged
- [x] Tests first; coverage not lower
