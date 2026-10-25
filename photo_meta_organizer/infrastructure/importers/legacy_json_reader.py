"""Read-only access to a legacy TinyDB ``metadata.json`` (ADR-001, ADR-003 R7, ticket 19).

Before SQLite the library lived in one TinyDB JSON file. The only thing left to do with such a
file is to read it once, for :func:`~.legacy_json_importer.import_legacy_json`. This module
is that reader and nothing more: it never writes (apart from the self-repair of a damaged
file that earlier versions already did) and offers no queries.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any

from tinydb import TinyDB

from photo_meta_organizer.application.interfaces.collection_repository import CollectionRecord
from photo_meta_organizer.domain.datetimes import to_naive
from photo_meta_organizer.domain.models import (
    CameraProfile,
    GpsCoordinates,
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)

logger = logging.getLogger(__name__)


def _repair_corrupted_db(db_path: str) -> None:
    """Self-heal a JSON file that has extra trailing data or corrupted duplicate blocks."""
    if not os.path.exists(db_path):
        return
    try:
        with open(db_path, encoding="utf-8", errors="ignore") as f:
            content = f.read()
        obj, _ = json.JSONDecoder().raw_decode(content)
        with open(db_path, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)
        logger.info("Successfully repaired corrupted database at %s", db_path)
    except Exception as repair_err:
        logger.error("Failed to auto-repair %s: %s", db_path, repair_err)


class LegacyJsonReader:
    """Reads the photos and collections of a legacy TinyDB file."""

    def __init__(self, json_path: str) -> None:
        self._path = json_path
        try:
            self._db = TinyDB(json_path, indent=2)
            self._db.table("metadata").all()  # a damaged file only fails when read
        except json.decoder.JSONDecodeError as exc:
            logger.warning("JSONDecodeError in %s: %s. Performing auto-repair...", json_path, exc)
            _repair_corrupted_db(json_path)
            self._db = TinyDB(json_path, indent=2)

    def records(self) -> list[ImageMetadata]:
        """Every stored photo."""
        return [_deserialize(doc) for doc in self._db.table("metadata").all()]

    def collections(self) -> list[CollectionRecord]:
        """Every stored collection."""
        return [
            CollectionRecord(
                name=doc.get("name", ""),
                description=doc.get("description", ""),
                photo_hashes=list(doc.get("photo_hashes", [])),
                updated_at=doc.get("updated_at", ""),
            )
            for doc in self._db.table("collections").all()
        ]

    def close(self) -> None:
        self._db.close()


def _deserialize(doc: dict[str, Any]) -> ImageMetadata:
    """Convert a TinyDB document to an ImageMetadata entity."""
    info = doc["file_info"]
    return ImageMetadata(
        file_hash=doc["file_hash"],
        file_info=ImageFileInfo(
            name=info["name"],
            path=info["path"],
            size_bytes=info["size_bytes"],
            mime_type=info["mime_type"],
            modified_time=_parse_mtime(info.get("modified_time")),
        ),
        dimensions=ImageDimensions(
            width=doc["dimensions"]["width"], height=doc["dimensions"]["height"]
        ),
        exif=_deserialize_exif(doc["exif"]),
        labels=doc.get("labels", []),
        rating=doc.get("rating"),
        flagged=doc.get("flagged", False),
        added_at=datetime.fromisoformat(doc["added_at"]),
    )


def _parse_mtime(value: str | None) -> datetime | None:
    """Legacy documents may have no mtime, and a bad value reads as none."""
    if not value:
        return None
    try:
        return to_naive(datetime.fromisoformat(value))
    except (ValueError, TypeError):
        return None


def _deserialize_exif(exif_doc: dict[str, Any]) -> ImageExifData:
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
    if exif_doc.get("camera_profile"):
        try:
            camera_profile = CameraProfile(exif_doc["camera_profile"])
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
