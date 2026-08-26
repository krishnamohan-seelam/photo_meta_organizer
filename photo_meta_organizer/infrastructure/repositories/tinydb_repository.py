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

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from tinydb import TinyDB, Query

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

    def __init__(self, db_path: str) -> None:
        """Initialize with path to the JSON database file.

        Args:
            db_path: File path for the TinyDB JSON file.
                     Created automatically if it doesn't exist.
        """
        self._db = TinyDB(db_path, indent=2)
        self._table = self._db.table("metadata")
        
        # Index data structures
        self._hash_index: Dict[str, Dict[str, Any]] = {}
        self._path_index: Dict[str, Dict[str, Any]] = {}
        self._captured_at_index: List[tuple[datetime, Dict[str, Any]]] = []
        self._size_index: List[tuple[int, Dict[str, Any]]] = []
        
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
                    captured_at_dt = datetime.fromisoformat(captured_at_str)
                    self._captured_at_index.append((captured_at_dt, doc))
                except (ValueError, TypeError):
                    pass

        self._captured_at_index.sort(key=lambda x: x[0])
        self._size_index.sort(key=lambda x: x[0])

    def close(self) -> None:
        """Close the database connection."""
        self._db.close()

    # =========================================================================
    # Protocol Methods
    # =========================================================================

    def save(self, metadata: ImageMetadata) -> None:
        """Persist image metadata with upsert semantics.

        If a record with the same file_hash exists, it is updated.
        Otherwise, a new record is inserted.

        Args:
            metadata: The ImageMetadata entity to persist.
        """
        doc = self._serialize(metadata)
        q = Query()
        existing = self._table.search(q.file_hash == metadata.file_hash)

        if existing:
            self._table.update(doc, q.file_hash == metadata.file_hash)
            logger.debug("Updated metadata for hash: %s", metadata.file_hash[:12])
        else:
            self._table.insert(doc)
            logger.debug("Inserted metadata for hash: %s", metadata.file_hash[:12])

        self.rebuild_indexes()

    def get_by_filehash(self, file_hash: str) -> Optional[ImageMetadata]:
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

    def get_by_path(self, file_path: str) -> Optional[ImageMetadata]:
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

    def list_all(self) -> List[ImageMetadata]:
        """Retrieve all stored metadata records.

        Returns:
            List of all ImageMetadata entities in storage.
        """
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

    def find_by_paths(self, paths: List[str]) -> List[ImageMetadata]:
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
        date_start: Optional[datetime] = None,
        date_end: Optional[datetime] = None,
    ) -> List[ImageMetadata]:
        """Find metadata records captured within a date range using captured_at index.

        Args:
            date_start: Minimum captured_at datetime (inclusive).
            date_end: Maximum captured_at datetime (inclusive).

        Returns:
            List of ImageMetadata records within the date range.
        """
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
        min_bytes: Optional[int] = None,
        max_bytes: Optional[int] = None,
    ) -> List[ImageMetadata]:
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
    # Serialization: Domain Models → TinyDB Documents
    # =========================================================================

    @staticmethod
    def _serialize(metadata: ImageMetadata) -> Dict[str, Any]:
        """Convert ImageMetadata to a TinyDB-compatible dictionary.

        Handles:
        - Frozen dataclasses → nested dicts
        - CameraProfile enum → string value
        - GpsCoordinates → lat/lon/alt/datum dict
        - datetime → ISO 8601 string
        - raw_tags preserved as-is (already dict)
        """
        doc: Dict[str, Any] = {
            "file_hash": metadata.file_hash,
            "file_info": {
                "name": metadata.file_info.name,
                "path": metadata.file_info.path,
                "size_bytes": metadata.file_info.size_bytes,
                "mime_type": metadata.file_info.mime_type,
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
    def _serialize_exif(exif: ImageExifData) -> Dict[str, Any]:
        """Serialize ImageExifData (three-tier model) to dict."""
        exif_doc: Dict[str, Any] = {
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

    def update_metadata(self, file_hash: str, updates: dict) -> Optional[ImageMetadata]:
        """Update specific fields of an ImageMetadata entity."""
        doc = self._hash_index.get(file_hash)
        if not doc:
            return None

        if "rating" in updates:
            doc["rating"] = updates["rating"]
        if "flagged" in updates:
            doc["flagged"] = bool(updates["flagged"])
        if "labels" in updates:
            doc["labels"] = list(updates["labels"])
        if "add_tags" in updates:
            current_tags = set(doc.get("labels", []))
            current_tags.update(updates["add_tags"])
            doc["labels"] = list(current_tags)
        if "remove_tags" in updates:
            current_tags = set(doc.get("labels", []))
            current_tags.difference_update(updates["remove_tags"])
            doc["labels"] = list(current_tags)

        q = Query()
        self._table.update(doc, q.file_hash == file_hash)
        self.rebuild_indexes()
        return self._deserialize(doc)

    def batch_update(self, file_hashes: List[str], updates: dict) -> int:
        """Apply batch updates across multiple image records atomically."""
        count = 0
        q = Query()
        action = updates.get("action")
        value = updates.get("value")

        for f_hash in file_hashes:
            doc = self._hash_index.get(f_hash)
            if not doc:
                continue
            if action == "add_tag" and isinstance(value, str):
                current_tags = set(doc.get("labels", []))
                current_tags.add(value)
                doc["labels"] = list(current_tags)
            elif action == "remove_tag" and isinstance(value, str):
                current_tags = set(doc.get("labels", []))
                current_tags.discard(value)
                doc["labels"] = list(current_tags)
            elif action == "set_rating":
                doc["rating"] = value
            elif action == "set_flag":
                doc["flagged"] = bool(value)
            elif action == "delete":
                self.delete(f_hash)
                count += 1
                continue

            self._table.update(doc, q.file_hash == f_hash)
            count += 1

        self.rebuild_indexes()
        return count

    def get_collections(self) -> List[dict]:
        """Retrieve all stored collections."""
        col_table = self._db.table("collections")
        return col_table.all()

    def save_collection(self, name: str, photo_hashes: List[str], description: str = "") -> dict:
        """Save or update a named collection."""
        col_table = self._db.table("collections")
        q = Query()
        col_doc = {
            "name": name,
            "description": description,
            "photo_hashes": list(photo_hashes),
            "updated_at": datetime.utcnow().isoformat(),
        }
        col_table.upsert(col_doc, q.name == name)
        return col_doc

    # =========================================================================
    # Deserialization: TinyDB Documents → Domain Models
    # =========================================================================

    @staticmethod
    def _deserialize(doc: Dict[str, Any]) -> ImageMetadata:
        """Convert a TinyDB document back to an ImageMetadata entity."""
        file_info = ImageFileInfo(
            name=doc["file_info"]["name"],
            path=doc["file_info"]["path"],
            size_bytes=doc["file_info"]["size_bytes"],
            mime_type=doc["file_info"]["mime_type"],
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
    def _deserialize_exif(exif_doc: Dict[str, Any]) -> ImageExifData:
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

    def close(self) -> None:
        """Close the underlying TinyDB database file."""
        self._db.close()
