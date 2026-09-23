"""TinyDB-based implementation of ImageMetadataRepository.

Persists ImageMetadata domain entities to a JSON file using TinyDB.
Handles serialization of frozen dataclasses (including enums, datetimes,
and nested value objects) to and from TinyDB-compatible dictionaries.

TinyDB stores data as plain JSON objects in a single file, making it
ideal for Phase 1 (single-user, moderate dataset sizes). For Phase 4+
(multi-user, large datasets), swap to MongoDBRepository or
ElasticsearchRepository via the same protocol.

Example:
    >>> repo = TinyDBRepository(db_path="metadata.json")
    >>> repo.save(image_metadata)
    >>> found = repo.get_by_filehash("e3b0c44298fc...")
"""

import json
import logging
import math
import os
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from tinydb import Query, TinyDB

from photo_meta_organizer.application.interfaces.search_types import (
    FacetCount,
    Facets,
    GpsBounds,
    Page,
    SearchQuery,
)
from photo_meta_organizer.domain.curation import (
    AddTag,
    CurationCommand,
    RemoveTag,
    SetFlag,
    SetLabels,
    SetRating,
    merge_labels,
    validate_rating,
    validate_tag,
)
from photo_meta_organizer.domain.datetimes import to_naive
from photo_meta_organizer.domain.geo import haversine_distance_km
from photo_meta_organizer.domain.models import (
    CameraProfile,
    GpsCoordinates,
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)

logger = logging.getLogger(__name__)


