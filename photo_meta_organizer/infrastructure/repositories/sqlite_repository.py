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
from dataclasses import replace
from datetime import datetime
from typing import Any, NamedTuple, TypeVar

from photo_meta_organizer.application.interfaces.search_types import (
    BoundingBox,
    FacetCount,
    Facets,
    GeoCluster,
    GpsBounds,
    LibraryStats,
    Page,
    SearchQuery,
)
from photo_meta_organizer.domain.curation import (
    AddTag,
    Curation,
    CurationCommand,
    RemoveTag,
    SetFlag,
    SetLabels,
    SetRating,
    is_valid_rating,
    merge_curation,
    merge_labels,
)
from photo_meta_organizer.domain.datetimes import to_naive, utc_now_naive
from photo_meta_organizer.domain.geo import haversine_distance_km
from photo_meta_organizer.domain.models import (
    CameraProfile,
    GpsCoordinates,
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
    StoredFile,
)
from photo_meta_organizer.infrastructure.repositories.migrations import migrate

T = TypeVar("T")


class _StoredCuration(NamedTuple):
    curation: Curation
    added_at: str  # ISO timestamp, as stored


# Extracted from the content: one row per Asset.
_ASSET_COLUMNS = [
    "file_hash",
    "size_bytes",
    "mime_type",
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
    "extracted_at",
]


