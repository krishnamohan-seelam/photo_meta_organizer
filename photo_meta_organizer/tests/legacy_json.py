"""Test helper: write a legacy TinyDB ``metadata.json`` (the format ADR-001 retired).

Production code only ever reads such a file (``infrastructure.importers.legacy_json_reader``).
Tests that need one build it here, in the shape the old ``TinyDBRepository`` stored.
"""

from typing import Any

from tinydb import Query, TinyDB

from photo_meta_organizer.domain.datetimes import utc_now_naive
from photo_meta_organizer.domain.models import ImageExifData, ImageMetadata


def _exif_doc(exif: ImageExifData) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "camera_make": exif.camera_make,
        "camera_model": exif.camera_model,
        "f_stop": exif.f_stop,
        "exposure_time": exif.exposure_time,
        "iso": exif.iso,
        "focal_length": exif.focal_length,
        "captured_at": exif.captured_at.isoformat() if exif.captured_at else None,
        "camera_profile": exif.camera_profile.value,
        "location": None,
        "flash_fired": exif.flash_fired,
        "focal_length_35mm": exif.focal_length_35mm,
        "white_balance_mode": exif.white_balance_mode,
        "exposure_program": exif.exposure_program,
        "metering_mode": exif.metering_mode,
        "orientation": exif.orientation,
        "raw_tags": dict(exif.raw_tags),
    }
    if exif.location is not None:
        doc["location"] = {
            "latitude": exif.location.latitude,
            "longitude": exif.location.longitude,
            "altitude": exif.location.altitude,
            "datum": exif.location.datum,
        }
    return doc


def _doc(m: ImageMetadata) -> dict[str, Any]:
    info = m.file_info
    return {
        "file_hash": m.file_hash,
        "file_info": {
            "name": info.name,
            "path": info.path,
            "size_bytes": info.size_bytes,
            "mime_type": info.mime_type,
            "modified_time": info.modified_time.isoformat() if info.modified_time else None,
        },
        "dimensions": {"width": m.dimensions.width, "height": m.dimensions.height},
        "exif": _exif_doc(m.exif),
        "labels": list(m.labels),
        "rating": m.rating,
        "flagged": m.flagged,
        "added_at": m.added_at.isoformat(),
    }


class LegacyJsonWriter:
    """Builds a legacy file: ``save`` photos, ``save_collection``, then ``close``.

    ``db`` and ``table`` are exposed so a test can poison a document by hand.
    """

    def __init__(self, path: str) -> None:
        self.db = TinyDB(path, indent=2)
        self.table = self.db.table("metadata")

    def save(self, metadata: ImageMetadata) -> None:
        self.table.upsert(_doc(metadata), Query().file_hash == metadata.file_hash)

    def save_collection(self, name: str, photo_hashes: list[str], description: str = "") -> None:
        self.db.table("collections").upsert(
            {
                "name": name,
                "description": description,
                "photo_hashes": list(photo_hashes),
                "updated_at": utc_now_naive().isoformat(),
            },
            Query().name == name,
        )

    def close(self) -> None:
        self.db.close()
