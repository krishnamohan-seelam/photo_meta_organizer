# Photo Meta Organizer

Metadata indexing and organization system built specifically for large-scale photo collections (20GB+). It automates the extraction of comprehensive EXIF data, performs content-based deduplication using SHA-256 hashing, and persists results in a queryable SQLite database (WAL mode). Built with **Clean Architecture** principles: retrievers, extractors, and repositories sit behind Protocol-based ports, so business logic does not depend on a specific backend.

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)
![React 19](https://img.shields.io/badge/React-19.0-61dafb)
![Tests](https://img.shields.io/badge/Tests-671%20backend%20%2B%20239%20frontend-brightgreen)
![Coverage](https://img.shields.io/badge/Coverage-93%25-green)
![Throughput](https://img.shields.io/badge/Throughput-~31%2C000%20imgs%2Fmin-blue)
![License](https://img.shields.io/badge/License-MIT-green)

> **Status:** phases 0-4 are built and the hardening pass is complete. Some known gaps remain. Read [Known limitations](#known-limitations) before relying on it for a large library.

---

## ✨ Features

- **Interactive C4 Architecture Topology**: self-contained HTML architecture document following Simon Brown's C4 model (`DOCS/c4-architecture.html`, generated locally and git-ignored, not part of this repo) with interactive SVG pan/zoom and narrative tables across System Context (L1), Containers (L2), Components (L3), and Ingestion Flow (L4).
- **React 19 Frontend Studio**: Web UI built with React 19, TypeScript, Vite, Zustand, and TanStack Virtual. See [frontend/README.md](frontend/README.md) for its structure and conventions, and [design_docs/front_enddesign.md](design_docs/front_enddesign.md) for the design it implements.
  - **Neutral, photo-first chrome**: hue-free greys in dark and light themes with one amber accent for selection, picks, primary actions and focus. A nav rail switches views (`G` Library, `T` Timeline, `M` Map, `C` Collections, `A` Insights) and toggles the Library panel (`\`), Details panel (`I`), Lights Out (`L`) and the theme; `?` lists every shortcut.
  - **Query bar**: filters as tokens with autocomplete from your library (makes, tags, years, collections, with counts). `/` focuses it. The syntax covers only what the search API can filter on:

    | Token | Filters by |
    | --- | --- |
    | `make:sony` | Camera make (several `make:` tokens are ORed) |
    | `model:"a7 iv"` | Camera model contains |
    | `tag:night` | Tag (several `tag:` tokens are ANDed) |
    | `in:"Japan 2026"` | Collection |
    | `pick:yes` | Picks (flagged) |
    | `rating:5` | Exact star rating 1-5 |
    | `year:2026`, `year:unknown` | Capture year, or no EXIF date |
    | `date:2026-05-14..2026-05-21`, `date:2026-05-14` | Capture date or inclusive range (replaces a year) |
    | `geo:yes`, `geo:no` | Has GPS coordinates |
    | `kyoto`, `"tokyo tower"` | Free text in file name, path, camera or tags |

    Field names are case-insensitive and quotes keep spaces. Unknown fields (`iso:800`) and invalid values are shown struck through in red and never sent. The bar, the Library panel and the toolbar chips edit the same filters, so they always agree.
  - **Library view, grid or table (`V`)**: justified rows that keep every photo's aspect ratio (EXIF-rotated portraits included; row height 140-340 px), or a dense sortable table (Name, Camera, Captured, Size sort on the server; Lens and Size columns drop out when space is short). Both are virtualized: with 20,000 photos the DOM holds at most 60 rows. The server filters, sorts and pages the library (200 photos a page), so the browser never loads the whole library.
  - **Keyboard culling**: `←`/`→` (grid) or `J`/`K` (table, `Shift` extends the selection) move through photos, `1`-`5` rate, `0` clears, `P` picks, `X` selects, `Enter` opens the viewer and `Esc` clears the selection. Ctrl-click toggles a photo, Shift-click selects a range in the table.
  - **Library panel**: All photos, Picks, exact star ratings, collections (create one from the selection), cameras with proportion bars, and tag pills, all with whole-library counts from `GET /api/facets`.
  - **Details inspector**: preview, rating and Pick, an RGB **histogram computed from the photo's pixels** (hidden when they cannot be read), an exposure strip, camera/lens/date/location/file details, hash and raw-JSON copy, and tag editing.
  - **Selection dock**: appears with a selection; shows its total size and offers Pick, batch Rate, Add to collection, Tag, and Export (a streamed ZIP of the originals with progress, or metadata JSON). Select All works across pages.
  - **Command Palette (`Ctrl + K`)**: views, Import/Sync, theme, Lights Out, the shortcut list, export the library as JSON, and a filter for each camera make and tag in your library.
  - **Timeline as chapters**: photos grouped into trip-like chapters (a new chapter after a gap you choose, 12 h to 7 days, default 36 h, or when the month changes) with a serif date-range title, a summary line, "Select chapter", and a mosaic where portraits, panoramas and each chapter's best photo get bigger tiles. Photos without an EXIF date form a final "Unknown date" chapter.
  - **Map Explorer**: a real map of your geotagged photos. The server groups them into clusters sized for the zoom level (`POST /api/geo/clusters`), honouring the same filters as the Library, and labels each with its nearest place ("Tokyo, Japan", or just the country when zoomed out) from a bundled offline city table. Click a group to zoom in, a single photo to inspect it, **Fit to photos** to see everything, and **Show these in Library** to narrow the Library to the visible area (a removable "Map area" chip). The basemap is a bundled country outline, so the map works offline and sends your coordinates nowhere; online tiles are opt-in (see `PMO_MAP_TILES_URL`).
  - **Kanban Staging Board** (the *Collections* view): 3 stages derived from rating, flag and the `export` tag, one stage per photo (Export Ready: 5 stars or tagged `export`; Picks: flagged or 4 stars; Inbox: the rest), with forward and back actions on each card.
  - **Library Analytics Dashboard** (the *Insights* view): KPI metrics and charts with click-to-filter drilldowns.
  - **Fullscreen Lightbox**: a 2048 px preview (works for HEIC and RAW too), a filmstrip, and keyboard navigation (arrows, `Esc`, `P`, `0`-`5`).
- **Windows Desktop Application (Electron shell)**: starts the Python FastAPI backend on a free port, opens the UI, and provides a native folder picker for indexing. The packaged app keeps its data under the per-user data directory and sets a per-launch API token cookie (see [Security model](#security-model)); the `electron-builder` + `PyInstaller` pipeline is verified on the unpacked app (see [Known limitations](#known-limitations) for the remaining code-signing caveat).
- **WebP Thumbnail Cache & Streaming Service**: SHA-256 hash-addressed thumbnails with EXIF transpose correction, cached under `.cache/thumbnails/` (or `PMO_CACHE_DIR`). Writes are atomic, each thumbnail renders once even under concurrent requests, and the cache is bounded by `PMO_THUMBNAIL_CACHE_MB` (default 1024) with least-recently-used eviction.
- **HEIC/HEIF and camera RAW**: decoded with pillow-heif and rawpy (the RAW file's embedded preview) for dimensions, thumbnails and the lightbox preview.
- **Export**: `POST /api/export/zip` streams a ZIP of the selected originals (skipped files are listed in an `export_report.txt` inside it); `POST /api/export/json` exports metadata for a selection or the whole library.
- **Asynchronous Index & Sync Jobs**: `POST /api/index` and `POST /api/sync` return `202` plus a job id; `GET /api/jobs/{id}` reports progress and errors, and a job can be cancelled mid-run. The frontend shows a progress bar and an in-app folder dialog (`FolderJobDialog`) instead of `window.prompt`. Only image files are indexed, exactly as with the CLI.
- **Curation & Batch REST API**: `PATCH /api/photos/{hash}` for rating, flag, and tags, and `POST /api/photos/batch` for `add_tag`, `remove_tag`, `set_rating`, `set_flag`, and `delete`. Input is validated (rating 1-5 or `null`, non-empty tags, real booleans); bad input returns `422` and nothing is written.
- **AI analysis API** (Phase 5): `GET /api/analysis/status`; `POST /api/analysis/model/download` (needs `{"accept": true}`, runs as a job with byte progress); `POST /api/analysis/run` (embeddings and suggested tags, a job); `POST /api/search/semantic` (free text or `like_hash`, with every normal search filter); `GET`/`POST /api/photos/{hash}/ai-tags` and `POST /api/ai-tags/batch` to accept, reject or reopen suggestions; `GET /api/ai-tags` for counts. Suggestions become labels only when accepted. Without the optional `ai` extra these answer `503`; without the model, `409`. See [AI analysis](#ai-analysis-phase-5-command-line-only-so-far).
- **Curated Collections API**: `GET/POST /api/collections` for named photo sets, used by the frontend's Library panel and selection dock.
- **Search & Facets API**: `POST /api/search` filters, sorts and pages in SQL; `POST /api/search/ids` returns every match for Select All; `GET /api/facets` returns camera/tag/year/ISO counts, GPS bounds and library stats. The frontend uses all three.
- **Generated API types**: the frontend's TypeScript types are generated from the API's OpenAPI schema, and a test on each side fails when they drift (see [Run Tests](#run-tests)).
- **CLI**: `index`, `sync`, `search`, `stats`, `prune` and `dedupe`, with tabular output via `tabulate`. Search input it cannot read (a bad date or location) is an error, not a silently unfiltered search.
- **Multi-Threaded Parallel Indexing**: `ThreadPoolExecutor` workers, a bounded queue, and a dedicated DB-writer thread. Measured after the SQLite migration (2026-10-03): 3,000 generated 640×480 JPEGs (16 MB, warm disk cache, 16-thread CPU) in 5.5-5.9 s with the default 4 workers, about **31,000 images/min** including process start-up. 8 workers was slower (6.6-6.9 s). Real camera files are larger and slower to hash and decode.
- **Comprehensive EXIF Extraction**: three-tier model (Universal → Common → Camera-Specific) for DSLR, mirrorless, mobile, action cam, and film scanner profiles, with automatic DMS → decimal GPS conversion (WGS84).
- **Content-Based Deduplication**: SHA-256 file hash as primary key.
- **Ports & Adapters**: retriever, extractor, and repository interfaces are Protocols. A local-disk retriever and a SQLite repository (WAL mode, per ADR-001) are wired in, with a one-time importer from legacy TinyDB `metadata.json` libraries; an S3 retriever exists but is not wired into the CLI or API, and there is no MongoDB backend yet.
- **Extension Filtering**: one shared list of image extensions (JPEG, PNG, TIFF, WebP, HEIC/HEIF, and RAW formats such as CR2, CR3, NEF, ARW, RAF, ORF, RW2 and DNG) used by both the CLI and the API.
- **Incremental Synchronization**: `sync` classifies files as NEW / MODIFIED / DELETED / UNCHANGED by comparing size and modification time, replaces the record on a MODIFIED and carries over its rating/flag/labels and collection membership, and can repair libraries synced before that fix with `dedupe`. It only touches records under the folder it scans. See the limitations below for the one case it still misses.
- **Local-Only API Hardening**: no wildcard CORS, the `Host` header is validated to block DNS-rebinding, and the packaged desktop app requires a per-launch API token cookie (see [Security model](#security-model)).

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+ & npm (for frontend development)
- [uv](https://docs.astral.sh/uv/) (manages the Python environment and the lockfile)

### Installation

```bash
# Clone the repository
git clone https://github.com/krishnamohan-seelam/photo_meta_organizer.git
cd photo_meta_organizer

# Create .venv with the exact locked versions (runtime + dev tools)
uv sync

# Activate it, or prefix commands with `uv run`
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS/Linux
```

Dependencies live in the root `pyproject.toml` (runtime, the `dev` group, the `build`
group for desktop packaging, and the optional `s3` extra) and are pinned in `uv.lock`.
Add one with `uv add <package>` (or `uv add --group dev <package>`) and commit both files.

---

## 🖥️ Running the Application (Backend & Frontend)

Run the API commands from the **repository root**: the database path (`photos.db`) and the thumbnail cache (`.cache/`) are relative to the working directory. `--db photos.db` still works against an old TinyDB library — it is imported once into a sibling `.db` file and never modified.

### Option A: Development Mode (Two Terminals with Hot-Reload)

#### Terminal 1: Backend REST API
```bash
# 1. Activate virtual environment
.venv\Scripts\activate

# 2. Seed sample demo photos and metadata (optional)
python -m scripts.seed_demo_data

# 3. Start FastAPI backend on port 8000 (loopback only)
python -m uvicorn photo_meta_organizer.api.app:create_app --factory --port 8000 --reload
```
*API Swagger documentation:* **`http://localhost:8000/docs`**

#### Terminal 2: React 19 Frontend
```bash
cd frontend
npm install
npm run dev        # Vite dev server on port 5173, proxies /api to localhost:8000
```
*Open your browser at:* **`http://localhost:5173`**

---

### Option B: Standalone Production Mode (Single Port)

Build the React frontend once and have FastAPI serve both the REST API and the React SPA on `http://localhost:8000`:

```bash
# 1. Build the production React SPA
cd frontend
npm run build
cd ..

# 2. Start the FastAPI server (serves the SPA at /)
python -m uvicorn photo_meta_organizer.api.app:create_app --factory --port 8000
```
*Open your browser at:* **`http://localhost:8000`**. Without `frontend/dist/`, `/` returns a "Frontend not built" page.

---

### Option C: Windows Desktop Application (Electron)

```bash
# 1. Build the frontend and launch the desktop application
npm run frontend:build
npm run desktop:start

# Live development mode with hot-reloading
npm run desktop:dev

# Package into an NSIS installer and portable executable
npm run backend:package      # builds the frontend, then the PyInstaller backend (uv's `build` group) with the UI inside
npm run desktop:package
```
*Output binaries are generated in:* `desktop/dist-package/`

The installed app keeps its data in the per-user data directory
(`%APPDATA%\Photo Meta Organizer\`): `photos.db`, `thumbnails\` and `logs\backend.log`.
Nothing is written to the install directory, so updates and reinstalls keep the library.
A database left by an older build in the install's `resources\` folder (`photos.db` or
`metadata.json`) is copied or imported once on first start; the original is not modified.

---

### Configuration

The CLI, the API and the desktop backend read the same settings (`application/settings.py`).
An explicit flag or argument wins, then the environment, then the development default:

| Variable | Meaning | Default |
|---|---|---|
| `PMO_DATA_DIR` | Base directory for the three paths below | (unset) |
| `PMO_DB` | SQLite database file | `<data dir>/photos.db`, else `photos.db` |
| `PMO_CACHE_DIR` | Thumbnail cache | `<data dir>/thumbnails`, else `.cache/thumbnails` |
| `PMO_MODEL_DIR` | Where the downloaded AI model lives | `<data dir>/models`, else `.cache/models` |
| `PMO_LOG_DIR` | Directory for a rotating log (CLI: `photo_meta_organizer.log`, also `--log-dir`; desktop backend: `backend.log`) | `<data dir>/logs`, else no log file |
| `PMO_THUMBNAIL_CACHE_MB` | Size budget of the thumbnail cache | `1024` |
| `PMO_ALLOWED_HOSTS` | Host names the API accepts | `localhost,127.0.0.1` |
| `PMO_CORS_ORIGINS` | Origins granted CORS | the Vite dev origins |
| `PMO_MAP_TILES_URL` | Opt-in online map tiles, an `http(s)` template containing `{z}`, `{x}` and `{y}`. The browser then asks that server for tiles, which reveals the area you are viewing | (unset: offline outline) |
| `PMO_MAP_TILES_ATTRIBUTION` | Credit line the map shows for that tile server | (unset) |

Relative paths are relative to the working directory, so start the API from the repository root.

### Security model

The API is meant to be reachable only by the local user's own front end. Three defenses enforce that:

- **CORS** allows only the Vite dev origins (`http://localhost:5173`, `http://127.0.0.1:5173`), never `*`, and grants no credentials. The built UI and the desktop shell are same-origin and need no CORS.
- **Host header check** accepts only `localhost` and `127.0.0.1` (plus `testserver` for the test client). Requests with any other `Host` get `400`, which blocks DNS-rebinding.
- **Per-launch API token** (desktop app). When `PMO_API_TOKEN` is set, every request except `/health` must carry it in the `pmo_token` cookie, or it gets `401`. The packaged desktop app generates a random token on each launch, passes it to the backend in the environment (never on the command line), and sets it as an `HttpOnly`, `SameSite=Strict` cookie in its own window only. Other local programs and web pages therefore cannot use the backend. Without the cookie, `/health` returns only `{"status": "ok"}`. The dev server and `uvicorn` runs have no token unless you set `PMO_API_TOKEN` yourself.

Keep the server bound to `127.0.0.1`. If you deliberately expose it on a LAN name, set `PMO_ALLOWED_HOSTS` (comma-separated) and/or `PMO_CORS_ORIGINS`, and accept that anyone on that network can then read and change the library unless you also set a token. CORS stops a hostile web page from *reading* responses, not from *sending* requests; the token is what blocks sending.

---

### Index Your Photos

Only image files are indexed; other files in the folder are skipped.

```bash
# Index all images in a directory (uses 4 workers by default)
python -m photo_meta_organizer.main index --path "C:\your\photos" --db photos.db

# Index with a specific number of worker threads
python -m photo_meta_organizer.main index --path "C:\your\photos" --db photos.db --workers 8

# With verbose logging (global flags, placed before the command). Log lines go to stderr;
# --log-dir (or PMO_LOG_DIR) also writes a rotating photo_meta_organizer.log there.
python -m photo_meta_organizer.main --log-level DEBUG --log-dir logs index --path /photos --db photos.db

# View help
python -m photo_meta_organizer.main --help
```

`--path` is required for `index` and `sync`. Re-running `index` re-extracts every file and replaces each record, which resets its rating, flag, and labels. Use `sync` for routine updates.

### Library Statistics & CLI Search

```bash
# View library statistics
python -m photo_meta_organizer.main stats --db photos.db

# Search by camera make or model (substring match)
python -m photo_meta_organizer.main search --camera Sony --db photos.db

# Search by date range (YYYY-MM, YYYY-MM-DD, or ISO datetimes). A bare day or month as the end
# covers the whole period: --date-to 2026-12-31 includes photos taken on the 31st.
python -m photo_meta_organizer.main search --date-from 2026-01-01 --date-to 2026-12-31 --db photos.db

# One month or one day
python -m photo_meta_organizer.main search --date 2026-03 --db photos.db

# Search near a GPS coordinate within a 25 km radius (all three flags, or --location lat,lon,km)
python -m photo_meta_organizer.main search --lat 35.6586 --lon 139.7454 --radius 25 --db photos.db

# Tags: a photo must have ALL listed tags
python -m photo_meta_organizer.main search --tags travel,japan --db photos.db
```

**Dates are naive local time.** EXIF has no timezone, so `captured_at` is the wall-clock time the camera recorded. Date bounds that carry a timezone (for example `...Z` in an API request) have the timezone dropped, not converted.

### Sync Your Library (Incremental)

```bash
# Index new photos and update modified ones
python -m photo_meta_organizer.main sync --path "C:\your\photos" --db photos.db

# Also remove records for files that no longer exist
python -m photo_meta_organizer.main sync --path /photos --db photos.db --cleanup-deleted

# Preview changes without writing to the DB
python -m photo_meta_organizer.main sync --path /photos --db photos.db --dry-run
```

### AI analysis (Phase 5, command line only so far)

`analyze` computes an AI embedding for every photo and suggests tags from a fixed vocabulary of about 540 labels. It needs the optional `ai` extra and a one-time model download (about 305 MB, OpenAI's CLIP ViT-B/32 under the MIT licence). Everything runs on your computer; only the model is downloaded, and your photos never leave it.

```bash
uv sync --extra ai     # a plain `uv sync` removes the extra

# First time: shows what will be downloaded and asks before doing it (--yes agrees up front)
python -m photo_meta_organizer.main analyze --db photos.db --download

# Afterwards: only photos with no embedding yet are processed, so it is safe to interrupt and re-run
python -m photo_meta_organizer.main analyze --db photos.db
python -m photo_meta_organizer.main analyze --db photos.db --no-tags --limit 500 --reanalyze
```

Suggested tags never touch your own tags until you accept them, and a rejected suggestion is not suggested for that photo again. A modified file is analysed again on the next run. Expect roughly 10 photos a second (about 35 minutes for 20,000), once. The same work is available over the API (see Features): download the model, run the analysis, search by meaning and review tags, all as jobs and requests. The web UI for it comes in the next step; until then use the CLI or `/docs`.

### Prune Non-Image Records

Earlier versions of `POST /api/index` indexed every file in a folder, so a library built through the UI may contain records for `.txt`, `.mp4`, `Thumbs.db`, and similar. `sync --cleanup-deleted` cannot remove them because the files still exist.

```bash
# Dry run (default): list what would be removed
python -m photo_meta_organizer.main prune --db photos.db

# Actually delete those records (files on disk are never touched)
python -m photo_meta_organizer.main prune --db photos.db --apply
```

Back up `photos.db` before any command that deletes records.

### Repair Duplicate Paths and Force a Full Re-check

Before this fix, syncing an edited file saved the new content as a second record and left the old one behind. `dedupe` keeps the newest record for each path and merges the rating, flag and labels of the others into it.

```bash
# Dry run (default)
python -m photo_meta_organizer.main dedupe --db photos.db

# Merge them
python -m photo_meta_organizer.main dedupe --db photos.db --apply
```

`sync` compares each file's size and modification time with what was stored and hashes only the files that differ. Records created by older versions have no stored time; they are trusted on size and filled in on the next sync. To hash every file regardless (slow, reads the whole library), for example after an edit that preserved size and mtime:

```bash
python -m photo_meta_organizer.main sync --path "D:\photos" --db photos.db --rehash
```

Records indexed before the capture-date fix may carry the file's modification time as their capture date. `--reextract` re-reads every file already in the database and keeps ratings, flags, labels and the date added (slow; back up `photos.db` first):

```bash
python -m photo_meta_organizer.main sync --path "D:\photos" --db photos.db --reextract
```

### Run Tests

Run backend tests from the **`photo_meta_organizer/`** directory. Three test files import `tests.conftest`, which fails at collection when pytest is started from the repository root.

```bash
cd photo_meta_organizer

# All 671 unit and integration tests (pytest.ini also enables coverage, 94%)
python -m pytest

# Without coverage, one file, or one test
python -m pytest --no-cov tests/unit/domain/test_services.py
python -m pytest --no-cov tests/unit/domain/test_services.py::TestName::test_name
```

Frontend (from `frontend/`): `npm test` runs the Vitest + Testing Library suite (239 tests: API client errors, optimistic edits and rollback, loading/error/empty states, the Map view and the data-layer helpers), `npm run build` typechecks (tests included) and builds, and `npm run lint` runs oxlint.

**After changing the API** (a route, or a schema in `api/schemas.py`), regenerate the frontend's types and commit both files; `test_openapi_contract.py` (pytest) and `schema.test.ts` (Vitest) fail until you do:

```bash
python -m scripts.export_openapi       # from the repo root: writes frontend/openapi.json
npm --prefix frontend run gen:api      # writes frontend/src/api/schema.ts
```

---

## 🏗️ Architecture

The project follows **Clean Architecture** with dependency inversion:
- **System Architecture & Data Flows:** **[DOCS/ARCHITECTURE.md](DOCS/ARCHITECTURE.md)**

Design docs for individual phases and the SQLite ADR live in `design_docs/`, which is git-ignored and not part of this repository, so they aren't linked here.

```
┌──────────────────────────────────────────────────────────────┐
│  Presentation Layer (FastAPI & React 19 Frontend)            │
│  ├── frontend/        React 19 + TypeScript + Vite + Zustand │
│  ├── api/routes/      REST Endpoints (/photos, /collections) │
│  └── main.py          CLI interface                          │
└────────────────────────────┬─────────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────────┐
│  Application Layer                                           │
│  ├── interfaces/      Protocols (ImageRetriever,             │
│  │                    ImageMetadataExtractor,                 │
│  │                    ImageMetadataRepository)                │
│  ├── composition.py   Builds retrievers and repositories     │
│  ├── settings.py      One Settings object for every entry    │
│  ├── jobs.py          Background index/sync jobs             │
│  ├── orchestrators.py ExtractorOrchestrator, SyncOrchestrator │
│  └── use_cases/       IndexPhotos, ParallelIndexPhotos,      │
│                       SearchPhotos, SynchronizeMetadata,      │
│                       PruneNonImages, DedupePaths             │
└────────────────────────────┬─────────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────────┐
│  Domain Layer (models, rules, domain services)               │
│  ├── models.py     ImageMetadata, SyncResult, FileState, ... │
│  ├── services.py   CameraClassifier, MetadataStateAnalyzer   │
│  ├── curation.py   Rating / tag rules                        │
│  ├── datetimes.py  Naive-local datetime convention           │
│  └── formats.py    Indexable image extensions                │
└──────────────────────────────────────────────────────────────┘
```

Concrete implementations live in `infrastructure/` (local-disk retriever, extension filter, EXIF extractor, SQLite repository, thumbnail service; a legacy TinyDB repository is kept only as the source for a one-time import). `application/composition.py` is the one place that builds the retriever *and* the repository (SQLite vs. legacy import) for the CLI, the API, and the desktop backend; `main.py` still builds the extractor itself.

---

<a id="known-limitations"></a>

## ⚠️ Known limitations

These are open, documented gaps. The full analysis and work plan are tracked in internal design docs (`design_docs/`, git-ignored, not part of this repository).

- **Sync still trusts size + modification time, not content, for the common case.** An edit that preserves both is invisible to a normal `sync`; run `sync --rehash` to force a full hash check. (An edit that changes size or mtime *is* detected, and now correctly replaces the old record and carries over its rating/flag/labels — `dedupe` repairs libraries synced before that fix.)
- **RAW and HEIC were verified on a real Nikon NEF only.** HEIC tests use pillow-heif's own encoder; no real phone HEIC or Canon CR3 / Sony ARW file has been tried, and the packaged desktop build has not been checked with the new native libraries.
- **Old capture dates.** Libraries indexed before the capture-date fix may show a file's modification time as its capture date. Run `sync --reextract` once to repair them.
- The query bar can filter only on what the search API supports: no ISO, aperture, focal-length or lens filters, no rating ranges. The map area chosen with "Show these in Library" is a filter of its own (a chip), not a query-bar token.
- **Map details:** place names come from cities of 15,000+ inhabitants ([GeoNames](https://www.geonames.org), CC BY 4.0), so a photo in a village is named after the nearest such city; the offline outline is Natural Earth's 1:50m countries, coarse at street zoom (use online tiles for detail). Clusters ignore the radius filter, and the packaged desktop build has not been checked with the new data file.
- **Kanban moves change ratings.** Stages are derived, not stored, so moving a card back from Export Ready drops the 5th star, and moving it back from Picks caps the rating at 3.
- **Batch edits after Select All** update photos that are not loaded on the server only, and a photo edited out of the current filter stays visible until the next reload.
- **Desktop packaging on Windows needs symlink permission once.** electron-builder unpacks its `winCodeSign` tool, which contains macOS symlinks; without Windows Developer Mode (or one run from an elevated shell) `npm run desktop:package` fails at that step. Do not work around it with `"signAndEditExecutable": false`: that also skips writing the app's name and version into the exe, which is left posing as `electron.exe`, and antivirus heuristics then flag it. Once `%LOCALAPPDATA%\electron-builder\Cache\winCodeSign\winCodeSign-2.6.0` exists, later builds need no special permission.
- **The Windows build is unsigned**, so SmartScreen warns on first run and some antivirus products may still flag it until it is code-signed. On a freshly built copy, the first start can take several seconds while the antivirus scans the backend files.
- **API token only in the desktop app.** The dev server and `uvicorn` runs rely on the CORS and Host checks unless `PMO_API_TOKEN` is set.

---

## 🗺️ Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| **Phase 0** | ✅ Complete | Foundation: domain models, interfaces, test infrastructure |
| **Phase 1** | ✅ Complete | MVP: local disk indexing, TinyDB persistence, CLI |
| **Phase 1.5**| ✅ Complete | Incremental Sync: NEW/MODIFIED/DELETED detection (see limitations) |
| **Phase 2** | ✅ Complete | Parallel processing (ThreadPoolExecutor + Queue) |
| **Phase 3** | ✅ Complete | Search & indexing + FastAPI REST API + CLI search & stats |
| **Phase 4** | ✅ Complete | React 19 Studio UI, WebP thumbnail cache, curation API, Electron shell |
| **Hardening** | ✅ Complete | Correctness, security, scale (SQLite), packaging, server-driven UI, generated API types and tests |
| **Phase 5** | 🚧 In progress | AI Tagging, Neural Image Embeddings & Semantic Search: storage, model, `analyze` command and API done; web UI to come |
| **Phase 6** | 🔲 Planned | Cloud S3 / MinIO Blob Storage & Distributed MongoDB Scale-Out |

*Numbering note:* an internal design doc calls the Electron desktop app "Phase 5"; in this table it is part of Phase 4 and "Phase 5" means AI tagging.

**Hardening:** validated curation input, one datetime convention, images-only indexing, `prune` and `dedupe`, CORS/Host lock-down and the per-launch desktop token; sync correctness (replace on modify, curation carry-over, mtime fingerprint, `--rehash`, `--reextract`, folder-scoped cleanup); the SQLite migration with search, paging and facets in the store; asynchronous index/sync jobs with progress and cancel; one `Settings` object and composition root; HEIC/RAW decoding; a bounded thumbnail cache; server-driven paging, filtering and sorting in the UI; ZIP and JSON export; accessibility and keyboard handling; logging and CLI fixes; API types generated from OpenAPI; and a frontend test suite. What is left is under [Known limitations](#known-limitations).

---

## 🛠️ Technology Stack

| Layer | Technology |
|-------|-----------|
| **Frontend Framework** | React 19 + TypeScript + Vite; Leaflet for the Map view (lazy-loaded) |
| **State & Virtualization** | Zustand (selector subscriptions) + TanStack Virtual (gallery rows) |
| **Styling & Icons** | Tokenized CSS variables (Light/Dark), mostly inline styles (no Tailwind), Lucide Icons |
| **Backend Runtime** | Python 3.11+ |
| **REST API Server** | FastAPI + Uvicorn + Pydantic v2 |
| **Image Processing** | Pillow, pillow-heif (HEIC/HEIF), rawpy (camera RAW) + WebP thumbnail cache |
| **EXIF Extraction** | exifread (three-tier Universal/Common/Raw model) |
| **Deduplication** | SHA-256 content-based file fingerprinting |
| **Database** | SQLite (WAL mode, single writer connection, ADR-001); legacy TinyDB JSON libraries are imported once and never modified |
| **Testing & Quality** | pytest + pytest-cov (671 tests, 94% coverage); Vitest + Testing Library (239 tests), oxlint and `tsc` for the frontend |
| **Type System** | mypy + TypeScript (API types generated with openapi-typescript) |

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
