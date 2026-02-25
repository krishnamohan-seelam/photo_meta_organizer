# Architecture and Wiring

**Status:** ✅ Phase 1 Complete  
**Last Updated:** February 25, 2026  
**Tests:** 98 passing

---

## Overview

This project uses **Clean Architecture** with a stateless extractor design.
All components communicate through Protocol-based interfaces (ports), with
concrete implementations (adapters) injected at the composition root (`main.py`).

### Core Abstractions

| Protocol | Responsibility | Implementation |
|----------|---------------|----------------|
| `ImageRetriever` | File discovery + stream access | `LocalDiskRetriever`, `ExtensionFilteredRetriever` |
| `ImageMetadataExtractor` | Stateless metadata parsing | `DiskMetaDataExtractor` |
| `ImageMetadataRepository` | Persistence (CRUD) | `TinyDBRepository` |

### Key Design Decisions

- **Extractor is stateless**: `extract(file_handle, stream) → ImageMetadata`
- **Retriever owns I/O**: `get_file_stream()` returns a context manager (`ContextManager[BinaryIO]`)
- **Repository uses upsert**: `save()` updates if `file_hash` exists, inserts otherwise
- **Three-tier EXIF model**: Universal → Common → Camera-Specific (raw_tags)
- **Camera profile inference**: `CameraClassifier` domain service (no infra dependencies)

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
IndexPhotosUseCase
  │
  ├── ExtractorOrchestrator  (retrieve → extract)
  │     ├── ImageRetriever.list_files()
  │     ├── ImageRetriever.get_file_stream()  [context manager]
  │     └── ImageMetadataExtractor.extract()  [stateless]
  │
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
- `use_cases/`: `IndexPhotosUseCase` — full retrieve→extract→persist pipeline

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
