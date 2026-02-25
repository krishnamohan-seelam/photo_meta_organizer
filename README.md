# Photo Meta Organizer

Metadata indexing and organization system built specifically for large-scale photo collections (20GB+). It automates the extraction of comprehensive EXIF data, performs content-based deduplication using SHA-256 hashing, and persists results in a structured, queryable JSON repository. Built with **Clean Architecture** principles — swap storage backends, retrievers, and extractors without touching business logic.

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)
![Tests](https://img.shields.io/badge/Tests-98%20passing-brightgreen)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ Features

- **Comprehensive EXIF Extraction** — Three-tier model (Universal → Common → Camera-Specific) supporting DSLR, mirrorless, mobile, action cam, and film scanner profiles
- **Content-Based Deduplication** — SHA-256 file hashing as primary key
- **Pluggable Backends** — Swap retrievers (local disk → S3) and repositories (TinyDB → MongoDB) via factory functions
- **Extension Filtering** — Automatic filtering for image formats (JPEG, PNG, TIFF, RAW, HEIC, WebP, etc.)
- **GPS Coordinate Parsing** — Automatic DMS → decimal conversion with WGS84 datum
- **Stateless Extraction** — Extractors have zero dependencies; safe for parallel processing

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/photo_meta_organizer.git
cd photo_meta_organizer

# Create and activate virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Index Your Photos

```bash
# Index all images in a directory
python -m photo_meta_organizer.main index --path "C:\your\photos" --db metadata.json

# With verbose logging
python -m photo_meta_organizer.main index --path /photos --db metadata.json --log-level DEBUG

# View help
python -m photo_meta_organizer.main --help
```

### Run Tests

```bash
# Run all tests
python -m pytest photo_meta_organizer/tests/ -v

# With coverage
python -m pytest photo_meta_organizer/tests/ --cov=photo_meta_organizer --cov-report=term-missing
```

---

## 🏗️ Architecture

The project follows **Clean Architecture** with strict dependency inversion. For a detailed breakdown of wiring examples and component diagrams, see **[DOCS/ARCHITECTURE.md](DOCS/ARCHITECTURE.md)**.

```
┌──────────────────────────────────────────────────────────────┐
│  Presentation Layer (main.py)                                │
│  CLI interface, logging, factory functions (composition root)│
└────────────────────────────┬─────────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────────┐
│  Application Layer                                           │
│  ├── interfaces/      Protocols (ImageRetriever,             │
│  │                    ImageMetadataExtractor,                 │
│  │                    ImageMetadataRepository)                │
│  ├── orchestrators.py ExtractorOrchestrator (batch extract)  │
│  └── use_cases/       IndexPhotosUseCase (full pipeline)     │
└────────────────────────────┬─────────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────────┐
│  Domain Layer (zero external dependencies)                   │
│  ├── models.py   ImageMetadata, ImageExifData,               │
│  │               GpsCoordinates, CameraProfile, etc.         │
│  └── services.py CameraClassifier (stateless)                │
└──────────────────────────────────────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────────┐
│  Infrastructure Layer (adapters)                             │
│  ├── retriever/       LocalDiskRetriever,                    │
│  │                    ExtensionFilteredRetriever              │
│  ├── extractors/      DiskMetaDataExtractor (exifread+PIL)   │
│  └── repositories/    TinyDBRepository (JSON persistence)    │
└──────────────────────────────────────────────────────────────┘
```

### Data Flow

```
Discovery → Extraction → Persistence
LocalDiskRetriever   DiskMetaDataExtractor   TinyDBRepository
   │                       │                       │
   ├─ list_files()         │                       │
   ├─ get_file_stream()  ──┤                       │
   │                       ├─ extract(handle, stream)
   │                       │  → ImageMetadata    ──┤
   │                       │                       ├─ save(metadata)
   │                       │                       └─ → metadata.json
```

### Backend Swapping

The factory functions in `main.py` make it trivial to swap backends:

```python
# main.py
def build_retriever(args):
    # Phase 1: Local disk (current)
    return ExtensionFilteredRetriever(LocalDiskRetriever(args.path), IMAGE_EXTENSIONS)
    # Phase 4: return S3Retriever(bucket=args.bucket)

def build_repository(args):
    # Phase 1: TinyDB (current)
    return TinyDBRepository(db_path=args.db)
    # Phase 4: return MongoDBRepository(connection_url=args.db)
```

---

## 📁 Project Structure

```
photo_meta_organizer/
├── domain/
│   ├── models.py                   # Core entities (ImageMetadata, ImageExifData, GpsCoordinates, etc.)
│   └── services.py                 # CameraClassifier domain service
├── application/
│   ├── interfaces/                 # Protocol definitions (ports)
│   │   ├── image_extractor.py      # ImageMetadataExtractor protocol
│   │   ├── image_retriever.py      # ImageRetriever + RemoteFileHandle
│   │   └── image_repository.py     # ImageMetadataRepository protocol
│   ├── orchestrators.py            # ExtractorOrchestrator (batch coordination)
│   └── use_cases/
│       └── index_photos_use_case.py # Full pipeline: retrieve → extract → persist
├── infrastructure/
│   ├── extractors/
│   │   └── disk_metadata_extractor.py  # exifread + Pillow + SHA-256
│   ├── retriever/
│   │   ├── local_disk_retriever.py     # Recursive local filesystem discovery
│   │   └── filtered_retriever.py       # Extension-based filtering decorator
│   └── repositories/
│       └── tinydb_repository.py        # TinyDB JSON persistence with upsert
├── tests/
│   ├── conftest.py                 # Fixtures + mock implementations
│   └── unit/
│       ├── domain/                 # test_models.py, test_services.py
│       ├── application/            # test_interfaces.py, test_use_cases.py
│       └── infrastructure/         # test_extractors.py
├── main.py                         # CLI entry point + composition root
├── pyproject.toml
├── requirements.txt
└── pytest.ini
```

---

## 📊 Domain Model

### ImageMetadata (Primary Entity)

| Field | Type | Description |
|-------|------|-------------|
| `file_hash` | `str` | SHA-256 content hash (primary key) |
| `file_info` | `ImageFileInfo` | Name, path, size, MIME type |
| `dimensions` | `ImageDimensions` | Width, height, aspect ratio |
| `exif` | `ImageExifData` | Three-tier EXIF model |
| `labels` | `list[str]` | User/AI tags |
| `added_at` | `datetime` | Indexing timestamp |

### ImageExifData (Three-Tier EXIF Model)

| Tier | Fields | Coverage |
|------|--------|----------|
| **Tier 1 (Universal)** | camera_make, camera_model, iso, f_stop, exposure_time, focal_length, captured_at | >95% of images |
| **Tier 2 (Common)** | camera_profile, location (GPS), flash_fired, focal_length_35mm, white_balance, exposure_program, metering_mode, orientation | 50-95% |
| **Tier 3 (Camera-specific)** | raw_tags dict | Everything else |

### CameraProfile Enum

`DSLR` · `MIRRORLESS` · `MOBILE` · `ACTION_CAM` · `FILM_SCANNER` · `UNKNOWN`

Automatically inferred from camera make/model via `CameraClassifier` domain service.

---

## 💡 Key Design Decisions

- **Stateless Extractors** — Extractors have zero dependencies and no internal state; they receive streams and return metadata, making them perfectly safe for parallel execution.
- **Context Manager Streams** — Retrievers provide file streams via context managers, ensuring resources like file handles are always properly closed.
- **Dependency Injection** — All major components are injected via factory functions in `main.py`, allowing you to swap any part of the system (Storage, Extraction, Retrieval) with a single line change.
- **Three-Tier EXIF Model** — Data is organized into Universal (ISO, Aperture), Common (GPS, White Balance), and Camera-Specific (Raw Tags) tiers to balance structure with flexibility.
- **Domain-Driven Inference** — Camera profiles are inferred using internal domain services, keeping infrastructure logic out of the core models.

---

## 🗺️ Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| **Phase 0** | ✅ Complete | Foundation: domain models, interfaces, test infrastructure |
| **Phase 1** | ✅ Complete | MVP: local disk indexing, TinyDB persistence, CLI |
| **Phase 2** | 🔲 Planned | Parallel processing (ThreadPoolExecutor + Queue) |
| **Phase 3** | 🔲 Planned | Search/filtering + FastAPI REST API |
| **Phase 4** | 🔲 Planned | MongoDB + S3 backends |
| **Phase 5** | 🔲 Planned | AI tagging + reverse geocoding |
| **Phase 6** | 🔲 Planned | React web gallery UI |

---

## 🛠️ Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| EXIF Parsing | exifread |
| Image Processing | Pillow (PIL) |
| Hashing | hashlib (SHA-256) |
| Persistence | TinyDB (Phase 1) |
| Testing | pytest + pytest-cov |
| Type Checking | mypy (strict) |

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
