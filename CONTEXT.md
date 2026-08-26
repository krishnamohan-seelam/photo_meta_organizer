# Domain Vocabulary & Glossary (Photo Meta Organizer)

This document serves as the canonical domain glossary for the Photo Meta Organizer project across backend, data layer, CLI, and frontend UI.

---

## Core Domain Terms

### Media & Metadata
- **Image Metadata (`ImageMetadata`)**: The immutable domain model encapsulating file attributes (path, name, size, SHA-256 hash, MIME type), EXIF exposure metrics (aperture, shutter speed, ISO, focal length), camera details (make, model, serial number), timestamps, dimensions, GPS coordinates (latitude, longitude, altitude), and tags.
- **File Hash (`file_hash`)**: The SHA-256 cryptographic digest of an image's raw bytes, used as the primary immutable identifier across database lookup, REST API streaming, and thumbnail caching.
- **Exposure Triangle**: The trio of primary photographic exposure parameters: Aperture ($f$-number), Shutter Speed (exposure time in fractional seconds), and ISO Speed rating.
- **Luminance / RGB Histogram**: A visual frequency distribution representing tonal distribution across 256 intensity bins for Red, Green, Blue, and overall Luminosity channels.

### Organization & Curation
- **Pick / Flag (`flagged`)**: A boolean curation indicator marking a photo as accepted/curated (`🚩`) or rejected.
- **Star Rating (`rating`)**: A 1-to-5 integer scale representing photographic quality or curation priority.
- **Tag (`tags`)**: A user-defined or system-extracted categorical string label (e.g., `#landscape`, `#tokyo`, `#night`).
- **Collection (`Collection`)**: A named grouping or virtual album of photos (e.g., "Japan Trip 2026", "Client Deliverables") referencing photos by their immutable `file_hash`.

### Presentation & UX Concepts
- **Studio Inspector**: The primary 3-column desktop workspace featuring a collapsible filter hierarchy (left), responsive photo grid (center), and deep EXIF metadata inspector with exposure dials and raw JSON viewer (right).
- **DOM Virtualization**: A rendering optimization technique that dynamically renders only the subset of photo cards currently visible within the browser viewport (~30 elements), maintaining 60 FPS performance regardless of library size (50,000+ items).
- **Command Palette (`Ctrl + K`)**: A keyboard-first modal overlay allowing instantaneous fuzzy searching across camera models, tags, cities, and batch operations.
- **Lights Out Mode (`L`)**: A curation viewing state that dims surrounding UI chrome (sidebars, toolbar) to 12% opacity to allow evaluation of photos without visual distraction.
- **Floating Selection Dock**: An animated bottom utility bar that emerges whenever multiple photos are selected, displaying item count, cumulative storage size (MB/GB), and batch curation actions.
- **Kanban Collection Builder**: A drag-and-drop 3-stage board (`Inbox (Unsorted)`, `Picks / Highlights`, `Export Queue`) for staging and curating photo selections.
