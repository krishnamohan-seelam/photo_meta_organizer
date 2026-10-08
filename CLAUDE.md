# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Photo Meta Organizer indexes large photo libraries: it extracts EXIF, keys every photo by SHA-256 of its contents (dedup), and stores results in SQLite (`photos.db`), behind the same repository port. Three front doors share one backend: a CLI (`main.py`), a FastAPI REST API, and a React 19 SPA that can also be wrapped in an Electron desktop app. README.md lists phases 0–4 as complete and phases 5–6 (AI tagging, S3/MongoDB) as planned. Note the numbering conflict: `design_docs/PHASE_5_COMPLETION.md` labels the finished Electron desktop app as "Phase 5", while the README treats the desktop app as part of the current state. The S3 and MongoDB backends and AI tagging do not exist yet.

## Repository layout (non-obvious bits)

The repo root is the uv project root: `pyproject.toml` (runtime deps, `dev` and `build` dependency groups, optional `s3` extra, ruff/black config), `uv.lock` and `.python-version` (3.11) live there, and `uv sync` manages `.venv` at the root. The package `photo_meta_organizer/` is installed editable, so it imports from any directory. Inside the package, `pytest.ini` is the only pytest config and `setup.cfg` holds only the mypy config. The version's single source is `photo_meta_organizer/__init__.py` (`__version__`; the API and `--version` read it). The root also holds `frontend/` (Vite SPA), `desktop/` (Electron), `scripts/` and the npm workspace `package.json`.

Runtime files sit in the repo root or wherever you run from: `photos.db` (the SQLite DB, plus its `-wal`/`-shm` files), `.cache/thumbnails/`; the CLI writes a rotating `photo_meta_organizer.log` only when given `--log-dir` or `PMO_LOG_DIR` (logging is configured at startup by `infrastructure/logging_setup.py`, never at import; log lines go to stderr). Don't commit or casually rewrite these. A pre-migration `metadata.json` (the old TinyDB store, ~16 MB) may still sit alongside it as a legacy artifact — see ADR-001 below; `*.bak*` files are stray backups.

## Commands

Use uv (Windows: `.venv\Scripts\activate` after `uv sync`, or prefix commands with `uv run`). Python 3.11.