class TinyDBRepository:
    """TinyDB-backed repository for ImageMetadata persistence.

    Implements the ImageMetadataRepository protocol with JSON file storage.
    Each ImageMetadata is stored as a flat document with nested dicts for
    sub-objects (file_info, dimensions, exif).

    Upsert semantics: save() updates the record if file_hash exists,
    inserts otherwise.

    Attributes:
        _db: TinyDB database instance.
        _table: Default TinyDB table for metadata storage.
    """

    @staticmethod
    def _repair_corrupted_db(db_path: str) -> None:
        """Self-heal a JSON file that has extra trailing data or corrupted duplicate blocks."""
        if not os.path.exists(db_path):
            return
        try:
            with open(db_path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
            decoder = json.JSONDecoder()
            obj, _ = decoder.raw_decode(content)
            with open(db_path, "w", encoding="utf-8") as f:
                json.dump(obj, f, indent=2)
            logger.info("Successfully repaired corrupted database at %s", db_path)
        except Exception as repair_err:
            logger.error("Failed to auto-repair %s: %s", db_path, repair_err)

    def __init__(self, db_path: str) -> None:
        """Initialize with path to the JSON database file.

        Args:
            db_path: File path for the TinyDB JSON file.
                     Created automatically if it doesn't exist.
        """
        self._db_path = db_path
        try:
            self._db = TinyDB(db_path, indent=2)
            self._table = self._db.table("metadata")
        except json.decoder.JSONDecodeError as e:
            logger.warning("JSONDecodeError in %s: %s. Performing auto-repair...", db_path, e)
            self._repair_corrupted_db(db_path)
            self._db = TinyDB(db_path, indent=2)
            self._table = self._db.table("metadata")

        # Index data structures
        self._hash_index: dict[str, dict[str, Any]] = {}
        self._path_index: dict[str, dict[str, Any]] = {}
        self._captured_at_index: list[tuple[datetime, dict[str, Any]]] = []
        self._size_index: list[tuple[int, dict[str, Any]]] = []

        self.rebuild_indexes()
        logger.info("TinyDB repository initialized at: %s with indexes built", db_path)

    def rebuild_indexes(self) -> None:
        """Rebuild all in-memory indexes from the TinyDB table records."""
        self._hash_index.clear()
        self._path_index.clear()
        self._captured_at_index.clear()
        self._size_index.clear()

        for doc in self._table.all():
            file_hash = doc.get("file_hash")
            if file_hash:
                self._hash_index[file_hash] = doc

            file_info = doc.get("file_info", {})
            file_path = file_info.get("path")
            if file_path:
                self._path_index[file_path] = doc

            size_bytes = file_info.get("size_bytes")
            if size_bytes is not None:
                self._size_index.append((size_bytes, doc))

            exif_doc = doc.get("exif", {})
            captured_at_str = exif_doc.get("captured_at")
            if captured_at_str:
                try:
                    captured_at_dt = to_naive(datetime.fromisoformat(captured_at_str))
                    self._captured_at_index.append((captured_at_dt, doc))
                except (ValueError, TypeError):
                    pass

        self._captured_at_index.sort(key=lambda x: x[0])
        self._size_index.sort(key=lambda x: x[0])

    def close(self) -> None:
        """Close the database connection."""
        self._db.close()

    @property
    def db(self) -> TinyDB:
        """The underlying TinyDB instance, shared with :class:`TinyDBCollectionRepository`."""
        return self._db

    # =========================================================================
    # Protocol Methods
    # =========================================================================

    def save_many(self, items: Sequence[ImageMetadata]) -> None:
        """Upsert many records in one batch (one index rebuild, not one per record)."""
        for metadata in items:
            self._upsert(metadata)
        self.rebuild_indexes()

    def save(self, metadata: ImageMetadata) -> None:
        """Persist image metadata with upsert semantics.

        If a record with the same file_hash exists, it is updated.
        Otherwise, a new record is inserted.

        Args:
            metadata: The ImageMetadata entity to persist.
        """
        self._upsert(metadata)
        self.rebuild_indexes()

    def _upsert(self, metadata: ImageMetadata) -> None:
        """Insert or update by file hash without touching the indexes."""
        doc = self._serialize(metadata)
        q = Query()
        if self._table.search(q.file_hash == metadata.file_hash):
            self._table.update(doc, q.file_hash == metadata.file_hash)
            logger.debug("Updated metadata for hash: %s", metadata.file_hash[:12])
        else:
            self._table.insert(doc)
            logger.debug("Inserted metadata for hash: %s", metadata.file_hash[:12])

    def replace(self, old_hash: str, metadata: ImageMetadata) -> None:
        """Swap the record stored under ``old_hash`` for ``metadata``.

        Content is the identity, so an edited file gets a new hash; a plain ``save``
        would leave the old record behind as a duplicate of the same path. If
        ``metadata.file_hash`` already exists (the edit made it identical to another
        photo) the two collapse into one record. One index rebuild.
        """
        q = Query()
        if old_hash != metadata.file_hash:
            self._table.remove(q.file_hash == old_hash)
        self._upsert(metadata)
        self.rebuild_indexes()

    def refresh_fingerprints(self, updates: Sequence[tuple[str, int, datetime]]) -> int:
        """Record ``(file_hash, size_bytes, modified_time)`` on existing records.

        Bookkeeping for sync (backfilling legacy records, catching up after a
        ``touch``): nothing else on the record changes. Applied as a single write,
        not one per record, because a JSON-backed store rewrites the whole file.

        Returns:
            Number of records updated; unknown hashes are skipped.
        """
        wanted = {h: (size, mtime) for h, size, mtime in updates}
        if not wanted:
            return 0
        touched = 0

        def apply(doc: dict[str, Any]) -> None:
            nonlocal touched
            size, mtime = wanted[doc["file_hash"]]
            doc["file_info"]["size_bytes"] = size
            doc["file_info"]["modified_time"] = mtime.isoformat()
            touched += 1

        q = Query()
        self._table.update(apply, q.file_hash.test(lambda h: h in wanted))
        self.rebuild_indexes()
        return touched

    def get_by_filehash(self, file_hash: str) -> ImageMetadata | None:
        """Retrieve metadata by SHA-256 file hash using fast O(1) index.

        Args:
            file_hash: The content hash to search for.

        Returns:
            ImageMetadata if found, None otherwise.
        """
        doc = self._hash_index.get(file_hash)
        if doc is not None:
            return self._deserialize(doc)

        q = Query()
        results = self._table.search(q.file_hash == file_hash)
        if not results:
            return None
        return self._deserialize(results[0])

    def get_by_path(self, file_path: str) -> ImageMetadata | None:
        """Retrieve metadata by original file path using fast O(1) index.

        Args:
            file_path: The file path to search for.

        Returns:
            ImageMetadata if found, None otherwise.
        """
        doc = self._path_index.get(file_path)
        if doc is not None:
            return self._deserialize(doc)

        q = Query()
        results = self._table.search(q.file_info.path == file_path)
        if not results:
            return None
        return self._deserialize(results[0])

    def list_all(self) -> list[ImageMetadata]:
        """Retrieve all stored metadata records.

        Returns:
            List of all ImageMetadata entities in storage.
        """
        try:
            return [self._deserialize(doc) for doc in self._table.all()]
        except json.decoder.JSONDecodeError as e:
            logger.warning("JSON corruption detected during list_all: %s. Auto-healing...", e)
            self._repair_corrupted_db(self._db_path)
            self.rebuild_indexes()
            return [self._deserialize(doc) for doc in self._table.all()]

    def delete(self, file_hash: str) -> bool:
        """Delete metadata by file hash and update indexes.

        Args:
            file_hash: The content hash of the record to delete.

        Returns:
            True if a record was deleted, False if not found.
        """
        q = Query()
        removed = self._table.remove(q.file_hash == file_hash)
        if removed:
            self.rebuild_indexes()
            return True
        return False

    def count(self) -> int:
        """Return the number of stored records."""
        return len(self._table)

    def delete_by_path(self, file_path: str) -> bool:
        """Delete metadata record by file path and update indexes.

        Args:
            file_path: The original file path stored in file_info.path.

        Returns:
            True if a record was found and deleted, False otherwise.
        """
        q = Query()
        removed = self._table.remove(q.file_info.path == file_path)
        if removed:
            self.rebuild_indexes()
            logger.debug("Deleted metadata for path: %s", file_path)
            return True
        logger.debug("No record found for path: %s", file_path)
        return False

    def find_by_paths(self, paths: list[str]) -> list[ImageMetadata]:
        """Find multiple metadata records by file paths using path index.

        Args:
            paths: List of file paths to look up.

        Returns:
            List of ImageMetadata for matching records.
            Paths with no match are silently skipped.
        """
        if not paths:
            return []

        results = []
        for p in paths:
            doc = self._path_index.get(p)
            if doc is not None:
                results.append(self._deserialize(doc))
        return results

    def find_by_date_range(
        self,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
    ) -> list[ImageMetadata]:
        """Find metadata records captured within a date range using captured_at index.

        Args:
            date_start: Minimum captured_at datetime (inclusive).
            date_end: Maximum captured_at datetime (inclusive).

        Returns:
            List of ImageMetadata records within the date range.
        """
        date_start, date_end = to_naive(date_start), to_naive(date_end)
        results = []
        for captured_at_dt, doc in self._captured_at_index:
            if date_start and captured_at_dt < date_start:
                continue
            if date_end and captured_at_dt > date_end:
                continue
            results.append(self._deserialize(doc))
        return results

    def find_by_size_range(
        self,
        min_bytes: int | None = None,
        max_bytes: int | None = None,
    ) -> list[ImageMetadata]:
        """Find metadata records with file size in bytes within a specified range using size index.

        Args:
            min_bytes: Minimum file size in bytes (inclusive).
            max_bytes: Maximum file size in bytes (inclusive).

        Returns:
            List of ImageMetadata records within the size range.
        """
        results = []
        for size_bytes, doc in self._size_index:
            if min_bytes is not None and size_bytes < min_bytes:
                continue
            if max_bytes is not None and size_bytes > max_bytes:
                continue
            results.append(self._deserialize(doc))
        return results

    # =========================================================================
    # Search, paging and facets (PMO-07/09)
    # =========================================================================

    def query(self, query: SearchQuery) -> Page[ImageMetadata]:
        """Filter, sort and page records. TinyDB has no query planner, so this
        still deserializes every record; the SQLite implementation is where
        paging actually avoids that cost.
        """
        all_records = self.list_all()
        filtered = [record for record in all_records if self._matches_query(record, query)]
        sorted_records = self._sort_records(filtered, query.sort_by, query.sort_order)

        total_count = len(sorted_records)
        page_size = max(1, query.page_size)
        total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1
        page = max(1, min(query.page, total_pages))

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        return Page(
            items=sorted_records[start_idx:end_idx],
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    @staticmethod
    def _matches_query(record: ImageMetadata, query: SearchQuery) -> bool:
        exif = record.exif
        info = record.file_info

        if query.date_start or query.date_end:
            captured_at = to_naive(exif.captured_at) if exif else None
            if not captured_at:
                return False
            if query.date_start and captured_at < query.date_start:
                return False
            if query.date_end and captured_at > query.date_end:
                return False

        if query.camera_make:
            make = exif.camera_make if exif else None
            if not make or query.camera_make.lower() not in make.lower():
                return False
        if query.camera_model:
            model = exif.camera_model if exif else None
            if not model or query.camera_model.lower() not in model.lower():
                return False

        if (
            query.location_lat is not None
            and query.location_lon is not None
            and query.radius_km is not None
        ):
            gps = exif.location if exif else None
            if not gps or gps.latitude is None or gps.longitude is None:
                return False
            dist = haversine_distance_km(
                query.location_lat, query.location_lon, gps.latitude, gps.longitude
            )
            if dist > query.radius_km:
                return False

        if query.tags:
            rec_tags = set(record.labels or [])
            if not set(query.tags).issubset(rec_tags):
                return False

        if query.rating is not None and record.rating != query.rating:
            return False

        if query.flagged is not None and record.flagged != query.flagged:
            return False

        if query.search_term:
            haystack = " ".join(
                filter(
                    None,
                    [
                        info.name,
                        info.path,
                        exif.camera_make if exif else None,
                        exif.camera_model if exif else None,
                        *record.labels,
                    ],
                )
            ).lower()
            if query.search_term.lower() not in haystack:
                return False

        return True

    @staticmethod
    def _sort_records(
        records: list[ImageMetadata], sort_by: str, sort_order: str
    ) -> list[ImageMetadata]:
        reverse = sort_order.lower() == "desc"

        def get_sort_key(record: ImageMetadata):
            if sort_by == "size_bytes":
                return record.file_info.size_bytes or 0
            elif sort_by == "camera_model":
                return (record.exif.camera_model if record.exif else "") or ""
            elif sort_by == "file_name":
                return record.file_info.name or ""
            else:  # captured_at
                dt = to_naive(record.exif.captured_at) if record.exif else None
                return dt if dt is not None else datetime.min

        return sorted(records, key=get_sort_key, reverse=reverse)

    def facets(self) -> Facets:
        """Aggregate counts for filter UIs, computed over every record."""
        cameras: dict[str, int] = {}
        tags: dict[str, int] = {}
        years: dict[str, int] = {}
        lats: list[float] = []
        lons: list[float] = []

        for record in self.list_all():
            if record.exif and record.exif.camera_make:
                cameras[record.exif.camera_make] = cameras.get(record.exif.camera_make, 0) + 1
            for tag in record.labels:
                tags[tag] = tags.get(tag, 0) + 1
            captured_at = record.exif.captured_at if record.exif else None
            if captured_at:
                year = str(captured_at.year)
                years[year] = years.get(year, 0) + 1
            if record.exif and record.exif.location:
                lats.append(record.exif.location.latitude)
                lons.append(record.exif.location.longitude)

        gps_bounds = None
        if lats and lons:
            gps_bounds = GpsBounds(
                min_lat=min(lats), max_lat=max(lats), min_lon=min(lons), max_lon=max(lons)
            )

        return Facets(
            cameras=[FacetCount(name=k, count=v) for k, v in sorted(cameras.items())],
            tags=[FacetCount(name=k, count=v) for k, v in sorted(tags.items())],
            years=[FacetCount(name=k, count=v) for k, v in sorted(years.items())],
            gps_bounds=gps_bounds,
        )

    # =========================================================================
    # Typed curation commands (PMO-07)
    # =========================================================================

    def apply(self, file_hash: str, command: CurationCommand) -> ImageMetadata | None:
        """Apply one typed curation command to a single record."""
        doc = self._hash_index.get(file_hash)
        if not doc:
            return None
        self._apply_command_to_doc(doc, command)
        q = Query()
        self._table.update(doc, q.file_hash == file_hash)
        self.rebuild_indexes()
        return self._deserialize(doc)

    def apply_batch(self, file_hashes: Sequence[str], command: CurationCommand) -> int:
        """Apply one typed curation command to many records. Unknown hashes are skipped."""
        count = 0
        q = Query()
        for f_hash in file_hashes:
            doc = self._hash_index.get(f_hash)
            if not doc:
                continue
            self._apply_command_to_doc(doc, command)
            self._table.update(doc, q.file_hash == f_hash)
            count += 1
        self.rebuild_indexes()
        return count

    @staticmethod
    def _apply_command_to_doc(doc: dict[str, Any], command: CurationCommand) -> None:
        """Mutate ``doc`` in place per ``command``. Commands validate at construction,
        so nothing here can raise on a bad value.
        """
        if isinstance(command, SetRating):
            doc["rating"] = command.value
        elif isinstance(command, SetFlag):
            doc["flagged"] = command.value
        elif isinstance(command, AddTag):
            doc["labels"] = merge_labels(doc.get("labels", []), [command.value])
        elif isinstance(command, RemoveTag):
            doc["labels"] = [t for t in doc.get("labels", []) if t != command.value]
        elif isinstance(command, SetLabels):
            doc["labels"] = merge_labels([], list(command.value))
        else:
            raise TypeError(f"unknown curation command: {command!r}")

    def batch_delete(self, file_hashes: Sequence[str]) -> int:
        """Delete many records by hash. Returns the number actually deleted."""
        count = 0
        for f_hash in file_hashes:
            if self.delete(f_hash):
                count += 1
        return count

    # =========================================================================
    # Serialization: Domain Models → TinyDB Documents
    # =========================================================================

    @staticmethod
    def _serialize(metadata: ImageMetadata) -> dict[str, Any]:
        """Convert ImageMetadata to a TinyDB-compatible dictionary.

        Handles:
        - Frozen dataclasses → nested dicts
        - CameraProfile enum → string value
        - GpsCoordinates → lat/lon/alt/datum dict
        - datetime → ISO 8601 string
        - raw_tags preserved as-is (already dict)
        """
        doc: dict[str, Any] = {
            "file_hash": metadata.file_hash,
            "file_info": {
                "name": metadata.file_info.name,
                "path": metadata.file_info.path,
                "size_bytes": metadata.file_info.size_bytes,
                "mime_type": metadata.file_info.mime_type,
                "modified_time": (
                    metadata.file_info.modified_time.isoformat()
                    if metadata.file_info.modified_time
                    else None
                ),
            },
            "dimensions": {
                "width": metadata.dimensions.width,
                "height": metadata.dimensions.height,
            },
            "exif": TinyDBRepository._serialize_exif(metadata.exif),
            "labels": list(metadata.labels),
            "rating": metadata.rating,
            "flagged": metadata.flagged,
            "added_at": metadata.added_at.isoformat(),
        }
        return doc

    @staticmethod
    def _serialize_exif(exif: ImageExifData) -> dict[str, Any]:
        """Serialize ImageExifData (three-tier model) to dict."""
        exif_doc: dict[str, Any] = {
            # Tier 1
            "camera_make": exif.camera_make,
            "camera_model": exif.camera_model,
            "f_stop": exif.f_stop,
            "exposure_time": exif.exposure_time,
            "iso": exif.iso,
            "focal_length": exif.focal_length,
            "captured_at": exif.captured_at.isoformat() if exif.captured_at else None,
            # Tier 2
            "camera_profile": exif.camera_profile.value,
            "location": None,
            "flash_fired": exif.flash_fired,
            "focal_length_35mm": exif.focal_length_35mm,
            "white_balance_mode": exif.white_balance_mode,
            "exposure_program": exif.exposure_program,
            "metering_mode": exif.metering_mode,
            "orientation": exif.orientation,
            # Tier 3
            "raw_tags": dict(exif.raw_tags),
        }

        if exif.location is not None:
            exif_doc["location"] = {
                "latitude": exif.location.latitude,
                "longitude": exif.location.longitude,
                "altitude": exif.location.altitude,
                "datum": exif.location.datum,
            }

        return exif_doc

    # =========================================================================
    # Mutation & Collection Operations
    # =========================================================================

    def update_metadata(self, file_hash: str, updates: dict) -> ImageMetadata | None:
        """Update user-controlled fields (rating, flag, labels) of one record.

        Raises:
            ValueError: If a value violates the curation rules; nothing is written.
        """
        doc = self._hash_index.get(file_hash)
        if not doc:
            return None

        # Validate everything first so a bad value can never be half-applied.
        if "rating" in updates:
            validate_rating(updates["rating"])
        for key in ("labels", "add_tags", "remove_tags"):
            if key in updates and (
                not isinstance(updates[key], (list, tuple, set))
                or not all(isinstance(t, str) for t in updates[key])
            ):
                raise ValueError(f"{key} must be a list of strings")

        if "rating" in updates:
            doc["rating"] = updates["rating"]
        if "flagged" in updates:
            doc["flagged"] = bool(updates["flagged"])
        if "labels" in updates:
            doc["labels"] = merge_labels([], list(updates["labels"]))
        if "add_tags" in updates:
            doc["labels"] = merge_labels(doc.get("labels", []), list(updates["add_tags"]))
        if "remove_tags" in updates:
            removed = set(updates["remove_tags"])
            doc["labels"] = [t for t in doc.get("labels", []) if t not in removed]

        q = Query()
        self._table.update(doc, q.file_hash == file_hash)
        self.rebuild_indexes()
        return self._deserialize(doc)

    _BATCH_ACTIONS = frozenset({"add_tag", "remove_tag", "set_rating", "set_flag", "delete"})

    def batch_update(self, file_hashes: list[str], updates: dict) -> int:
        """Apply one curation action to many records.

        Returns:
            Number of existing records the action was applied to (for ``delete``:
            the number removed). Unknown hashes are skipped.

        Raises:
            ValueError: For an unknown action or a value that violates the curation
                rules. Validation happens before any record is touched.
        """
        action = updates.get("action")
        value = updates.get("value")
        if action not in self._BATCH_ACTIONS:
            raise ValueError(
                f"unknown batch action {action!r}; expected one of {sorted(self._BATCH_ACTIONS)}"
            )
        if action in ("add_tag", "remove_tag"):
            value = validate_tag(value)
        elif action == "set_rating":
            validate_rating(value)
        elif action == "set_flag" and not isinstance(value, bool):
            raise ValueError(f"set_flag requires a boolean value; got {value!r}")

        count = 0
        q = Query()
        for f_hash in file_hashes:
            doc = self._hash_index.get(f_hash)
            if not doc:
                continue
            if action == "delete":
                self.delete(f_hash)
                count += 1
                continue
            if action == "add_tag":
                doc["labels"] = merge_labels(doc.get("labels", []), [value])
            elif action == "remove_tag":
                doc["labels"] = [t for t in doc.get("labels", []) if t != value]
            elif action == "set_rating":
                doc["rating"] = value
            elif action == "set_flag":
                doc["flagged"] = value

            self._table.update(doc, q.file_hash == f_hash)
            count += 1

        self.rebuild_indexes()
        return count

    # =========================================================================
    # Deserialization: TinyDB Documents → Domain Models
    # =========================================================================

    @staticmethod
    def _deserialize(doc: dict[str, Any]) -> ImageMetadata:
        """Convert a TinyDB document back to an ImageMetadata entity."""
        file_info = ImageFileInfo(
            name=doc["file_info"]["name"],
            path=doc["file_info"]["path"],
            size_bytes=doc["file_info"]["size_bytes"],
            mime_type=doc["file_info"]["mime_type"],
            modified_time=TinyDBRepository._parse_mtime(doc["file_info"].get("modified_time")),
        )

        dimensions = ImageDimensions(
            width=doc["dimensions"]["width"],
            height=doc["dimensions"]["height"],
        )

        exif = TinyDBRepository._deserialize_exif(doc["exif"])

        added_at = datetime.fromisoformat(doc["added_at"])

        return ImageMetadata(
            file_hash=doc["file_hash"],
            file_info=file_info,
            dimensions=dimensions,
            exif=exif,
            labels=doc.get("labels", []),
            rating=doc.get("rating"),
            flagged=doc.get("flagged", False),
            added_at=added_at,
        )

    @staticmethod
    def _parse_mtime(value: str | None) -> datetime | None:
        """Parse a stored mtime; legacy documents have none, and a bad value reads as none."""
        if not value:
            return None
        try:
            return to_naive(datetime.fromisoformat(value))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _deserialize_exif(exif_doc: dict[str, Any]) -> ImageExifData:
        """Deserialize exif dict back to ImageExifData."""
        location = None
        loc_doc = exif_doc.get("location")
        if loc_doc is not None:
            location = GpsCoordinates(
                latitude=loc_doc["latitude"],
                longitude=loc_doc["longitude"],
                altitude=loc_doc.get("altitude"),
                datum=loc_doc.get("datum", "WGS84"),
            )

        captured_at = None
        if exif_doc.get("captured_at"):
            try:
                captured_at = datetime.fromisoformat(exif_doc["captured_at"])
            except (ValueError, TypeError):
                captured_at = None

        camera_profile = CameraProfile.UNKNOWN
        profile_str = exif_doc.get("camera_profile")
        if profile_str:
            try:
                camera_profile = CameraProfile(profile_str)
            except ValueError:
                camera_profile = CameraProfile.UNKNOWN

        return ImageExifData(
            camera_make=exif_doc.get("camera_make"),
            camera_model=exif_doc.get("camera_model"),
            f_stop=exif_doc.get("f_stop"),
            exposure_time=exif_doc.get("exposure_time"),
            iso=exif_doc.get("iso"),
            focal_length=exif_doc.get("focal_length"),
            captured_at=captured_at,
            camera_profile=camera_profile,
            location=location,
            flash_fired=exif_doc.get("flash_fired"),
            focal_length_35mm=exif_doc.get("focal_length_35mm"),
            white_balance_mode=exif_doc.get("white_balance_mode"),
            exposure_program=exif_doc.get("exposure_program"),
            metering_mode=exif_doc.get("metering_mode"),
            orientation=exif_doc.get("orientation"),
            raw_tags=exif_doc.get("raw_tags", {}),
        )
