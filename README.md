# Photo Meta Organizer

Metadata indexing and organization system built specifically for large-scale photo collections (20GB+). It automates the extraction of comprehensive EXIF data, performs content-based deduplication using SHA-256 hashing, and persists results in a structured, queryable JSON repository. Built with **Clean Architecture** principles — swap storage backends, retrievers, and extractors without touching business logic.

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)
![React 19](https://img.shields.io/badge/React-19.0-61dafb)
![Tests](https://img.shields.io/badge/Tests-195%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/Coverage-93%25-green)
![Throughput](https://img.shields.io/badge/Throughput-21%2C710%20imgs%2Fmin-blue)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ Features

- **Interactive C4 Architecture Topology** — Comprehensive, self-contained HTML architecture document adhering to Simon Brown's C4 model standard ([DOCS/c4-architecture.html](DOCS/c4-architecture.html)) featuring interactive SVG pan/zoom, fullscreen maximization, and narrative tables across System Context (L1), Containers (L2), Components (L3), and Ingestion Flow (L4).
- **Phase 4 React 19 Production Frontend Studio** — Complete, high-performance Web UI built with React 19, TypeScript, Vite, Zustand, and TanStack Virtualization.
  - **Light & Dark Themes** with tokenized CSS variables, sleek contrast palettes, and system theme synchronization.
  - **Lights Out Dimmer (`L`)** — Cinema-grade ambient mode dimming sidebars and controls to emphasize photo viewing.
  - **Global Command Palette (`Ctrl + K`)** — Instant fuzzy search across camera makes, tags, cities, and actions.
  - **Studio Grid View** — Virtualized 60fps gallery with live density zoom slider (160px–320px), flag badges, and star ratings.
  - **Deep EXIF Inspector** — Real-time canvas RGB/Luminance histogram, exposure triangle dials (Aperture, Shutter, ISO, Focal Length), technical telemetry, and raw JSON export.
  - **Interactive Filter Accordions** — Collapsible dropdowns for Camera Brands, Tags & Labels, and Curated Collections with active count badges and instant reset links.
  - **Floating Selection Dock** — Multi-select bar with cumulative size calculator, batch tagging, flag all, and ZIP export.
  - **Geospatial Map Explorer** — Interactive world map with GPS clusters and adjustable radius filter slider.
  - **Chronological Timeline Feed** — Date-grouped photo stream with year scrubber.
  - **Kanban Staging Board** — 3-stage visual workflow (`Inbox`, `Picks & Flagged`, `Export Ready`).
  - **Library Analytics Dashboard** — KPI metrics and interactive SVG charts with click-to-filter drilldowns.
  - **Fullscreen Lightbox** — Fullscreen image stage, bottom filmstrip thumbnails, and keyboard navigation (`Space`, `Esc`, `P`, `1-5`).
- **Standalone Windows Desktop Application (Electron Shell)** — High-performance desktop application bundling the entire React 19 UI and Python backend engine into an installable desktop experience:
  - **Native Windows Folder Selection** — Direct integration with Windows File Explorer directory picker dialogs to scan and index local photo albums without terminal commands.
  - **Auto-Managed Backend Sidecar** — Automatically starts the Python FastAPI service on an ephemeral port upon launch and gracefully terminates the process tree on window close.
  - **Zero-Rewrite Desktop Port** — Full 100% preservation of React 19 components, Zustand state, TanStack Virtual grid, and HTML5 Canvas EXIF histograms.
  - **Standalone Windows Executable Packaging** — Production-ready `electron-builder` and `PyInstaller` pipeline generating an NSIS installer (`.exe`) and portable standalone binary.
- **WebP Thumbnail Cache & Streaming Service** — SHA-256 hash-addressed thumbnail generator with EXIF transpose correction and `.cache/thumbnails/` persistent disk caching.
- **Folder Indexing REST API** — `POST /api/index` endpoint for programmatically triggering multi-threaded parallel extraction of arbitrary disk directories.
- **Curation & Batch Mutations REST API** — `PATCH /api/photos/{hash}` for star ratings/flags/tags and `POST /api/photos/batch` for atomic batch updates.
- **Curated Collections API** — `GET/POST /api/collections` for creating and organizing named photo sets.
- **CLI Search & Library Statistics** — `python main.py search` and `python main.py stats` formatted using `tabulate` for date, camera, location radius, tag, and size filtering.
- **In-Memory Database Indexing** — `TinyDBRepository` indexes `file_hash` ($O(1)$ lookup), `file_path`, `captured_at`, and `size_bytes` range queries for high-performance retrieval.
- **Multi-Threaded Parallel Indexing** — `ThreadPoolExecutor` worker pool + bounded queue + dedicated DB writer thread (21,000+ imgs/min).
- **Comprehensive EXIF Extraction** — Three-tier model (Universal → Common → Camera-Specific) supporting DSLR, mirrorless, mobile, action cam, and film scanner profiles.
- **Content-Based Deduplication** — SHA-256 file hashing as primary key.
- **Pluggable Backends** — Swap retrievers (local disk → S3) and repositories (TinyDB → MongoDB) via factory functions.
- **Extension Filtering** — Automatic filtering for image formats (JPEG, PNG, TIFF, RAW, HEIC, WebP, etc.).
- **GPS Coordinate Parsing** — Automatic DMS → decimal conversion with WGS84 datum.
- **Stateless Extraction** — Extractors have zero dependencies; safe for parallel processing.
- **Incremental Synchronization** — Change-aware sync (NEW/MODIFIED/DELETED) using hybrid fingerprinting to avoid redundant hashing.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+ & npm (for frontend development)
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/krishnamohan-seelam/photo_meta_organizer.git
cd photo_meta_organizer

# Create and activate virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

# Install Python backend dependencies
pip install -r requirements.txt
```

---

## 🖥️ Running the Application (Backend & Frontend)

### Option A: Development Mode (Two Terminals with Hot-Reload)

#### Terminal 1 — Backend REST API:
```bash
# 1. Activate virtual environment
.venv\Scripts\activate

# 2. Seed sample demo photos and metadata (optional)
python -m scripts.seed_demo_data

# 3. Start FastAPI backend on port 8000
python -m uvicorn photo_meta_organizer.api.app:create_app --factory --port 8000 --reload
```
*API Swagger Documentation is available at:* **`http://localhost:8000/docs`**

#### Terminal 2 — React 19 Frontend:
```bash
# 1. Enter frontend directory
cd frontend

# 2. Install node packages
npm install

# 3. Start Vite dev server on port 5173 (proxies /api to localhost:8000)
npm run dev
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
*Open your browser at:* **`http://localhost:8000`**

---

### Option C: Standalone Windows Desktop Application (Electron)

Launch the native Windows desktop application with auto-managed backend sidecar:

```bash
# 1. Build frontend and launch desktop application
npm run frontend:build
npm run desktop:start
```

To run in live development mode with hot-reloading:
```bash
npm run desktop:dev
```

To package into a Windows standalone installer (`.exe` / NSIS) & portable executable:
```bash
npm run desktop:package
```
*Output binaries are generated in:* `desktop/dist-package/`


---

### Index Your Photos

```bash
# Index all images in a directory (uses 4 workers by default)
python -m photo_meta_organizer.main index --path "C:\your\photos" --db metadata.json

# Index with specific number of worker threads (Parallel Processing)
python -m photo_meta_organizer.main index --path "C:\your\photos" --db metadata.json --workers 8

# With verbose logging
python -m photo_meta_organizer.main index --path /photos --db metadata.json --log-level DEBUG

# View help
python -m photo_meta_organizer.main --help
```

### Library Statistics & CLI Search

```bash
# View library statistics
python -m photo_meta_organizer.main stats --db metadata.json

# Search photos by camera make
python -m photo_meta_organizer.main search --camera-make Sony --db metadata.json

# Search photos by date range
python -m photo_meta_organizer.main search --date-from 2026-01-01 --date-to 2026-12-31 --db metadata.json

# Search photos near GPS coordinate within 25km radius
python -m photo_meta_organizer.main search --lat 35.6586 --lon 139.7454 --radius 25 --db metadata.json
```

### Sync Your Library (Incremental)

```bash
# Fast sync: index new photos and update modified ones
python -m photo_meta_organizer.main sync --path "C:\your\photos" --db metadata.json

# Sync with orphaned entry cleanup (removes records for deleted files)
python -m photo_meta_organizer.main sync --path /photos --db metadata.json --cleanup-deleted

# Preview changes without writing to DB
python -m photo_meta_organizer.main sync --path /photos --db metadata.json --dry-run
```

### Run Tests

```bash
# Run all 195 unit and integration tests
python -m pytest -v

# With coverage report
python -m pytest --cov=photo_meta_organizer --cov-report=term-missing
```

---

## 🏗️ Architecture

The project follows **Clean Architecture** with strict dependency inversion:
- **System Architecture & Data Flows:** **[DOCS/ARCHITECTURE.md](DOCS/ARCHITECTURE.md)**
- **Phase 3 Search & API Design:** **[design_docs/PHASE_3_DESIGN.md](design_docs/PHASE_3_DESIGN.md)**
- **Phase 4 Frontend UI Design:** **[design_docs/PHASE_4_UI_DESIGN.md](design_docs/PHASE_4_UI_DESIGN.md)**
- **Phase 4 Completion Report:** **[design_docs/PHASE_4_COMPLETION.md](design_docs/PHASE_4_COMPLETION.md)**

```
┌──────────────────────────────────────────────────────────────┐
│  Presentation Layer (FastAPI & React 19 Frontend)            │
│  ├── frontend/        React 19 + TypeScript + Vite + Zustand │
│  ├── api/routes/      REST Endpoints (/photos, /collections) │
│  └── main.py          CLI interface, composition root        │
└────────────────────────────┬─────────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────────┐
│  Application Layer                                           │
│  ├── interfaces/      Protocols (ImageRetriever,             │
│  │                    ImageMetadataExtractor,                 │
│  │                    ImageMetadataRepository)                │
│  ├── orchestrators.py ExtractorOrchestrator, SyncOrchestrator │
│  └── use_cases/       IndexPhotosUseCase, SearchPhotosUseCase,│
│                       SynchronizeMetadataUseCase              │
└────────────────────────────┬─────────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────────┐
│  Domain Layer (zero external dependencies)                   │
│  ├── models.py   ImageMetadata, SyncResult, FileState, etc.  │
│  └── services.py CameraClassifier, MetadataStateAnalyzer     │
└──────────────────────────────────────────────────────────────┘
```

---

## 🗺️ Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| **Phase 0** | ✅ Complete | Foundation: domain models, interfaces, test infrastructure |
| **Phase 1** | ✅ Complete | MVP: local disk indexing, TinyDB persistence, CLI |
| **Phase 1.5**| ✅ Complete | Incremental Sync: NEW/MODIFIED/DELETED detection |
| **Phase 2** | ✅ Complete | Parallel processing (ThreadPoolExecutor + Queue, 21k+ imgs/min) |
| **Phase 3** | ✅ Complete | Search & indexing + FastAPI REST API + CLI search & stats |
| **Phase 4** | ✅ Complete | Production React 19 Studio UI, WebP Thumbnail Cache & Curation API |
| **Phase 5** | 🔲 Planned | AI Tagging, Neural Image Embeddings & Semantic Search |
| **Phase 6** | 🔲 Planned | Cloud S3 / MinIO Blob Storage & Distributed MongoDB Scale-Out |

---

## 🛠️ Technology Stack

| Layer | Technology |
|-------|-----------|
| **Frontend Framework** | React 19 + TypeScript + Vite |
| **State & Virtualization** | Zustand + TanStack Virtualization |
| **Styling & Icons** | Tokenized CSS Variable System (Light/Dark) + Lucide Icons |
| **Backend Runtime** | Python 3.11+ |
| **REST API Server** | FastAPI + Uvicorn + Pydantic v2 |
| **Image Processing** | Pillow (PIL) + WebP Thumbnail Cache |
| **EXIF Extraction** | exifread (Three-Tier Universal/Common/Raw Model) |
| **Deduplication** | SHA-256 Content-Based File Fingerprinting |
| **Embedded Database** | TinyDB (In-Memory Hash & Range Indexed) |
| **Testing & Quality** | pytest + pytest-cov (195 tests, 90% coverage) |
| **Type System** | mypy (strict) + TypeScript |

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