```bash
uv sync                      # exact locked env: runtime + dev group (removes anything not in uv.lock)
uv add <pkg> | uv add --group dev <pkg>   # then commit pyproject.toml and uv.lock
# This machine intercepts HTTPS with a locally trusted cert: `native-tls = true` in [tool.uv] handles it.
# If pyvenv.cfg's version drifts from the base Python, uv tries to delete and recreate .venv, which fails
# while VS Code's Black extension or a dev server holds files; correct pyvenv.cfg and `uv sync --reinstall`.

# Tests — MUST run from photo_meta_organizer/ (three test files do `from tests.conftest import ...`,
# which fails at collection when run from the repo root). Baseline on 2026-10-08: all 671 pass (frontend: 239).
# uv add --group dev now also carries bandit and pip-audit (added 2026-09-27); not yet wired into any command above.
python -m pytest                                        # full suite; pytest.ini adds --cov and -v
python -m pytest --no-cov tests/unit/domain/test_services.py
python -m pytest --no-cov -k "sync and dry_run"         # single test by keyword
python -m pytest --no-cov tests/unit/domain/test_services.py::TestName::test_name

# Lint / types (config is in photo_meta_organizer/; run from that directory)
cd photo_meta_organizer && ruff check . && black --check . && mypy .

# CLI (run from repo root; --db defaults to $PMO_DB, else photos.db)
python -m photo_meta_organizer.main index  --path "D:\photos" --db photos.db --workers 8
python -m photo_meta_organizer.main sync   --path "D:\photos" --db photos.db [--dry-run] [--cleanup-deleted]
python -m photo_meta_organizer.main search --camera Sony --db photos.db
python -m photo_meta_organizer.main stats  --db photos.db
python -m photo_meta_organizer.main prune  --db photos.db [--apply]   # drop records for non-image files; dry run by default
python -m photo_meta_organizer.main dedupe --db photos.db [--apply]   # merge records sharing a path (old MODIFIED bug); dry run by default
python -m photo_meta_organizer.main sync   --path "D:\photos" --db photos.db --rehash   # hash every file, ignoring size+mtime (slow)
# Pointing --db at an existing legacy *.json file (TinyDB) triggers a one-time import into a sibling *.db
# (SQLite) file; the .json is left untouched and the returned repository is the SQLite one (ADR-001, PMO-08).

# API — create_app() reads Settings from PMO_* env vars (PMO_DB, PMO_DATA_DIR, ...); default photos.db relative to the CWD, so start it from the repo root.
# It accepts only local Host headers (localhost, 127.0.0.1) and CORS only from the Vite dev origins; override with
# PMO_ALLOWED_HOSTS / PMO_CORS_ORIGINS (comma-separated) if you deliberately expose it. Keep it bound to 127.0.0.1.
# PMO_API_TOKEN (optional) makes every route but /health require it as the `pmo_token` cookie (api/auth.py, 401).
python -m scripts.seed_demo_data                        # optional demo data
python -m uvicorn photo_meta_organizer.api.app:create_app --factory --port 8000 --reload   # docs at /docs

# Frontend (from frontend/): dev server on :5173 proxies /api -> localhost:8000
npm run dev | npm run build   # build = tsc -b && vite build
npm run lint                  # oxlint, not eslint
npm test                      # Vitest + Testing Library (src/**/*.test.ts(x)); tsc -b type-checks tests too
# After changing a route or api/schemas.py: regenerate the frontend's API types and commit both files
python -m scripts.export_openapi && npm --prefix frontend run gen:api   # openapi.json -> src/api/schema.ts
# test_openapi_contract.py (pytest) and src/api/schema.test.ts (Vitest) fail until you do.

# Desktop (from repo root)
npm run desktop:dev | desktop:start | desktop:package
npm run backend:package       # uv run --group build: PyInstaller build of scripts/desktop_backend.py
```

Notes on the test config: `photo_meta_organizer/pytest.ini` is the only pytest config. The mypy settings are in `photo_meta_organizer/setup.cfg` (tests excluded; `mypy .` reports ~43 existing type errors as of 2026-09-27). `ruff check .` and `black --check .` report existing lint debt (~300 ruff findings, 37 unformatted files as of 2026-09-27); compare counts before/after a change rather than expecting zero. Markers are `unit` and `integration`, but most tests are not marked, so select by directory (`tests/unit`, `tests/integration`) rather than by marker.

## Architecture

Clean Architecture with Protocol-based ports. Dependencies point inward: `api`/`main` → `application` → `domain`; `infrastructure` implements the `application/interfaces` Protocols.

