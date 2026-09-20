# Architecture and Wiring

**Status:** ✅ Phase 4 (Web-Based Studio Gallery UI & Thumbnail Streaming) Complete & Verified  
**Last Updated:** September 5, 2026  
**Tests:** 195 passing (93% coverage)  
**Throughput:** 21,710 imgs/min (8 workers)  
**Interactive C4 Model:** [c4-architecture.html](c4-architecture.html)

---

## Overview

This project uses **Clean Architecture** with a stateless extractor design.
All components communicate through Protocol-based interfaces (ports), with
concrete implementations (adapters) injected at the composition root (`main.py`).

An interactive, multi-level architectural topology document adhering to Simon Brown's C4 model standard is available at [DOCS/c4-architecture.html](c4-architecture.html), featuring zoom/pan diagrams and component tables across:
- **Level 1: System Context** (Photographers, Dataset Managers, Filesystem & S3 Storage, Browser & Desktop Clients)
- **Level 2: Container Topology** (Electron Desktop Host, React 19 SPA, FastAPI REST API, CLI Runner, WebP Thumbnail Cache, TinyDB Document DB)
- **Level 3: Component Architecture** (Controllers, Use Cases, Domain Models/Services, Infrastructure Adapters)
- **Level 4: Code & Parallel Ingestion Execution Flow** (Worker ThreadPool, Bounded Queue, Dedicated Single-Writer Thread)

### Core Abstractions

| Protocol | Responsibility | Implementation |
|----------|---------------|----------------|
| `ImageRetriever` | File discovery + stream access | `LocalDiskRetriever`, `ExtensionFilteredRetriever`, `S3Retriever` |
| `ImageMetadataExtractor` | Stateless metadata parsing | `DiskMetaDataExtractor` |
| `ImageMetadataRepository` | Persistence (CRUD, batch, collections) | `TinyDBRepository` |

### Key Design Decisions

- **Extractor is stateless**: `extract(file_handle, stream) → ImageMetadata`
- **Retriever owns I/O**: `get_file_stream()` returns a context manager (`ContextManager[BinaryIO]`)
- **Repository uses upsert**: `save()` updates if `file_hash` exists, inserts otherwise
- **Three-tier EXIF model**: Universal → Common → Camera-Specific (raw_tags)
- **Camera profile inference**: `CameraClassifier` domain service (no infra dependencies)
- **Multi-criteria Search**: `SearchPhotosUseCase` with `SearchPhotosQuery` DTO & `PaginatedResult` iterator
- **TinyDB In-Memory Indexing & Self-Healing Storage**: `TinyDBRepository` maintains $O(1)$ hash/path lookups (`_hash_index`, `_path_index`) and sorted range indexes (`_captured_at_index`, `_size_index`) for accelerated queries, with automated self-healing JSON repair for cross-process recovery
- **REST API**: `FastAPI` factory `create_app(db_path)` with endpoints (`GET/DELETE /api/photos`, `GET /api/photos/{hash}`, `POST /api/search`, `PATCH /api/photos/{hash}`, `POST /api/photos/batch`, `GET/POST /api/collections`, `POST /api/index`, `GET /api/photos/{hash}/thumbnail`, `GET /api/photos/{hash}/raw`) backed by Pydantic schemas
- **Thumbnail Cache & Streaming**: `ThumbnailService` generates on-the-fly WebP thumbnails with Pillow LANCZOS resampling, EXIF orientation transpose, and persistent disk caching in `.cache/thumbnails/`
- **React 19 Studio Frontend**: Headless, virtualized gallery UI colocated in `frontend/` powered by TanStack Virtual, Tailwind CSS v4, Zustand, and OffscreenCanvas histogram generation
- **Standalone Windows Desktop Application**: Electron-based desktop shell (`desktop/`) orchestrating the FastAPI backend as a managed sidecar process with automatic port discovery, conflict resolution (attaching to existing instances or dynamically finding open ports), native Windows folder picker dialogs, and OS shell actions via context-isolated IPC channels
- **Desktop Packaging**: Automated multi-stage packaging using `PyInstaller` (freezing Python runtime into `photo_meta_organizer_backend.exe`) and `electron-builder` producing standalone Windows NSIS installers and portable executables

---

## Wiring Examples

### 1. Direct retriever + extractor (manual loop)

