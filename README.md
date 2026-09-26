# Photo Meta Organizer

Metadata indexing and organization system built specifically for large-scale photo collections (20GB+). It automates the extraction of comprehensive EXIF data, performs content-based deduplication using SHA-256 hashing, and persists results in a queryable SQLite database (WAL mode). Built with **Clean Architecture** principles: retrievers, extractors, and repositories sit behind Protocol-based ports, so business logic does not depend on a specific backend.

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)
![React 19](https://img.shields.io/badge/React-19.0-61dafb)
![Tests](https://img.shields.io/badge/Tests-482%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/Coverage-92%25-green)
![Throughput](https://img.shields.io/badge/Throughput-21%2C710%20imgs%2Fmin-blue)
![License](https://img.shields.io/badge/License-MIT-green)

> **Status:** phases 0-4 are built; a hardening pass is well under way, with sync correctness, SQLite storage, async index/sync jobs, and accessibility done. A few UI features are still prototype-level, and some known gaps remain. Read [Known limitations](#known-limitations) before relying on it for a large library.

---

## ✨ Features

- **Interactive C4 Architecture Topology**: self-contained HTML architecture document following Simon Brown's C4 model (`DOCS/c4-architecture.html`, generated locally and git-ignored, not part of this repo) with interactive SVG pan/zoom and narrative tables across System Context (L1), Containers (L2), Components (L3), and Ingestion Flow (L4).
- **React 19 Frontend Studio**: Web UI built with React 19, TypeScript, Vite, Zustand, and TanStack Virtual. See [frontend/README.md](frontend/README.md) for its structure and conventions.
  - **Light & Dark Themes** with tokenized CSS variables.
  - **Lights Out Dimmer (`L`)**: ambient mode dimming sidebars and controls to emphasize photo viewing.
  - **Global Command Palette (`Ctrl + K`)**: fuzzy search across camera makes, tags, and actions.
  - **Studio Grid View**: row-virtualized gallery (only the rows near the viewport are in the DOM; measured 8,704 → 525 DOM elements on a 700-photo library) with a live density slider (160px-320px), flag badges, and star ratings.
  - **EXIF Inspector**: exposure triangle (Aperture, Shutter, ISO, Focal Length), technical telemetry, raw JSON copy. *The RGB/luminance histogram is a placeholder drawing, not computed from the image.*
  - **Filter Accordions** for Camera Brands, Tags & Labels, and Collections, with real camera/tag/year counts derived from your loaded library and real named collections from the Collections API (tags are ANDed, not ORed).
  - **Floating Selection Dock**: multi-select bar with cumulative size, batch tagging, and flag-all. *ZIP export is a placeholder — it shows an error toast, not a fake success.*
  - **Map Explorer**: *placeholder view with fixed example clusters, not derived from your library's GPS data.*
  - **Chronological Timeline Feed**: date-grouped photo stream with year scrubber.
  - **Kanban Staging Board**: 3-stage view (`Inbox`, `Picks & Flagged`, `Export Ready`) derived from rating and flag.
  - **Library Analytics Dashboard**: KPI metrics and SVG charts with click-to-filter drilldowns.
  - **Fullscreen Lightbox**: image stage, filmstrip, and keyboard navigation (`Space`, `Esc`, `P`, `1-5`).
- **Windows Desktop Application (Electron shell)**: starts the Python FastAPI backend on a free port, opens the UI, and provides a native folder picker for indexing. The packaged app keeps its data under the per-user data directory and sets a per-launch API token cookie (see [Security model](#security-model)); the `electron-builder` + `PyInstaller` pipeline is verified on the unpacked app (see [Known limitations](#known-limitations) for the remaining code-signing caveat).
- **WebP Thumbnail Cache & Streaming Service**: SHA-256 hash-addressed thumbnails with EXIF transpose correction, cached under `.cache/thumbnails/` (relative to the working directory).
- **Asynchronous Index & Sync Jobs**: `POST /api/index` and `POST /api/sync` return `202` plus a job id; `GET /api/jobs/{id}` reports progress and errors, and a job can be cancelled mid-run. The frontend shows a progress bar and an in-app folder dialog (`FolderJobDialog`) instead of `window.prompt`. Only image files are indexed, exactly as with the CLI.
- **Curation & Batch REST API**: `PATCH /api/photos/{hash}` for rating, flag, and tags, and `POST /api/photos/batch` for `add_tag`, `remove_tag`, `set_rating`, `set_flag`, and `delete`. Input is validated (rating 1-5 or `null`, non-empty tags, real booleans); bad input returns `422` and nothing is written.
- **Curated Collections API**: `GET/POST /api/collections` for named photo sets, consumed by the frontend's filter sidebar.
- **Facets API**: `GET /api/facets` returns camera/tag/year counts and GPS bounds computed in the repository; the frontend currently derives the same facets client-side from the loaded library, not yet from this endpoint.
- **CLI**: `index`, `sync`, `search`, `stats`, `prune` and `dedupe`, with tabular output via `tabulate`.
- **Multi-Threaded Parallel Indexing**: `ThreadPoolExecutor` workers, a bounded queue, and a dedicated DB-writer thread (21,710 imgs/min in the Phase 2 benchmark on a small database; not re-measured since the SQLite migration).
- **Comprehensive EXIF Extraction**: three-tier model (Universal → Common → Camera-Specific) for DSLR, mirrorless, mobile, action cam, and film scanner profiles, with automatic DMS → decimal GPS conversion (WGS84).
- **Content-Based Deduplication**: SHA-256 file hash as primary key.
- **Ports & Adapters**: retriever, extractor, and repository interfaces are Protocols. A local-disk retriever and a SQLite repository (WAL mode, per ADR-001) are wired in, with a one-time importer from legacy TinyDB `metadata.json` libraries; an S3 retriever exists but is not wired into the CLI or API, and there is no MongoDB backend yet.
- **Extension Filtering**: one shared list of image extensions (JPEG, PNG, TIFF, WebP, HEIC, RAW families, and more) used by both the CLI and the API.
- **Incremental Synchronization**: `sync` classifies files as NEW / MODIFIED / DELETED / UNCHANGED by comparing size and modification time, replaces the record on a MODIFIED and carries over its rating/flag/labels, and can repair libraries synced before that fix with `dedupe`. See the limitations below for the one case it still misses.
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
| `PMO_LOG_DIR` | Backend log directory (desktop backend) | `<data dir>/logs`, else no log file |
| `PMO_ALLOWED_HOSTS` | Host names the API accepts | `localhost,127.0.0.1` |
| `PMO_CORS_ORIGINS` | Origins granted CORS | the Vite dev origins |

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

# With verbose logging (global flag, placed before the command)
python -m photo_meta_organizer.main --log-level DEBUG index --path /photos --db photos.db

# View help
python -m photo_meta_organizer.main --help
```

Re-running `index` re-extracts every file and replaces each record, which resets its rating, flag, and labels. Use `sync` for routine updates.

### Library Statistics & CLI Search

```bash
# View library statistics
python -m photo_meta_organizer.main stats --db photos.db

# Search by camera make or model (substring match)
python -m photo_meta_organizer.main search --camera Sony --db photos.db

# Search by date range (YYYY-MM, YYYY-MM-DD, or ISO datetimes)
python -m photo_meta_organizer.main search --date-from 2026-01-01 --date-to 2026-12-31 --db photos.db

# Search near a GPS coordinate within a 25 km radius
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

### Run Tests

Run tests from the **`photo_meta_organizer/`** directory. Three test files import `tests.conftest`, which fails at collection when pytest is started from the repository root.

```bash
cd photo_meta_organizer

# All 311 unit and integration tests (pytest.ini also enables coverage)
python -m pytest

# Without coverage, one file, or one test
python -m pytest --no-cov tests/unit/domain/test_services.py
python -m pytest --no-cov tests/unit/domain/test_services.py::TestName::test_name
```

Frontend: `cd frontend && npm run build` (typechecks) and `npm run lint`. The frontend has no test suite yet.

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
│  ├── composition.py   Shared retriever factory (images only) │
│  ├── orchestrators.py ExtractorOrchestrator, SyncOrchestrator │
│  └── use_cases/       IndexPhotos, ParallelIndexPhotos,      │
│                       SearchPhotos, SynchronizeMetadata,      │
│                       PruneNonImages                          │
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
- **RAW and HEIC** files are accepted for indexing, but Pillow has no built-in decoder for them, so expect missing dimensions and thumbnails.
- **UI prototype areas:** the Map Explorer clusters, the EXIF histogram, and ZIP export are placeholders (see [Features](#-features)); JSON export is not implemented server-side either. The frontend still loads the whole library at startup and filters it in the browser (server-driven paging is planned). The frontend has no automated test suite.
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
| **Hardening** | 🚧 In progress | Correctness, security, scale (SQLite) and packaging fixes; most of the plan is done, remaining work below |
| **Phase 5** | 🔲 Planned | AI Tagging, Neural Image Embeddings & Semantic Search |
| **Phase 6** | 🔲 Planned | Cloud S3 / MinIO Blob Storage & Distributed MongoDB Scale-Out |

*Numbering note:* an internal design doc calls the Electron desktop app "Phase 5"; in this table it is part of Phase 4 and "Phase 5" means AI tagging.

**Hardening progress:** validated curation input, one datetime convention, images-only indexing in both the CLI and the API, the `prune` command, CORS and Host lock-down, and the virtualized gallery are done. Sync correctness (replace on modify, curation carry-over, mtime fingerprint, `dedupe`, `sync --rehash`), the frontend data layer (one react-query cache, honest loading/error/empty states, failed saves shown as failed), and the **SQLite migration** (repository port v2, legacy JSON importer, search/facets moved into the store) are done. Also done: real facets/collections and AND-semantics tag search in the sidebar, asynchronous index/sync jobs with progress and cancel, a single `Settings`/composition root, chunked content hashing, keyboard/screen-reader accessibility, and the per-launch desktop API token. Next: RAW/HEIC support, thumbnail-cache hardening, server-driven paging and ZIP/JSON export, a generated API client, and frontend tests.

---

## 🛠️ Technology Stack

| Layer | Technology |
|-------|-----------|
| **Frontend Framework** | React 19 + TypeScript + Vite |
| **State & Virtualization** | Zustand (selector subscriptions) + TanStack Virtual (gallery rows) |
| **Styling & Icons** | Tokenized CSS variables (Light/Dark), mostly inline styles, Lucide Icons |
| **Backend Runtime** | Python 3.11+ |
| **REST API Server** | FastAPI + Uvicorn + Pydantic v2 |
| **Image Processing** | Pillow (PIL) + WebP thumbnail cache |
| **EXIF Extraction** | exifread (three-tier Universal/Common/Raw model) |
| **Deduplication** | SHA-256 content-based file fingerprinting |
| **Database** | SQLite (WAL mode, single writer connection, ADR-001); legacy TinyDB JSON libraries are imported once and never modified |
| **Testing & Quality** | pytest + pytest-cov (482 tests, 92% coverage); oxlint + `tsc` for the frontend (no frontend test runner yet) |
| **Type System** | mypy + TypeScript |

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