- **domain/** has no I/O and its models are frozen dataclasses. `models.py` holds `ImageMetadata` (the aggregate, keyed by `file_hash`), the three-tier `ImageExifData` (universal → common → camera-specific plus `raw_tags`), and the sync types `FileInfo`, `FileState`, `SyncResult`. `services.py` holds `CameraClassifier` and `MetadataStateAnalyzer`. Small rule modules: `curation.py` (rating 1-5, tag and label rules, shared by the API schema and the repository), `datetimes.py` (`to_naive`), `formats.py` (`IMAGE_EXTENSIONS`, `is_image_filename`).
- **application/interfaces/** defines three Protocols: `ImageRetriever` (discover files and open streams), `ImageMetadataExtractor` (stateless: `extract(file_handle, stream)`) and `ImageMetadataRepository`. Use cases live in `use_cases/` (`IndexPhotos`, `ParallelIndexPhotos`, `SynchronizeMetadata`, `SearchPhotos`, `PruneNonImages`). `orchestrators.py` holds `ExtractorOrchestrator` and `SyncOrchestrator`.
- **infrastructure/** is organized into subpackages: `retriever/` (`LocalDiskRetriever` wrapped by `ExtensionFilteredRetriever`, `S3ImageRetriever` — imports `boto3` via the optional `s3` extra, not wired into any CLI or API path), `extractors/` (`DiskMetaDataExtractor`), `repositories/` (`SqliteRepository`/`SqliteCollectionRepository` — the live backend, ADR-001; `TinyDBRepository`/`TinyDBCollectionRepository` kept only as the legacy-import source), `importers/` (`legacy_json_importer.import_legacy_json`, one-time TinyDB → SQLite migration), plus `ThumbnailService` and `metrics.ProgressReporter`.

**Composition root:** `application/settings.Settings` (frozen; flag > `PMO_*` env > default) is the one configuration object for the CLI (`--db`), `api.app.create_app(settings=...)` and the desktop backend (`api/desktop.py`); its `db_path` defaults to `photos.db`. `application/composition.py` builds retrievers and repositories for all of them: `build_repository(db_path)` always returns a `SqliteRepository`, transparently importing a legacy `.json` file into a sibling `.db` file the first time it's pointed at one (the `.json` is left untouched). `create_app` stores a `Services` container on `app.state`; routes get the repository, collections, job manager and thumbnail service through `api/dependencies.py`, typed as the application Protocols. There is no `dependency_overrides` wiring in production. `main.py` still picks the extractor itself, and `POST /api/index`/`/api/sync` build the extractor and use case in the router.

### Data flows to understand before changing them

- **Parallel indexing** (`ParallelIndexPhotosUseCase`): the main thread lists files, a `ThreadPoolExecutor` runs extraction, and results go through a bounded `queue.Queue(100)` to a **single dedicated DB-writer thread**, stopped by a poison pill. Extraction stays free of repository calls by convention; this predates SQLite (ADR-001) and the current `SqliteRepository` is itself thread-safe (`check_same_thread=False` plus an internal `RLock`), so the single-writer-thread design is now a serialization choice, not a hard TinyDB requirement. `main.py index` uses this path when `--workers > 1` (default 4); `--workers 1` falls back to the serial `IndexPhotosUseCase`.
- **Incremental sync** (`SynchronizeMetadataUseCase`): the disk scan builds `FileInfo` per path, then `MetadataStateAnalyzer.analyze_changes` (pure) classifies each path as NEW / MODIFIED / UNCHANGED / DELETED, and `SyncOrchestrator` applies the changes according to the flags. Deleting orphans is opt-in (`--cleanup-deleted`) by design. `--dry-run` reports counts and writes nothing. Exit code is 2 if any per-file errors occurred.
  - **Fingerprint is (size, mtime).** `ImageFileInfo.modified_time` is stored on every record (naive local time; `SyncOrchestrator` stamps it from the disk scan, `DiskMetaDataExtractor` also sets it). If size or mtime differs the file is hashed: same hash is UNCHANGED, a different hash is MODIFIED. Legacy records with no stored mtime are trusted on size alone and backfilled (`FileState.refresh_fingerprint` → `repository.refresh_fingerprints`, one batched write, reported as `SyncResult.fingerprints_refreshed`). An edit that keeps both size and mtime is only caught by `sync --rehash`.
  - **MODIFIED replaces, it does not add.** Content is the primary key, so an edit changes the hash. `SyncOrchestrator._persist` calls `repository.replace(previous_hash, new)` and `domain.curation.carry_over_curation` copies rating/flag/labels from the old record (and from any record that already had the new content, e.g. a NEW copy of a curated photo). `dedupe` repairs libraries that were synced before this fix.
- **SqliteRepository** (ADR-001, `infrastructure/repositories/sqlite_repository.py`): the live backend. It holds one shared `sqlite3.Connection` (`check_same_thread=False`, WAL journal mode) guarded by an `RLock`, so search filters/sorts in SQL instead of the old `list_all()`-then-filter-in-Python approach, and single-record writes no longer rewrite or reindex the whole store. Collections live in their own tables, via `SqliteCollectionRepository` sharing the same connection/lock. `TinyDBRepository` (`infrastructure/repositories/tinydb_repository.py`) still exists but only as the read source for `infrastructure/importers/legacy_json_importer.py`'s one-time migration of an old `.json` file into a `.db` file — it is no longer wired into the CLI or API at runtime.
- **Datetimes are naive local time** (ADR D3): EXIF has no timezone, so `captured_at` is a naive wall-clock value. Anything with tzinfo (API bounds ending in `Z`, old records) is reduced with `to_naive`, which drops tzinfo without shifting the clock. `SearchPhotosQuery` normalises its own bounds.
- **Curation input is validated in three places on purpose:** the Pydantic schema (422), `SqliteRepository` (raises `ValueError`, which the router maps to 422) and `_to_response` (tolerates a bad stored rating). Batch `action` is a `Literal`, `delete` is reported as `deleted_count`.
- **Identity:** `file_hash` (SHA-256) is the primary key and `save()` is an upsert on it, so identical content at two paths collapses into one record. `file_info.path` is the last path seen. Sync matches on resolved path, not hash.
- **User curation fields** (`rating`, `flagged`, `labels`) live on the same record as extracted metadata, and `save()` replaces the whole document. Re-running `index` over an already-curated library therefore resets them to the extractor's defaults.

### API and frontend

`api/routes/photos_router.py` defines the photo, collection, search/facets, index, sync and job routers; `api/routes/export_router.py` streams ZIP and JSON exports. `_to_response` converts domain objects to the Pydantic schemas in `api/schemas.py`, so adding a domain field means touching the model, `sqlite_repository._to_row`/`_from_row` (and the schema in `_SCHEMA_SQL`), `schemas.py` and `_to_response`, then regenerating the frontend types (`frontend/src/api/schema.ts` is generated; `types/metadata.ts` only aliases it). Response models inherit `ResponseModel`, so fields with defaults are required in the generated types. `/health` returns `{"status": "ok", "photo_count": ...}`, which the Electron shell uses to detect an already-running backend. Thumbnails (and `/preview`, a 2048 px WebP the lightbox uses) are WebP, cached on disk under `.cache/thumbnails/` and addressed by file hash; the cache is written atomically, renders are single-flight per key, and it is bounded by `PMO_THUMBNAIL_CACHE_MB` with LRU eviction. **Map view:** `POST /api/geo/clusters` (search filters + `bbox` viewport + `zoom`) returns grid clusters from `repository.geo_clusters` (SQL `GROUP BY` on a cell sized by `application/geo.cell_degrees_for_zoom`; keep `frontend/src/utils/geo.ts` in step), each labelled by the `PlaceNamer` port (`infrastructure/geo/offline_place_namer.py`, a bundled GeoNames `cities.tsv.gz` built by `scripts/build_cities.py`, listed in `scripts/build_backend.py` as PyInstaller data; no network). `SearchRequest.within` is the separate map-area *filter* behind "Show these in Library" (store `filterArea`, a chip, not a query-bar token); the Map view's own requests drop it. `GET /api/config` exposes opt-in `PMO_MAP_TILES_URL` (validated `http(s)` template); with none, `LeafletMap.tsx` draws the bundled `world-atlas` outline, so no coordinates leave the machine. The Map view is `React.lazy`-loaded (Leaflet + a 750 KB outline chunk); Leaflet is not testable in jsdom, so `MapExplorerView.test.tsx` mocks `LeafletMap` and the logic lives in `utils/geo.ts` and `maps/markers.ts`. HEIC/HEIF (pillow-heif) and camera RAW (rawpy: embedded preview) decode through `infrastructure/image_decoding.py`, shared by the extractor and the thumbnailer. A photo without an EXIF date has `captured_at = None` (sorted last); `sync --reextract` repairs records from before that rule.

If `frontend/dist/` exists, FastAPI serves it at `/` (assets mounted at `/assets`). Otherwise `/` returns a 404 page saying the frontend is not built. The frontend uses relative `/api` URLs everywhere (`frontend/src/api/client.ts`), which is why both the Vite proxy and the same-origin FastAPI serving work. State lives in Zustand stores (`stores/`). The server filters, sorts and pages the library: `usePhotoSearch()` (`hooks/usePhotos.ts`) is one `useInfiniteQuery` per filter set against `POST /api/search` (200 a page; key `['photos', 'search', request]`), built from the store's filters by `utils/search.ts`. All photo queries share the `['photos']` prefix (the map's geotagged set, single records); counts and analytics come from `GET /api/facets` (`useFacets`, key `['facets']`), and Select All uses `POST /api/search/ids`. Edits go through `hooks/usePhotoMutations.ts` (`useCuration`): optimistic update of every cached copy, replaced by the server record on success, rolled back per photo on failure, with an error toast; facets are refetched after. The Zustand store keeps only `inspectedHash`; `useInspectedPhoto()` serves the record from the cache or fetches it by hash. `?demo=1` runs the same filter rules over sample data (`demo/demoLibrary.ts`). `App.tsx` shows distinct loading, error (with Retry) and empty-library states; sample data appears only with `?demo=1`. `api/client.ts` throws `ApiError` carrying FastAPI's `detail`. The UI follows `design_docs/front_enddesign.md` (nav rail, query bar, justified grid or table, chapter Timeline). The Library view (`gallery/LibraryView.tsx`) shows the justified grid (`PhotoGallery.tsx`, rows from the pure `utils/justifiedLayout.ts`, exact heights so nothing is measured) or the table (`PhotoTable.tsx`, fixed 38 px rows), both TanStack-virtualized; the Timeline (chapters from `utils/chapters.ts`) and Kanban views load further pages from a `LoadMore` footer. The query bar (`header/QueryBar.tsx`) edits the same store filters as the Library panel through the pure `utils/query.ts` (parse, resolve, tokens to filters and back). Thumbnails are rendered upright by the backend (EXIF transpose) while stored `dimensions` are not, so aspect ratios swap for orientations 5-8 (`utils/photoFormat.photoAspectRatio`). Components read the Zustand stores through selectors (`useShallow`), and `PhotoCard` is memoised and reads `selectedHashes.has(hash)` directly, so do not rely on the non-reactive `isSelected()` helper for rendering.

### Desktop (Electron)

`desktop/src/main.ts` finds a free port (or reuses a healthy backend found via `/health`) and spawns the Python backend, either `scripts/desktop_backend.py` in dev or the PyInstaller bundle from `desktop/backend_dist` (copied to `resources/backend`) when packaged. It waits for the `DESKTOP_BACKEND_READY:<port>` line on stdout, then loads `http://127.0.0.1:<port>/`. When packaged it generates a per-launch token, passes it as `PMO_API_TOKEN` in the child's environment (never argv) and sets it as an HttpOnly, SameSite=Strict `pmo_token` cookie before loading the page; dev mode has no token. Packaged per-user data lives in `userData`: `photos.db`, `thumbnails/` (not `Cache/`, which is Chromium's) and `logs/`. Do not set `win.signAndEditExecutable: false` in `electron-builder.json`: the exe then keeps Electron's identity and antivirus flags it. The winCodeSign symlink error is fixed by Developer Mode or one elevated build. `preload.ts` exposes `window.electronAPI` (typed in `frontend/src/types/electron.d.ts`) for the native folder picker and backend info. `desktop:package` runs the frontend build first, but you must run `backend:package` yourself before packaging.

## Repo conventions

- `.github/instructions/` holds the project's rules. The ones that matter: Conventional Commits (`feat(scope): subject`), TDD (write or adjust tests first), type hints on all signatures, and 100-column lines for black and ruff. Run `python -m pytest` before committing, and keep coverage from dropping (README claims ~93%).
- Docs live in `DOCS/ARCHITECTURE.md` and `design_docs/PHASE_*.md`. `c4_docs.html`, `photo_meta_organizer_architecture.*`, `graph.json` and `scripts/*mermaid*` are generated architecture artifacts, not source.
