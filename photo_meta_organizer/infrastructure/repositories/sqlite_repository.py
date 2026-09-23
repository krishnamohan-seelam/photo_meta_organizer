"""SQLite-based implementation of ImageMetadataRepository (PMO-08, ADR-001).

One connection, guarded by a re-entrant lock, shared across threads (the ADR's
"single writer connection behind a lock" option). WAL mode and a busy timeout
still let concurrent readers proceed without blocking on the lock for long;
the lock exists because Python's ``sqlite3`` module is not safe to share
across threads without one, and it also makes ``:memory:`` databases (used by
tests) behave correctly, since an in-memory database is private to the
connection that created it.
"""

import json
import math
import sqlite3
import threading
from collections.abc import Sequence
from datetime import datetime
from typing import Any

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
    is_valid_rating,
    merge_labels,
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

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS photos (
    file_hash TEXT PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mime_type TEXT NOT NULL,
    mtime TEXT,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    captured_at TEXT,
    camera_make TEXT,
    camera_model TEXT,
    f_stop REAL,
    exposure_time TEXT,
    iso INTEGER,
    focal_length TEXT,
    camera_profile TEXT NOT NULL DEFAULT 'unknown',
    flash_fired INTEGER,
    focal_length_35mm TEXT,
    white_balance_mode TEXT,
    exposure_program TEXT,
    metering_mode TEXT,
    orientation INTEGER,
    gps_lat REAL,
    gps_lon REAL,
    gps_alt REAL,
    gps_datum TEXT,
    raw_tags TEXT NOT NULL DEFAULT '{}',
    rating INTEGER CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
    flagged INTEGER NOT NULL DEFAULT 0,
    added_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_photos_captured_at ON photos(captured_at);
CREATE INDEX IF NOT EXISTS idx_photos_size_bytes ON photos(size_bytes);
CREATE INDEX IF NOT EXISTS idx_photos_camera_make ON photos(camera_make);
CREATE INDEX IF NOT EXISTS idx_photos_flagged_rating ON photos(flagged, rating);

CREATE TABLE IF NOT EXISTS photo_labels (
    file_hash TEXT NOT NULL REFERENCES photos(file_hash) ON DELETE CASCADE,
    label TEXT NOT NULL,
    PRIMARY KEY (file_hash, label)
);
CREATE INDEX IF NOT EXISTS idx_photo_labels_label ON photo_labels(label);

CREATE TABLE IF NOT EXISTS collections (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_photos (
    collection TEXT NOT NULL REFERENCES collections(name) ON DELETE CASCADE,
    file_hash TEXT NOT NULL REFERENCES photos(file_hash) ON DELETE CASCADE,
    PRIMARY KEY (collection, file_hash)
);
"""

_PHOTO_COLUMNS = [
    "file_hash",
    "path",
    "name",
    "size_bytes",
    "mime_type",
    "mtime",
    "width",
    "height",
    "captured_at",
    "camera_make",
    "camera_model",
    "f_stop",
    "exposure_time",
    "iso",
    "focal_length",
    "camera_profile",
    "flash_fired",
    "focal_length_35mm",
    "white_balance_mode",
    "exposure_program",
    "metering_mode",
    "orientation",
    "gps_lat",
    "gps_lon",
    "gps_alt",
    "gps_datum",
    "raw_tags",
    "rating",
    "flagged",
    "added_at",
]


class SqliteRepository:
    """SQLite-backed repository for ImageMetadata persistence (ADR-001)."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 5000")
        if db_path != ":memory:":
            self.connection.execute("PRAGMA journal_mode = WAL")
        with self.lock, self.connection:
            self.connection.executescript(_SCHEMA_SQL)

    def close(self) -> None:
        with self.lock:
            self.connection.close()

    # =========================================================================
    # Save / upsert
    # =========================================================================

    def save(self, metadata: ImageMetadata) -> None:
        with self.lock, self.connection:
            self._upsert(metadata)

    def save_many(self, items: Sequence[ImageMetadata]) -> None:
        with self.lock, self.connection:
            for metadata in items:
                self._upsert(metadata)

    def _upsert(self, metadata: ImageMetadata) -> None:
        """Insert or update by file hash. Must run inside an open transaction."""
        values = _to_row(metadata)
        placeholders = ", ".join("?" for _ in _PHOTO_COLUMNS)
        update_clause = ", ".join(
            f"{col}=excluded.{col}" for col in _PHOTO_COLUMNS if col != "file_hash"
        )
        self.connection.execute(
            f"""
            INSERT INTO photos ({", ".join(_PHOTO_COLUMNS)}) VALUES ({placeholders})
            ON CONFLICT(file_hash) DO UPDATE SET {update_clause}
            """,
            [values[col] for col in _PHOTO_COLUMNS],
        )
        self.connection.execute(
            "DELETE FROM photo_labels WHERE file_hash = ?", (metadata.file_hash,)
        )
        for label in merge_labels([], list(metadata.labels)):
            self.connection.execute(
                "INSERT OR IGNORE INTO photo_labels (file_hash, label) VALUES (?, ?)",
                (metadata.file_hash, label),
            )

    def replace(self, old_hash: str, metadata: ImageMetadata) -> None:
        with self.lock, self.connection:
            if old_hash != metadata.file_hash:
                self.connection.execute("DELETE FROM photos WHERE file_hash = ?", (old_hash,))
            self._upsert(metadata)

    def refresh_fingerprints(self, updates: Sequence[tuple[str, int, datetime]]) -> int:
        with self.lock, self.connection:
            touched = 0
            for file_hash, size, mtime in updates:
                cur = self.connection.execute(
                    "UPDATE photos SET size_bytes = ?, mtime = ? WHERE file_hash = ?",
                    (size, mtime.isoformat(), file_hash),
                )
                touched += cur.rowcount
            return touched

    # =========================================================================
    # Reads
    # =========================================================================

    def get_by_filehash(self, file_hash: str) -> ImageMetadata | None:
        with self.lock:
            row = self.connection.execute(
                "SELECT * FROM photos WHERE file_hash = ?", (file_hash,)
            ).fetchone()
            if row is None:
                return None
            return _from_row(row, self._labels_for([file_hash]).get(file_hash, []))

    def get_by_path(self, file_path: str) -> ImageMetadata | None:
        with self.lock:
            row = self.connection.execute(
                "SELECT * FROM photos WHERE path = ?", (file_path,)
            ).fetchone()
            if row is None:
                return None
            return _from_row(row, self._labels_for([row["file_hash"]]).get(row["file_hash"], []))

    def list_all(self) -> list[ImageMetadata]:
        with self.lock:
            rows = self.connection.execute("SELECT * FROM photos").fetchall()
            labels_by_hash = self._labels_for([r["file_hash"] for r in rows])
            return [_from_row(r, labels_by_hash.get(r["file_hash"], [])) for r in rows]

    def delete(self, file_hash: str) -> bool:
        with self.lock, self.connection:
            cur = self.connection.execute("DELETE FROM photos WHERE file_hash = ?", (file_hash,))
            return cur.rowcount > 0

    def delete_by_path(self, file_path: str) -> bool:
        with self.lock, self.connection:
            cur = self.connection.execute("DELETE FROM photos WHERE path = ?", (file_path,))
            return cur.rowcount > 0

    def batch_delete(self, file_hashes: Sequence[str]) -> int:
        if not file_hashes:
            return 0
        with self.lock, self.connection:
            placeholders = ", ".join("?" for _ in file_hashes)
            cur = self.connection.execute(
                f"DELETE FROM photos WHERE file_hash IN ({placeholders})",
                list(file_hashes),
            )
            return cur.rowcount

    def find_by_paths(self, paths: list[str]) -> list[ImageMetadata]:
        if not paths:
            return []
        with self.lock:
            placeholders = ", ".join("?" for _ in paths)
            rows = self.connection.execute(
                f"SELECT * FROM photos WHERE path IN ({placeholders})", paths
            ).fetchall()
            labels_by_hash = self._labels_for([r["file_hash"] for r in rows])
            return [_from_row(r, labels_by_hash.get(r["file_hash"], [])) for r in rows]

    def count(self) -> int:
        with self.lock:
            return self.connection.execute("SELECT COUNT(*) FROM photos").fetchone()[0]

    def _labels_for(self, file_hashes: Sequence[str]) -> dict[str, list[str]]:
        if not file_hashes:
            return {}
        placeholders = ", ".join("?" for _ in file_hashes)
        rows = self.connection.execute(
            f"SELECT file_hash, label FROM photo_labels WHERE file_hash IN ({placeholders}) "
            "ORDER BY rowid",
            list(file_hashes),
        ).fetchall()
        result: dict[str, list[str]] = {}
        for row in rows:
            result.setdefault(row["file_hash"], []).append(row["label"])
        return result

    # =========================================================================
    # Search, paging and facets
    # =========================================================================

    def query(self, query: SearchQuery) -> Page[ImageMetadata]:
        clauses: list[str] = []
        params: list[Any] = []

        if query.date_start:
            clauses.append("captured_at IS NOT NULL AND captured_at >= ?")
            params.append(query.date_start.isoformat())
        if query.date_end:
            clauses.append("captured_at IS NOT NULL AND captured_at <= ?")
            params.append(query.date_end.isoformat())
        if query.camera_make:
            clauses.append("camera_make LIKE ? ESCAPE '\\'")
            params.append(f"%{_escape_like(query.camera_make)}%")
        if query.camera_model:
            clauses.append("camera_model LIKE ? ESCAPE '\\'")
            params.append(f"%{_escape_like(query.camera_model)}%")
        if query.rating is not None:
            clauses.append("rating = ?")
            params.append(query.rating)
        if query.flagged is not None:
            clauses.append("flagged = ?")
            params.append(1 if query.flagged else 0)
        if query.tags:
            placeholders = ", ".join("?" for _ in query.tags)
            clauses.append(
                f"file_hash IN (SELECT file_hash FROM photo_labels WHERE label IN "
                f"({placeholders}) GROUP BY file_hash HAVING COUNT(DISTINCT label) = ?)"
            )
            params.extend(query.tags)
            params.append(len(set(query.tags)))
        if query.search_term:
            term = f"%{_escape_like(query.search_term)}%"
            clauses.append(
                "(name LIKE ? ESCAPE '\\' OR path LIKE ? ESCAPE '\\' OR "
                "camera_make LIKE ? ESCAPE '\\' OR camera_model LIKE ? ESCAPE '\\' OR "
                "file_hash IN (SELECT file_hash FROM photo_labels WHERE label LIKE ? ESCAPE '\\'))"
            )
            params.extend([term, term, term, term, term])

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order_sql = self._order_by_sql(query.sort_by, query.sort_order)

        with self.lock:
            if (
                query.location_lat is not None
                and query.location_lon is not None
                and (query.radius_km is not None)
            ):
                # No trig functions in stock SQLite: filter by distance in Python, over
                # the rows that already passed every other filter.
                rows = self.connection.execute(
                    f"SELECT * FROM photos {where_sql} ORDER BY {order_sql}", params
                ).fetchall()
                labels_by_hash = self._labels_for([r["file_hash"] for r in rows])
                candidates = [_from_row(r, labels_by_hash.get(r["file_hash"], [])) for r in rows]
                matched = [
                    m
                    for m in candidates
                    if m.exif.location is not None
                    and haversine_distance_km(
                        query.location_lat,
                        query.location_lon,
                        m.exif.location.latitude,
                        m.exif.location.longitude,
                    )
                    <= query.radius_km
                ]
                return _paginate(matched, query.page, query.page_size)

            total_count = self.connection.execute(
                f"SELECT COUNT(*) FROM photos {where_sql}", params
            ).fetchone()[0]
            page_size = max(1, query.page_size)
            import math as _math

            total_pages = max(1, _math.ceil(total_count / page_size)) if total_count > 0 else 1
            page = max(1, min(query.page, total_pages))
            offset = (page - 1) * page_size

            rows = self.connection.execute(
                f"SELECT * FROM photos {where_sql} ORDER BY {order_sql} LIMIT ? OFFSET ?",
                [*params, page_size, offset],
            ).fetchall()
            labels_by_hash = self._labels_for([r["file_hash"] for r in rows])
            items = [_from_row(r, labels_by_hash.get(r["file_hash"], [])) for r in rows]
            return Page(
                items=items,
                total_count=total_count,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
            )

    @staticmethod
    def _order_by_sql(sort_by: str, sort_order: str) -> str:
        direction = "DESC" if sort_order.lower() == "desc" else "ASC"
        column = {
            "size_bytes": "size_bytes",
            "camera_model": "COALESCE(camera_model, '')",
            "file_name": "name",
        }.get(sort_by, "captured_at")
        return f"{column} {direction}"

    def facets(self) -> Facets:
        with self.lock:
            camera_rows = self.connection.execute(
                "SELECT camera_make AS name, COUNT(*) AS n FROM photos "
                "WHERE camera_make IS NOT NULL GROUP BY camera_make ORDER BY camera_make"
            ).fetchall()
            tag_rows = self.connection.execute(
                "SELECT label AS name, COUNT(*) AS n FROM photo_labels "
                "GROUP BY label ORDER BY label"
            ).fetchall()
            year_rows = self.connection.execute(
                "SELECT strftime('%Y', captured_at) AS year, COUNT(*) AS n FROM photos "
                "WHERE captured_at IS NOT NULL GROUP BY year ORDER BY year"
            ).fetchall()
            bounds_row = self.connection.execute(
                "SELECT MIN(gps_lat), MAX(gps_lat), MIN(gps_lon), MAX(gps_lon) FROM photos "
                "WHERE gps_lat IS NOT NULL"
            ).fetchone()

        gps_bounds = None
        if bounds_row and bounds_row[0] is not None:
            gps_bounds = GpsBounds(
                min_lat=bounds_row[0],
                max_lat=bounds_row[1],
                min_lon=bounds_row[2],
                max_lon=bounds_row[3],
            )

        return Facets(
            cameras=[FacetCount(name=r["name"], count=r["n"]) for r in camera_rows],
            tags=[FacetCount(name=r["name"], count=r["n"]) for r in tag_rows],
            years=[FacetCount(name=r["year"], count=r["n"]) for r in year_rows],
            gps_bounds=gps_bounds,
        )

    # =========================================================================
    # Typed curation commands
    # =========================================================================

    def apply(self, file_hash: str, command: CurationCommand) -> ImageMetadata | None:
        with self.lock, self.connection:
            if (
                self.connection.execute(
                    "SELECT 1 FROM photos WHERE file_hash = ?", (file_hash,)
                ).fetchone()
                is None
            ):
                return None
            self._apply_command(file_hash, command)
        return self.get_by_filehash(file_hash)

    def apply_batch(self, file_hashes: Sequence[str], command: CurationCommand) -> int:
        count = 0
        with self.lock, self.connection:
            for file_hash in file_hashes:
                if (
                    self.connection.execute(
                        "SELECT 1 FROM photos WHERE file_hash = ?", (file_hash,)
                    ).fetchone()
                    is None
                ):
                    continue
                self._apply_command(file_hash, command)
                count += 1
        return count

    def _apply_command(self, file_hash: str, command: CurationCommand) -> None:
        """Mutate the record for ``file_hash``. Must run inside an open transaction."""
        if isinstance(command, SetRating):
            self.connection.execute(
                "UPDATE photos SET rating = ? WHERE file_hash = ?",
                (command.value, file_hash),
            )
        elif isinstance(command, SetFlag):
            self.connection.execute(
                "UPDATE photos SET flagged = ? WHERE file_hash = ?",
                (1 if command.value else 0, file_hash),
            )
        elif isinstance(command, AddTag):
            self.connection.execute(
                "INSERT OR IGNORE INTO photo_labels (file_hash, label) VALUES (?, ?)",
                (file_hash, command.value),
            )
        elif isinstance(command, RemoveTag):
            self.connection.execute(
                "DELETE FROM photo_labels WHERE file_hash = ? AND label = ?",
                (file_hash, command.value),
            )
        elif isinstance(command, SetLabels):
            self.connection.execute("DELETE FROM photo_labels WHERE file_hash = ?", (file_hash,))
            for label in merge_labels([], list(command.value)):
                self.connection.execute(
                    "INSERT OR IGNORE INTO photo_labels (file_hash, label) VALUES (?, ?)",
                    (file_hash, label),
                )
        else:
            raise TypeError(f"unknown curation command: {command!r}")

    # =========================================================================
    # Deprecated dict-based curation (kept until PMO-09 migrates callers)
    # =========================================================================

    def update_metadata(self, file_hash: str, updates: dict) -> ImageMetadata | None:
        from photo_meta_organizer.domain.curation import validate_rating, validate_tag

        if "rating" in updates:
            validate_rating(updates["rating"])
        for key in ("labels", "add_tags", "remove_tags"):
            if key in updates and (
                not isinstance(updates[key], (list, tuple, set))
                or not all(isinstance(t, str) for t in updates[key])
            ):
                raise ValueError(f"{key} must be a list of strings")

        with self.lock, self.connection:
            if (
                self.connection.execute(
                    "SELECT 1 FROM photos WHERE file_hash = ?", (file_hash,)
                ).fetchone()
                is None
            ):
                return None
            if "rating" in updates:
                self._apply_command(file_hash, SetRating(updates["rating"]))
            if "flagged" in updates:
                self._apply_command(file_hash, SetFlag(bool(updates["flagged"])))
            if "labels" in updates:
                self._apply_command(file_hash, SetLabels(list(updates["labels"])))
            if "add_tags" in updates:
                for tag in updates["add_tags"]:
                    self._apply_command(file_hash, AddTag(validate_tag(tag)))
            if "remove_tags" in updates:
                for tag in updates["remove_tags"]:
                    self._apply_command(file_hash, RemoveTag(validate_tag(tag)))
        return self.get_by_filehash(file_hash)

    _BATCH_ACTIONS = frozenset({"add_tag", "remove_tag", "set_rating", "set_flag", "delete"})

    def batch_update(self, file_hashes: list[str], updates: dict) -> int:
        from photo_meta_organizer.domain.curation import validate_rating, validate_tag

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

        if action == "delete":
            return self.batch_delete(file_hashes)

        command: CurationCommand
        if action == "add_tag":
            command = AddTag(value)
        elif action == "remove_tag":
            command = RemoveTag(value)
        elif action == "set_rating":
            command = SetRating(value)
        else:
            command = SetFlag(value)
        return self.apply_batch(file_hashes, command)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _paginate(items: list[ImageMetadata], page: int, page_size: int) -> Page[ImageMetadata]:
    total_count = len(items)
    page_size = max(1, page_size)
    total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    return Page(
        items=items[start:end],
        total_count=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


def _to_row(metadata: ImageMetadata) -> dict[str, Any]:
    exif = metadata.exif
    location = exif.location
    return {
        "file_hash": metadata.file_hash,
        "path": metadata.file_info.path,
        "name": metadata.file_info.name,
        "size_bytes": metadata.file_info.size_bytes,
        "mime_type": metadata.file_info.mime_type,
        "mtime": (
            metadata.file_info.modified_time.isoformat()
            if metadata.file_info.modified_time
            else None
        ),
        "width": metadata.dimensions.width,
        "height": metadata.dimensions.height,
        "captured_at": exif.captured_at.isoformat() if exif.captured_at else None,
        "camera_make": exif.camera_make,
        "camera_model": exif.camera_model,
        "f_stop": exif.f_stop,
        "exposure_time": exif.exposure_time,
        "iso": exif.iso,
        "focal_length": exif.focal_length,
        "camera_profile": exif.camera_profile.value,
        "flash_fired": None if exif.flash_fired is None else int(exif.flash_fired),
        "focal_length_35mm": exif.focal_length_35mm,
        "white_balance_mode": exif.white_balance_mode,
        "exposure_program": exif.exposure_program,
        "metering_mode": exif.metering_mode,
        "orientation": exif.orientation,
        "gps_lat": location.latitude if location else None,
        "gps_lon": location.longitude if location else None,
        "gps_alt": location.altitude if location else None,
        "gps_datum": location.datum if location else None,
        "raw_tags": json.dumps(dict(exif.raw_tags)),
        # A rating already poisoned upstream (e.g. a legacy JSON import) must not
        # trip the CHECK constraint and abort the whole write; drop it instead,
        # matching the tolerance the API layer already gives a corrupt stored value.
        "rating": metadata.rating if is_valid_rating(metadata.rating) else None,
        "flagged": int(metadata.flagged),
        "added_at": metadata.added_at.isoformat(),
    }


def _from_row(row: sqlite3.Row, labels: list[str]) -> ImageMetadata:
    location = None
    if row["gps_lat"] is not None and row["gps_lon"] is not None:
        location = GpsCoordinates(
            latitude=row["gps_lat"],
            longitude=row["gps_lon"],
            altitude=row["gps_alt"],
            datum=row["gps_datum"] or "WGS84",
        )

    try:
        camera_profile = CameraProfile(row["camera_profile"])
    except ValueError:
        camera_profile = CameraProfile.UNKNOWN

    exif = ImageExifData(
        camera_make=row["camera_make"],
        camera_model=row["camera_model"],
        f_stop=row["f_stop"],
        exposure_time=row["exposure_time"],
        iso=row["iso"],
        focal_length=row["focal_length"],
        captured_at=(datetime.fromisoformat(row["captured_at"]) if row["captured_at"] else None),
        camera_profile=camera_profile,
        location=location,
        flash_fired=None if row["flash_fired"] is None else bool(row["flash_fired"]),
        focal_length_35mm=row["focal_length_35mm"],
        white_balance_mode=row["white_balance_mode"],
        exposure_program=row["exposure_program"],
        metering_mode=row["metering_mode"],
        orientation=row["orientation"],
        raw_tags=json.loads(row["raw_tags"]) if row["raw_tags"] else {},
    )

    file_info = ImageFileInfo(
        name=row["name"],
        path=row["path"],
        size_bytes=row["size_bytes"],
        mime_type=row["mime_type"],
        modified_time=(to_naive(datetime.fromisoformat(row["mtime"])) if row["mtime"] else None),
    )

    return ImageMetadata(
        file_hash=row["file_hash"],
        file_info=file_info,
        dimensions=ImageDimensions(width=row["width"], height=row["height"]),
        exif=exif,
        labels=labels,
        rating=row["rating"],
        flagged=bool(row["flagged"]),
        added_at=datetime.fromisoformat(row["added_at"]),
    )