class SqliteRepository:
    """SQLite-backed repository for ImageMetadata persistence (ADR-001, ADR-003 R3).

    An Asset (content, keyed by hash) is stored once in ``assets``, each path holding
    it in ``files``, and the user's decisions in ``curation`` and ``asset_labels``.
    Reads go through ``photo_view``: one row per Asset with its primary file, so an
    :class:`ImageMetadata` still carries one path.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 5000")
        if db_path != ":memory:":
            self.connection.execute("PRAGMA journal_mode = WAL")
        try:
            with self.lock:
                migrate(self.connection, db_path)
        except BaseException:
            self.connection.close()  # a refused or failed open must not keep the file locked
            raise

    def close(self) -> None:
        with self.lock:
            self.connection.close()

    # =========================================================================
    # Save / upsert
    # =========================================================================

    def save(self, metadata: ImageMetadata, *, overwrite_curation: bool = False) -> None:
        with self.lock, self.connection:
            self._upsert(metadata, overwrite_curation=overwrite_curation)

    def save_many(self, items: Sequence[ImageMetadata]) -> None:
        with self.lock, self.connection:
            for metadata in items:
                self._upsert(metadata)

    def _upsert(self, metadata: ImageMetadata, *, overwrite_curation: bool = False) -> None:
        """Record the Asset and the File it was read from. Must run inside a transaction.

        An existing Asset keeps its curation unless ``overwrite_curation`` is set, so
        re-extracting a photo never erases the user's decisions (ADR-003 R2); a new one
        is stored with the curation the record arrives with. If the path held other
        content before (the file was edited), the File now points at this Asset and the
        old Asset's curation is merged in: moved when no other File still holds the old
        content (the old Asset is then deleted), copied when one does.
        """
        now = utc_now_naive().isoformat()
        file_hash = metadata.file_hash
        asset_existed = self._asset_exists(file_hash)
        asset = _asset_row(metadata, now)
        update_clause = ", ".join(
            f"{col}=excluded.{col}" for col in _ASSET_COLUMNS if col != "file_hash"
        )
        self.connection.execute(
            f"""
            INSERT INTO assets ({", ".join(_ASSET_COLUMNS)})
            VALUES ({", ".join("?" for _ in _ASSET_COLUMNS)})
            ON CONFLICT(file_hash) DO UPDATE SET {update_clause}
            """,
            [asset[col] for col in _ASSET_COLUMNS],
        )
        if not asset_existed or overwrite_curation:
            self._write_curation(
                file_hash,
                Curation(
                    # A rating already poisoned upstream (e.g. a legacy JSON import) must
                    # not trip the CHECK constraint and abort the whole write.
                    rating=metadata.rating if is_valid_rating(metadata.rating) else None,
                    flagged=metadata.flagged,
                    labels=tuple(merge_labels([], list(metadata.labels))),
                ),
                added_at=metadata.added_at.isoformat(),
            )

        info = metadata.file_info
        previous = self.connection.execute(
            "SELECT asset_hash FROM files WHERE path = ?", (info.path,)
        ).fetchone()
        self.connection.execute(
            """
            INSERT INTO files (asset_hash, path, name, size_bytes, mtime, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET asset_hash=excluded.asset_hash,
                name=excluded.name, size_bytes=excluded.size_bytes, mtime=excluded.mtime,
                last_seen=excluded.last_seen
            """,
            (
                file_hash,
                info.path,
                info.name,
                info.size_bytes,
                info.modified_time.isoformat() if info.modified_time else None,
                now,
                now,
            ),
        )
        if previous is not None and previous["asset_hash"] != file_hash:
            self._carry_over(previous["asset_hash"], file_hash, adopt_added_at=not asset_existed)

    def _carry_over(self, old_hash: str, new_hash: str, *, adopt_added_at: bool) -> None:
        """Merge ``old_hash``'s curation into ``new_hash``; drop the old Asset if unused.

        The edited file's own curation comes first, then whatever the new content already
        had (the rule from before ADR-003 R3).
        """
        old = self._stored_curation(old_hash)
        if old is not None:
            new = self._stored_curation(new_hash)
            merged = old.curation if new is None else merge_curation(old.curation, new.curation)
            # Content that replaced an edited file was still added when first indexed.
            added_at = old.added_at if adopt_added_at or new is None else new.added_at
            self._write_curation(new_hash, merged, added_at=added_at)
        still_held = self.connection.execute(
            "SELECT 1 FROM files WHERE asset_hash = ? LIMIT 1", (old_hash,)
        ).fetchone()
        if still_held is not None:
            return  # copied: another File still holds the old content, which keeps it all
        # Moved: the new content takes the old one's place (same rowid) in each collection;
        # OR IGNORE skips collections already holding it, and the delete drops the rest.
        self.connection.execute(
            "UPDATE OR IGNORE collection_photos SET file_hash = ? WHERE file_hash = ?",
            (new_hash, old_hash),
        )
        self.connection.execute("DELETE FROM assets WHERE file_hash = ?", (old_hash,))

    def _stored_curation(self, file_hash: str) -> _StoredCuration | None:
        row = self.connection.execute(
            "SELECT rating, flagged, added_at FROM curation WHERE asset_hash = ?", (file_hash,)
        ).fetchone()
        if row is None:
            return None
        labels = tuple(self._labels_for([file_hash]).get(file_hash, []))
        return _StoredCuration(
            Curation(rating=row["rating"], flagged=bool(row["flagged"]), labels=labels),
            row["added_at"],
        )

    def _write_curation(self, file_hash: str, curation: Curation, *, added_at: str) -> None:
        self.connection.execute(
            """
            INSERT INTO curation (asset_hash, rating, flagged, added_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(asset_hash) DO UPDATE SET rating=excluded.rating,
                flagged=excluded.flagged, added_at=excluded.added_at
            """,
            (file_hash, curation.rating, int(curation.flagged), added_at),
        )
        self.connection.execute("DELETE FROM asset_labels WHERE asset_hash = ?", (file_hash,))
        for label in curation.labels:
            self.connection.execute(
                "INSERT OR IGNORE INTO asset_labels (asset_hash, label) VALUES (?, ?)",
                (file_hash, label),
            )

    def _asset_exists(self, file_hash: str) -> bool:
        return (
            self.connection.execute(
                "SELECT 1 FROM assets WHERE file_hash = ?", (file_hash,)
            ).fetchone()
            is not None
        )

    def refresh_fingerprints(self, updates: Sequence[tuple[str, int, datetime]]) -> int:
        now = utc_now_naive().isoformat()
        with self.lock, self.connection:
            touched = 0
            for path, size, mtime in updates:
                cur = self.connection.execute(
                    "UPDATE files SET size_bytes = ?, mtime = ?, last_seen = ? WHERE path = ?",
                    (size, mtime.isoformat(), now, path),
                )
                touched += cur.rowcount
            return touched

    # =========================================================================
    # Reads
    # =========================================================================

    def get_by_filehash(self, file_hash: str) -> ImageMetadata | None:
        with self.lock:
            row = self.connection.execute(
                "SELECT * FROM photo_view WHERE file_hash = ?", (file_hash,)
            ).fetchone()
            if row is None:
                return None
            return _from_row(row, self._labels_for([file_hash]).get(file_hash, []))

    def get_by_path(self, file_path: str) -> ImageMetadata | None:
        found = self.find_by_paths([file_path])
        return found[0] if found else None

    def list_all(self) -> list[ImageMetadata]:
        with self.lock:
            rows = self.connection.execute("SELECT * FROM photo_view").fetchall()
            labels_by_hash = self._labels_for([r["file_hash"] for r in rows])
            return [_from_row(r, labels_by_hash.get(r["file_hash"], [])) for r in rows]

    def list_files(self) -> list[StoredFile]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT path, asset_hash, size_bytes, mtime FROM files ORDER BY id"
            ).fetchall()
        return [
            StoredFile(
                path=r["path"],
                file_hash=r["asset_hash"],
                size_bytes=r["size_bytes"],
                modified_time=_mtime(r["mtime"]),
            )
            for r in rows
        ]

    def delete(self, file_hash: str) -> bool:
        with self.lock, self.connection:
            cur = self.connection.execute("DELETE FROM assets WHERE file_hash = ?", (file_hash,))
            return cur.rowcount > 0

    def delete_by_path(self, file_path: str) -> bool:
        """Forget one File; its Asset goes too once no File holds it."""
        with self.lock, self.connection:
            row = self.connection.execute(
                "SELECT asset_hash FROM files WHERE path = ?", (file_path,)
            ).fetchone()
            if row is None:
                return False
            self.connection.execute("DELETE FROM files WHERE path = ?", (file_path,))
            self.connection.execute(
                "DELETE FROM assets WHERE file_hash = ? "
                "AND NOT EXISTS (SELECT 1 FROM files WHERE asset_hash = ?)",
                (row["asset_hash"], row["asset_hash"]),
            )
            return True

    def batch_delete(self, file_hashes: Sequence[str]) -> int:
        if not file_hashes:
            return 0
        with self.lock, self.connection:
            placeholders = ", ".join("?" for _ in file_hashes)
            cur = self.connection.execute(
                f"DELETE FROM assets WHERE file_hash IN ({placeholders})",
                list(file_hashes),
            )
            return cur.rowcount

    def find_by_paths(self, paths: list[str]) -> list[ImageMetadata]:
        """The photo held at each known path, with that path as its ``file_info``."""
        if not paths:
            return []
        with self.lock:
            placeholders = ", ".join("?" for _ in paths)
            rows = self.connection.execute(
                "SELECT v.*, f.path AS file_path, f.name AS file_name, "
                "f.size_bytes AS file_size, f.mtime AS file_mtime "
                "FROM files f JOIN photo_view v ON v.file_hash = f.asset_hash "
                f"WHERE f.path IN ({placeholders})",
                paths,
            ).fetchall()
            labels_by_hash = self._labels_for([r["file_hash"] for r in rows])
        found = []
        for r in rows:
            record = _from_row(r, labels_by_hash.get(r["file_hash"], []))
            file_info = replace(
                record.file_info,
                path=r["file_path"],
                name=r["file_name"],
                size_bytes=r["file_size"],
                modified_time=_mtime(r["file_mtime"]),
            )
            found.append(replace(record, file_info=file_info))
        return found

    def count(self) -> int:
        with self.lock:
            return int(self.connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0])

    def _labels_for(self, file_hashes: Sequence[str]) -> dict[str, list[str]]:
        if not file_hashes:
            return {}
        placeholders = ", ".join("?" for _ in file_hashes)
        rows = self.connection.execute(
            f"SELECT asset_hash, label FROM asset_labels WHERE asset_hash IN ({placeholders}) "
            "ORDER BY rowid",
            list(file_hashes),
        ).fetchall()
        result: dict[str, list[str]] = {}
        for row in rows:
            result.setdefault(row["asset_hash"], []).append(row["label"])
        return result

    # =========================================================================
    # Search, paging and facets
    # =========================================================================

    def query(self, query: SearchQuery) -> Page[ImageMetadata]:
        """Filter, sort and page on Assets; read full rows only for the page returned."""
        where_sql, params = search_where(query)
        source = search_source(query)
        order_sql = self._order_by_sql(query.sort_by, query.sort_order)

        with self.lock:
            if (
                query.location_lat is not None
                and query.location_lon is not None
                and (query.radius_km is not None)
            ):
                # No trig functions in stock SQLite: filter by distance in Python, over
                # the rows that already passed every other filter.
                located = self.connection.execute(
                    f"SELECT file_hash, gps_lat, gps_lon FROM {source} {where_sql} "
                    f"ORDER BY {order_sql}",
                    params,
                ).fetchall()
                matched = [
                    r["file_hash"]
                    for r in located
                    if r["gps_lat"] is not None
                    and r["gps_lon"] is not None
                    and haversine_distance_km(
                        query.location_lat, query.location_lon, r["gps_lat"], r["gps_lon"]
                    )
                    <= query.radius_km
                ]
                page_of_hashes = _paginate(matched, query.page, query.page_size)
                return replace(page_of_hashes, items=self._photos_in_order(page_of_hashes.items))

            total_count = self.connection.execute(
                f"SELECT COUNT(*) FROM {source} {where_sql}", params
            ).fetchone()[0]
            page_size = max(1, query.page_size)
            total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1
            page = max(1, min(query.page, total_pages))
            offset = (page - 1) * page_size

            hashes = [
                r[0]
                for r in self.connection.execute(
                    f"SELECT file_hash FROM {source} {where_sql} ORDER BY {order_sql} "
                    "LIMIT ? OFFSET ?",
                    [*params, page_size, offset],
                )
            ]
            return Page(
                items=self._photos_in_order(hashes),
                total_count=total_count,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
            )

    def _photos_in_order(self, hashes: Sequence[str]) -> list[ImageMetadata]:
        """The photos for ``hashes``, in that order. Caller holds the lock."""
        if not hashes:
            return []
        placeholders = ", ".join("?" for _ in hashes)
        rows = {
            r["file_hash"]: r
            for r in self.connection.execute(
                f"SELECT * FROM photo_view WHERE file_hash IN ({placeholders})", list(hashes)
            )
        }
        labels_by_hash = self._labels_for(list(rows))
        return [_from_row(rows[h], labels_by_hash.get(h, [])) for h in hashes if h in rows]

    @staticmethod
    def _order_by_sql(sort_by: str, sort_order: str) -> str:
        direction = "DESC" if sort_order.lower() == "desc" else "ASC"
        column = {
            "size_bytes": "size_bytes",
            "camera_model": "COALESCE(camera_model, '')",
            # The primary file's name: the only sort key that lives on ``files``.
            "file_name": (
                "(SELECT name FROM files WHERE asset_hash = file_hash "
                "ORDER BY last_seen DESC, id LIMIT 1)"
            ),
        }.get(sort_by, "captured_at")
        # file_hash breaks ties, so paging through equal keys never repeats or skips a row.
        if column == "captured_at":
            # Unknown capture dates (PMO-24) go last in either direction.
            return f"captured_at IS NULL, captured_at {direction}, file_hash"
        return f"{column} {direction}, file_hash"

    def geo_clusters(
        self, query: SearchQuery, bbox: BoundingBox | None, cell_degrees: float
    ) -> list[GeoCluster]:
        where_sql, params = search_where(query)
        source = search_source(query)
        located = "gps_lat IS NOT NULL AND gps_lon IS NOT NULL"
        where_sql = f"{where_sql} AND {located}" if where_sql else f"WHERE {located}"
        if bbox is not None:
            clause, bbox_params = _bbox_sql(bbox)
            where_sql += f" AND {clause}"
            params.extend(bbox_params)
        # Shifted to be positive, so CAST truncation is floor. The bare file_hash comes from
        # the row holding MAX(captured_at): the cluster's most recent photo.
        sql = (
            "SELECT AVG(gps_lat) AS lat, AVG(gps_lon) AS lon, COUNT(*) AS n, file_hash, "
            f"MAX(COALESCE(captured_at, '')) AS newest FROM {source} "
            f"{where_sql} "
            "GROUP BY CAST((gps_lat + 90.0) / ? AS INTEGER), "
            "CAST((gps_lon + 180.0) / ? AS INTEGER) "
            "ORDER BY n DESC, file_hash"
        )
        with self.lock:
            rows = self.connection.execute(sql, [*params, cell_degrees, cell_degrees]).fetchall()
        return [
            GeoCluster(
                latitude=r["lat"],
                longitude=r["lon"],
                count=r["n"],
                representative_hash=r["file_hash"],
            )
            for r in rows
        ]

    def facets(self) -> Facets:
        with self.lock:
            camera_rows = self.connection.execute(
                "SELECT camera_make AS name, COUNT(*) AS n FROM assets "
                "WHERE camera_make IS NOT NULL GROUP BY camera_make ORDER BY camera_make"
            ).fetchall()
            tag_rows = self.connection.execute(
                "SELECT label AS name, COUNT(*) AS n FROM asset_labels "
                "GROUP BY label ORDER BY label"
            ).fetchall()
            year_rows = self.connection.execute(
                "SELECT strftime('%Y', captured_at) AS year, COUNT(*) AS n FROM assets "
                "WHERE captured_at IS NOT NULL GROUP BY year ORDER BY year"
            ).fetchall()
            bounds_row = self.connection.execute(
                "SELECT MIN(gps_lat), MAX(gps_lat), MIN(gps_lon), MAX(gps_lon) FROM assets "
                "WHERE gps_lat IS NOT NULL"
            ).fetchone()
            iso_rows = self.connection.execute(
                "SELECT iso, COUNT(*) AS n FROM assets WHERE iso IS NOT NULL "
                "GROUP BY iso ORDER BY iso"
            ).fetchall()
            totals = self.connection.execute(
                "SELECT COUNT(*), SUM(flagged), "
                "SUM(gps_lat IS NOT NULL AND gps_lon IS NOT NULL), SUM(captured_at IS NULL), "
                "SUM(size_bytes), AVG(width * height / 1e6) FROM asset_view"
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
            isos=[FacetCount(name=str(r["iso"]), count=r["n"]) for r in iso_rows],
            stats=LibraryStats(
                total_count=totals[0],
                flagged_count=totals[1] or 0,
                geotagged_count=totals[2] or 0,
                undated_count=totals[3] or 0,
                total_bytes=totals[4] or 0,
                avg_megapixels=totals[5] or 0.0,
            ),
        )

    # =========================================================================
    # Typed curation commands
    # =========================================================================

    def apply(self, file_hash: str, command: CurationCommand) -> ImageMetadata | None:
        with self.lock, self.connection:
            if not self._asset_exists(file_hash):
                return None
            self._apply_command(file_hash, command)
        return self.get_by_filehash(file_hash)

    def apply_batch(self, file_hashes: Sequence[str], command: CurationCommand) -> int:
        count = 0
        with self.lock, self.connection:
            for file_hash in file_hashes:
                if not self._asset_exists(file_hash):
                    continue
                self._apply_command(file_hash, command)
                count += 1
        return count

    def _apply_command(self, file_hash: str, command: CurationCommand) -> None:
        """Mutate the curation of ``file_hash``. Must run inside an open transaction."""
        if isinstance(command, SetRating):
            self.connection.execute(
                "UPDATE curation SET rating = ? WHERE asset_hash = ?",
                (command.value, file_hash),
            )
        elif isinstance(command, SetFlag):
            self.connection.execute(
                "UPDATE curation SET flagged = ? WHERE asset_hash = ?",
                (1 if command.value else 0, file_hash),
            )
        elif isinstance(command, AddTag):
            self.connection.execute(
                "INSERT OR IGNORE INTO asset_labels (asset_hash, label) VALUES (?, ?)",
                (file_hash, command.value),
            )
        elif isinstance(command, RemoveTag):
            self.connection.execute(
                "DELETE FROM asset_labels WHERE asset_hash = ? AND label = ?",
                (file_hash, command.value),
            )
        elif isinstance(command, SetLabels):
            self.connection.execute("DELETE FROM asset_labels WHERE asset_hash = ?", (file_hash,))
            for label in merge_labels([], list(command.value)):
                self.connection.execute(
                    "INSERT OR IGNORE INTO asset_labels (asset_hash, label) VALUES (?, ?)",
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
            if not self._asset_exists(file_hash):
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
            command = AddTag(str(value))
        elif action == "remove_tag":
            command = RemoveTag(str(value))
        elif action == "set_rating":
            command = SetRating(value)
        else:
            command = SetFlag(bool(value))
        return self.apply_batch(file_hashes, command)


def search_source(query: SearchQuery) -> str:
    """The table :func:`search_where` filters: ``assets``, joined to curation only if needed."""
    return "asset_view" if query.rating is not None or query.flagged is not None else "assets"


def search_where(query: SearchQuery) -> tuple[str, list[Any]]:
    """The ``WHERE`` clause (or ``""``) and its parameters for the SQL-expressible filters."""
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
    if query.camera_makes:
        placeholders = ", ".join("?" for _ in query.camera_makes)
        clauses.append(f"camera_make IN ({placeholders})")
        params.extend(query.camera_makes)
    if query.has_capture_date is not None:
        clauses.append(
            "captured_at IS NOT NULL" if query.has_capture_date else "captured_at IS NULL"
        )
    if query.has_location is not None:
        located = "gps_lat IS NOT NULL AND gps_lon IS NOT NULL"
        clauses.append(located if query.has_location else f"NOT ({located})")
    if query.within is not None:
        clause, bbox_params = _bbox_sql(query.within)
        clauses.append(clause)
        params.extend(bbox_params)
    if query.collection is not None:
        clauses.append(
            "file_hash IN (SELECT file_hash FROM collection_photos WHERE collection = ?)"
        )
        params.append(query.collection)
    if query.ai_tag is not None:
        clauses.append(
            "file_hash IN (SELECT file_hash FROM photo_ai_tags WHERE label = ? "
            "AND status = 'suggested')"
        )
        params.append(query.ai_tag)
    if query.rating is not None:
        clauses.append("rating = ?")
        params.append(query.rating)
    if query.flagged is not None:
        clauses.append("flagged = ?")
        params.append(1 if query.flagged else 0)
    if query.tags:
        placeholders = ", ".join("?" for _ in query.tags)
        clauses.append(
            f"file_hash IN (SELECT asset_hash FROM asset_labels WHERE label IN "
            f"({placeholders}) GROUP BY asset_hash HAVING COUNT(DISTINCT label) = ?)"
        )
        params.extend(query.tags)
        params.append(len(set(query.tags)))
    if query.search_term:
        term = f"%{_escape_like(query.search_term)}%"
        clauses.append(
            "(file_hash IN (SELECT asset_hash FROM files WHERE name LIKE ? ESCAPE '\\' "
            "OR path LIKE ? ESCAPE '\\') OR "
            "camera_make LIKE ? ESCAPE '\\' OR camera_model LIKE ? ESCAPE '\\' OR "
            "file_hash IN (SELECT asset_hash FROM asset_labels WHERE label LIKE ? ESCAPE '\\'))"
        )
        params.extend([term, term, term, term, term])

    return (f"WHERE {' AND '.join(clauses)}" if clauses else ""), params


def _bbox_sql(bbox: BoundingBox) -> tuple[str, list[float]]:
    """SQL condition and parameters selecting the rows inside a map area."""
    if bbox.west <= bbox.east:
        lon = "gps_lon BETWEEN ? AND ?"
    else:  # the area crosses the antimeridian
        lon = "(gps_lon >= ? OR gps_lon <= ?)"
    return (
        f"(gps_lat BETWEEN ? AND ? AND {lon})",
        [bbox.south, bbox.north, bbox.west, bbox.east],
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _paginate(items: list[T], page: int, page_size: int) -> Page[T]:
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


def _asset_row(metadata: ImageMetadata, extracted_at: str) -> dict[str, Any]:
    exif = metadata.exif
    location = exif.location
    return {
        "file_hash": metadata.file_hash,
        "size_bytes": metadata.file_info.size_bytes,
        "mime_type": metadata.file_info.mime_type,
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
        "extracted_at": extracted_at,
    }


def _mtime(value: str | None) -> datetime | None:
    return to_naive(datetime.fromisoformat(value)) if value else None


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
        modified_time=_mtime(row["mtime"]),
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
