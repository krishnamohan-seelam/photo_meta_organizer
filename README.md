# Photo Meta Organizer

Metadata indexing and organization system built specifically for large-scale photo collections (20GB+). It automates the extraction of comprehensive EXIF data, performs content-based deduplication using SHA-256 hashing, and persists results in a structured, queryable JSON repository. Built with **Clean Architecture** principles: retrievers, extractors, and repositories sit behind Protocol-based ports, so business logic does not depend on a specific backend.

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)
![React 19](https://img.shields.io/badge/React-19.0-61dafb)
![Tests](https://img.shields.io/badge/Tests-311%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/Coverage-92%25-green)
![Throughput](https://img.shields.io/badge/Throughput-21%2C710%20imgs%2Fmin-blue)
![License](https://img.shields.io/badge/License-MIT-green)

> **Status:** phases 0-4 are built, and a hardening pass is under way. Several UI features are still prototype-level, and some known defects are open. Read [Known limitations](#known-limitations) before relying on it for a large library.

---

## ✨ Features

- **Interactive C4 Architecture Topology**: self-contained HTML architecture document following Simon Brown's C4 model ([DOCS/c4-architecture.html](DOCS/c4-architecture.html)) with interactive SVG pan/zoom and narrative tables across System Context (L1), Containers (L2), Components (L3), and Ingestion Flow (L4).
- **React 19 Frontend Studio**: Web UI built with React 19, TypeScript, Vite, Zustand, and TanStack Virtual. See [frontend/README.md](frontend/README.md) for its structure and conventions.
  - **Light & Dark Themes** with tokenized CSS variables.
  - **Lights Out Dimmer (`L`)**: ambient mode dimming sidebars and controls to emphasize photo viewing.
  - **Global Command Palette (`Ctrl + K`)**: fuzzy search across camera makes, tags, and actions.
  - **Studio Grid View**: row-virtualized gallery (only the rows near the viewport are in the DOM; measured 8,704 → 525 DOM elements on a 700-photo library) with a live density slider (160px-320px), flag badges, and star ratings.
  - **EXIF Inspector**: exposure triangle (Aperture, Shutter, ISO, Focal Length), technical telemetry, raw JSON copy. *The RGB/luminance histogram is a placeholder drawing, not computed from the image.*
  - **Filter Accordions** for Camera Brands, Tags & Labels, and Collections. *The lists in the sidebar are placeholder data, not derived from your library.*
  - **Floating Selection Dock**: multi-select bar with cumulative size, batch tagging, and flag-all. *ZIP export is a placeholder.*
  - **Map Explorer**: *placeholder view with fixed example clusters.*
  - **Chronological Timeline Feed**: date-grouped photo stream with year scrubber.
  - **Kanban Staging Board**: 3-stage view (`Inbox`, `Picks & Flagged`, `Export Ready`) derived from rating and flag.
  - **Library Analytics Dashboard**: KPI metrics and SVG charts with click-to-filter drilldowns.
  - **Fullscreen Lightbox**: image stage, filmstrip, and keyboard navigation (`Space`, `Esc`, `P`, `1-5`).
- **Windows Desktop Application (Electron shell)**: starts the Python FastAPI backend on a free port, opens the UI, and provides a native folder picker for indexing. The `electron-builder` + `PyInstaller` packaging pipeline exists but has not been verified end to end (see [Known limitations](#known-limitations)).
- **WebP Thumbnail Cache & Streaming Service**: SHA-256 hash-addressed thumbnails with EXIF transpose correction, cached under `.cache/thumbnails/` (relative to the working directory).
- **Folder Indexing REST API**: `POST /api/index` runs multi-threaded extraction over a directory. Only image files are indexed, exactly as with the CLI.
- **Curation & Batch REST API**: `PATCH /api/photos/{hash}` for rating, flag, and tags, and `POST /api/photos/batch` for `add_tag`, `remove_tag`, `set_rating`, `set_flag`, and `delete`. Input is validated (rating 1-5 or `null`, non-empty tags, real booleans); bad input returns `422` and nothing is written.
- **Curated Collections API**: `GET/POST /api/collections` for named photo sets. *The UI does not use it yet.*
- **CLI**: `index`, `sync`, `search`, `stats`, `prune` and `dedupe`, with tabular output via `tabulate`.
- **Multi-Threaded Parallel Indexing**: `ThreadPoolExecutor` workers, a bounded queue, and a dedicated DB-writer thread (21,710 imgs/min in the Phase 2 benchmark on a small database; not re-measured since).
- **Comprehensive EXIF Extraction**: three-tier model (Universal → Common → Camera-Specific) for DSLR, mirrorless, mobile, action cam, and film scanner profiles, with automatic DMS → decimal GPS conversion (WGS84).
- **Content-Based Deduplication**: SHA-256 file hash as primary key.
- **Ports & Adapters**: retriever, extractor, and repository interfaces are Protocols. A local-disk retriever and a TinyDB repository are wired in; an S3 retriever exists but is not wired into the CLI or API, and there is no MongoDB backend yet.
- **Extension Filtering**: one shared list of image extensions (JPEG, PNG, TIFF, WebP, HEIC, RAW families, and more) used by both the CLI and the API.
- **Incremental Synchronization**: `sync` classifies files as NEW / MODIFIED / DELETED / UNCHANGED. See the limitations below for what it can currently miss.
- **Local-Only API Hardening**: no wildcard CORS, and the `Host` header is validated to block DNS-rebinding (see [Security model](#security-model)).

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

Run the API commands from the **repository root**: the database path (`metadata.json`) and the thumbnail cache (`.cache/`) are relative to the working directory.

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

# Package into an NSIS installer and portable executable (see Known limitations first)
npm run backend:package      # PyInstaller build of the backend (uv adds PyInstaller from the `build` group)
npm run desktop:package
```
*Output binaries are generated in:* `desktop/dist-package/`

---

### Security model

The API has **no authentication**, so it must only be reachable by the local user's own front end. Two defenses enforce that:

- **CORS** allows only the Vite dev origins (`http://localhost:5173`, `http://127.0.0.1:5173`), never `*`, and grants no credentials. The built UI and the desktop shell are same-origin and need no CORS.
- **Host header check** accepts only `localhost` and `127.0.0.1` (plus `testserver` for the test client). Requests with any other `Host` get `400`, which blocks DNS-rebinding.

Keep the server bound to `127.0.0.1`. If you deliberately expose it on a LAN name, set `PMO_ALLOWED_HOSTS` (comma-separated) and/or `PMO_CORS_ORIGINS`, and accept that anyone on that network can then read and change the library. Note that CORS stops a hostile web page from *reading* responses, not from *sending* requests; a per-launch API token is planned.

---

### Index Your Photos

Only image files are indexed; other files in the folder are skipped.

```bash
# Index all images in a directory (uses 4 workers by default)
python -m photo_meta_organizer.main index --path "C:\your\photos" --db metadata.json

# Index with a specific number of worker threads
python -m photo_meta_organizer.main index --path "C:\your\photos" --db metadata.json --workers 8

# With verbose logging (global flag, placed before the command)
python -m photo_meta_organizer.main --log-level DEBUG index --path /photos --db metadata.json

# View help
python -m photo_meta_organizer.main --help
```

Re-running `index` re-extracts every file and replaces each record, which resets its rating, flag, and labels. Use `sync` for routine updates.

### Library Statistics & CLI Search

```bash
# View library statistics
python -m photo_meta_organizer.main stats --db metadata.json

# Search by camera make or model (substring match)
python -m photo_meta_organizer.main search --camera Sony --db metadata.json

# Search by date range (YYYY-MM, YYYY-MM-DD, or ISO datetimes)
python -m photo_meta_organizer.main search --date-from 2026-01-01 --date-to 2026-12-31 --db metadata.json

# Search near a GPS coordinate within a 25 km radius
python -m photo_meta_organizer.main search --lat 35.6586 --lon 139.7454 --radius 25 --db metadata.json

# Tags: a photo must have ALL listed tags
python -m photo_meta_organizer.main search --tags travel,japan --db metadata.json
```

**Dates are naive local time.** EXIF has no timezone, so `captured_at` is the wall-clock time the camera recorded. Date bounds that carry a timezone (for example `...Z` in an API request) have the timezone dropped, not converted.

### Sync Your Library (Incremental)

```bash
# Index new photos and update modified ones
python -m photo_meta_organizer.main sync --path "C:\your\photos" --db metadata.json

# Also remove records for files that no longer exist
python -m photo_meta_organizer.main sync --path /photos --db metadata.json --cleanup-deleted

# Preview changes without writing to the DB
python -m photo_meta_organizer.main sync --path /photos --db metadata.json --dry-run
```

### Prune Non-Image Records

Earlier versions of `POST /api/index` indexed every file in a folder, so a library built through the UI may contain records for `.txt`, `.mp4`, `Thumbs.db`, and similar. `sync --cleanup-deleted` cannot remove them because the files still exist.

```bash
# Dry run (default): list what would be removed
python -m photo_meta_organizer.main prune --db metadata.json

# Actually delete those records (files on disk are never touched)
python -m photo_meta_organizer.main prune --db metadata.json --apply
```

Back up `metadata.json` before any command that deletes records.

### Repair Duplicate Paths and Force a Full Re-check

Before this fix, syncing an edited file saved the new content as a second record and left the old one behind. `dedupe` keeps the newest record for each path and merges the rating, flag and labels of the others into it.

```bash
# Dry run (default)
python -m photo_meta_organizer.main dedupe --db metadata.json

# Merge them
python -m photo_meta_organizer.main dedupe --db metadata.json --apply
```

`sync` compares each file's size and modification time with what was stored and hashes only the files that differ. Records created by older versions have no stored time; they are trusted on size and filled in on the next sync. To hash every file regardless (slow, reads the whole library), for example after an edit that preserved size and mtime:

```bash
python -m photo_meta_organizer.main sync --path "D:\photos" --db metadata.json --rehash
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
- **Phase 3 Search & API Design:** **[design_docs/PHASE_3_DESIGN.md](design_docs/PHASE_3_DESIGN.md)**
- **Phase 4 Frontend UI Design:** **[design_docs/PHASE_4_UI_DESIGN.md](design_docs/PHASE_4_UI_DESIGN.md)**
- **Phase 4 Completion Report:** **[design_docs/PHASE_4_COMPLETION.md](design_docs/PHASE_4_COMPLETION.md)**
- **Storage decision (SQLite):** **[design_docs/ADR-001-sqlite-storage.md](design_docs/ADR-001-sqlite-storage.md)**

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

Concrete implementations live in `infrastructure/` (local-disk retriever, extension filter, EXIF extractor, TinyDB repository, thumbnail service). `main.py` and `api/app.py` still build the extractor and repository themselves; only the retriever is shared.

---

<a id="known-limitations"></a>

## ⚠️ Known limitations

These are open, documented defects and gaps. The full analysis is in [design_docs/design_flaws.md](design_docs/design_flaws.md) and the work plan in [design_docs/design_flaws_tickets.md](design_docs/design_flaws_tickets.md).

- **Sync can miss changes and leave duplicates.** It detects modification by file **size only**, so an edit that keeps the same size is not noticed. A file that does change gets a *new* record (the hash is the key) and the old record is not removed.
- **Storage does not scale yet.** TinyDB rewrites the whole JSON file on every write, and every search loads and filters all records in Python. Fine for hundreds to low thousands of photos; slow beyond that. The repository has no locking, so avoid running the CLI against a database a running server is using. Migration to SQLite is decided ([ADR-001](design_docs/ADR-001-sqlite-storage.md)).
- **RAW and HEIC** files are accepted for indexing, but Pillow has no built-in decoder for them, so expect missing dimensions and thumbnails.
- **UI prototype areas:** the filter sidebar lists, the Map Explorer clusters, the EXIF histogram, and ZIP/JSON export are placeholders (see [Features](#-features)). The Collections API is not connected to the UI. The frontend loads the whole library at startup and filters it in the browser.
- **Indexing through the UI is one blocking request** with no progress or cancel.
- **Desktop packaging is unverified.** As configured, the built frontend is not bundled into the PyInstaller backend and the database would be created in the install directory. Do not distribute an installer until this is checked.
- **No API authentication** beyond the CORS and Host checks described above.

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
| **Hardening** | 🚧 In progress | Correctness, security, and scale fixes; SQLite storage. Plan: [design_flaws_tickets.md](design_docs/design_flaws_tickets.md) |
| **Phase 5** | 🔲 Planned | AI Tagging, Neural Image Embeddings & Semantic Search |
| **Phase 6** | 🔲 Planned | Cloud S3 / MinIO Blob Storage & Distributed MongoDB Scale-Out |

*Numbering note:* `design_docs/PHASE_5_COMPLETION.md` calls the Electron desktop app "Phase 5"; in this table it is part of Phase 4 and "Phase 5" means AI tagging.

**Hardening progress:** validated curation input, one datetime convention, images-only indexing in both the CLI and the API, the `prune` command, CORS and Host lock-down, and the virtualized gallery are done. Sync correctness (replace on modify, curation carry-over, mtime fingerprint, `dedupe`, `sync --rehash`) and the frontend data layer (one react-query cache, honest loading/error/empty states, failed saves shown as failed) are done. Next: the SQLite migration.

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
| **Embedded Database** | TinyDB (single JSON file, in-memory hash and path lookups); SQLite planned |
| **Testing & Quality** | pytest + pytest-cov (311 tests, 92% coverage); oxlint + `tsc` for the frontend |
| **Type System** | mypy + TypeScript |

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