```python
from photo_meta_organizer.infrastructure.retriever.local_disk_retriever import LocalDiskRetriever
from photo_meta_organizer.infrastructure.extractors.disk_metadata_extractor import DiskMetaDataExtractor

retriever = LocalDiskRetriever(base_path="/photos")
extractor = DiskMetaDataExtractor()

for handle in retriever.list_files():
    with retriever.get_file_stream(handle) as stream:
        metadata = extractor.extract(handle, stream)
        print(f"{metadata.file_info.name}: {metadata.dimensions.width}x{metadata.dimensions.height}")
```

### 2. Using `ExtractorOrchestrator` (batch extraction)

```python
from photo_meta_organizer.application.orchestrators import ExtractorOrchestrator

orchestrator = ExtractorOrchestrator(extractor, retriever)
all_metadata = orchestrator.extract_all()  # List[ImageMetadata]
```

### 3. Full pipeline via `IndexPhotosUseCase` (recommended)

```python
from photo_meta_organizer.application.use_cases import IndexPhotosUseCase
from photo_meta_organizer.infrastructure.repositories.tinydb_repository import TinyDBRepository

repository = TinyDBRepository(db_path="metadata.json")

use_case = IndexPhotosUseCase(
    retriever=retriever,
    extractor=extractor,
    repository=repository,
)
results = use_case.execute()  # Extracts and persists all metadata
print(f"Indexed {len(results)} photos")
```

### 4. Searching metadata via `SearchPhotosUseCase`

```python
from photo_meta_organizer.application.use_cases import SearchPhotosUseCase, SearchPhotosQuery

search_use_case = SearchPhotosUseCase(repository=repository)
query = SearchPhotosQuery(
    camera_make="Sony",
    location_lat=37.7749,
    location_lon=-122.4194,
    radius_km=20.0,
    sort_by="captured_at",
    page=1,
    page_size=20
)
result = search_use_case.execute(query)
for photo in result:  # Implements Iterator protocol
    print(photo.file_info.name, photo.exif.captured_at)
```

### 4. CLI (end-user)

```bash
python -m photo_meta_organizer.main index --path /photos --db metadata.json
```

---

## Component Diagram

```
main.py (Composition Root)
  │
  ├── build_retriever() → ExtensionFilteredRetriever(LocalDiskRetriever)
  ├── build_extractor() → DiskMetaDataExtractor
  └── build_repository() → TinyDBRepository
         │
         ↓
IndexPhotosUseCase / ParallelIndexPhotosUseCase
  │
  ├── ThreadPoolExecutor (Parallel extraction)
  │     ├── ExtractorOrchestrator  (retrieve → extract)
  │     │     ├── ImageRetriever.list_files()
  │     │     ├── ImageRetriever.get_file_stream()  [context manager]
  │     │     └── ImageMetadataExtractor.extract()  [stateless]
  │
  └── Queue + Dedicated DB Writer Thread
        └── ImageMetadataRepository.save()  (persist each result)
```

---

## Layer Responsibilities

### Domain Layer (`domain/`)
- **Zero external dependencies** — pure Python only
- `models.py`: `ImageMetadata`, `ImageFileInfo`, `ImageDimensions`, `ImageExifData`, `GpsCoordinates`, `CameraProfile`
- `services.py`: `CameraClassifier` — infers camera profile from make/model

### Application Layer (`application/`)
- **Depends only on Domain** — no infrastructure imports
- `interfaces/`: Protocol definitions (ports) for retriever, extractor, repository
- `orchestrators.py`: `ExtractorOrchestrator` — coordinates retriever + extractor
- `use_cases/`: `IndexPhotosUseCase`, `ParallelIndexPhotosUseCase` — full retrieve→extract→persist pipelines

### Infrastructure Layer (`infrastructure/`)
- **Implements protocols** — the only layer that touches external libraries
- `retriever/`: `LocalDiskRetriever` (pathlib), `ExtensionFilteredRetriever` (decorator)
- `extractors/`: `DiskMetaDataExtractor` (exifread + Pillow + hashlib)
- `repositories/`: `TinyDBRepository` (TinyDB JSON file)

### Presentation Layer (`main.py`)
- **Composition root** — wires infrastructure to application via factory functions
- CLI argument parsing (argparse)
- Logging configuration

---

## Notes

- The extractor remains stateless and testable: unit tests pass a `BytesIO`
  stream directly to `extract()` without needing retriever plumbing.
- The orchestrator encapsulates I/O concerns, making it easier to add
  parallelism, error handling, and retry policies later (Phase 2).
- `ExtensionFilteredRetriever` is a **decorator** — wraps any `ImageRetriever`
  to filter by file extension without modifying the underlying retriever.
- `TinyDBRepository` handles full serialization/deserialization of frozen
  dataclasses, including `CameraProfile` enum, `GpsCoordinates`, and datetimes.
