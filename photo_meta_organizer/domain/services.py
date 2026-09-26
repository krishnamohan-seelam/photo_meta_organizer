"""Domain services for image metadata processing.

This module contains domain services that encapsulate business logic
which doesn't naturally belong to a single entity or value object.

Domain services are:
- Stateless (no internal state between calls)
- Depend only on domain models (no infrastructure dependencies)
- Contain business rules expressed in domain language
"""

import logging
import ntpath
import posixpath
from collections.abc import Callable

from photo_meta_organizer.domain.models import CameraProfile, FileInfo, FileState, ImageMetadata


class CameraClassifier:
    """Domain service for classifying camera types from extracted metadata.

    Camera profile classification is domain knowledge that determines
    recovery strategies and downstream behavior (e.g., which fields to
    expect as populated vs. gracefully missing).

    The classification uses make, model, and available field metadata
    to infer the camera profile. This is a pure domain decision — no
    infrastructure dependencies.
    """

    # Camera make patterns (all uppercase for case-insensitive matching)
    MOBILE_MAKES = {
        "APPLE", "SAMSUNG", "XIAOMI", "HUAWEI",
        "GOOGLE", "ONEPLUS", "OPPO", "VIVO",
    }
    DSLR_MAKES = {"SONY", "CANON", "NIKON", "PENTAX", "FUJIFILM"}
    ACTION_CAM_MAKES = {"GOPRO", "DJI", "INSTA360"}
    MIRRORLESS_PATTERNS = {
        "EOS R", "Z5", "Z6", "Z7", "Z8", "Z9",
        "A7", "A6", "S5", "S1", "X-T", "X-H",
    }

    @staticmethod
    def classify(
        camera_make: str | None,
        camera_model: str | None,
        has_lens_model: bool = False,
    ) -> CameraProfile:
        """Infer camera profile from make, model, and available field data.

        Args:
            camera_make: Camera manufacturer string (case-insensitive).
            camera_model: Camera model string (case-insensitive).
            has_lens_model: Whether EXIF LensModel tag was present.

        Returns:
            Best-guess CameraProfile enum value. Returns UNKNOWN
            when insufficient data is available.
        """
        if not camera_make:
            return CameraProfile.UNKNOWN

        make_upper = camera_make.strip().upper()
        model_upper = (camera_model or "").strip().upper()

        if make_upper in CameraClassifier.MOBILE_MAKES:
            return CameraProfile.MOBILE

        if make_upper in CameraClassifier.ACTION_CAM_MAKES:
            return CameraProfile.ACTION_CAM

        if "SCANNER" in model_upper or "FILM" in model_upper:
            return CameraProfile.FILM_SCANNER

        if any(
            pattern in model_upper
            for pattern in CameraClassifier.MIRRORLESS_PATTERNS
        ):
            return CameraProfile.MIRRORLESS

        if make_upper in CameraClassifier.DSLR_MAKES and has_lens_model:
            return CameraProfile.DSLR

        if make_upper in CameraClassifier.DSLR_MAKES:
            # Modern cameras from these brands without explicit detection
            return CameraProfile.MIRRORLESS

        return CameraProfile.UNKNOWN


logger = logging.getLogger(__name__)


def _lexical_normpath(path: str) -> str:
    """Normalise a path without touching the filesystem (Windows or POSIX style)."""
    if "\\" in path or ntpath.splitdrive(path)[0]:
        return ntpath.normpath(path)
    return posixpath.normpath(path)


class MetadataStateAnalyzer:
    """Domain service: compares disk state vs. DB to classify file changes.

    Implements the **Hybrid fingerprinting** strategy (Option C from the plan):

    1. Build a (path → FileInfo) index from disk files.
    2. Build a (path → ImageMetadata) index from DB entries.
    3. For each disk file:
       - Not in DB → **NEW**.
       - In DB, AND (size, mtime) match stored values → **UNCHANGED** (no hash).
       - In DB, but (size OR mtime) differ → compute SHA-256 → compare:
           • Same hash → **UNCHANGED** (content unchanged despite stat diff).
           • Different hash → **MODIFIED**.
       - Legacy record with no stored mtime and an equal size → **UNCHANGED**
         without hashing, flagged ``refresh_fingerprint`` so the caller can backfill
         it (a whole library is not re-hashed just because it predates mtimes).
       - ``force_rehash=True`` hashes every file already in the DB, ignoring the
         fingerprint; this is the only way to catch an edit that kept both size
         and mtime.
    4. DB entries whose path is not on disk → **DELETED**.

    This is a pure domain service: no I/O, fully testable. The caller injects
    both the hasher (it opens files, e.g. through the retriever) and the path
    normaliser (e.g. one that resolves symlinks and on-disk case). NEW files are
    not hashed here: extraction hashes them anyway, so each is read once (PMO-22).
    """

    def analyze_changes(
        self,
        disk_files: dict[str, FileInfo],
        db_entries: list[ImageMetadata],
        compute_hash: Callable[[str], str] | None = None,
        force_rehash: bool = False,
        normalise_path: Callable[[str], str] | None = None,
    ) -> list[FileState]:
        """Classify every file as NEW / MODIFIED / UNCHANGED / DELETED.

        Args:
            disk_files: Mapping of normalised path → FileInfo from disk scan.
            db_entries: All ImageMetadata records currently in the DB.
            compute_hash: Callable that accepts a (normalised) file path and returns
                its SHA-256 hex digest. Required as soon as a file must be hashed;
                a ``ValueError`` is raised if it is missing then.
            force_rehash: Hash every file that is already in the DB instead of
                trusting the (size, mtime) fingerprint.
            normalise_path: Maps a path to the form both sides are compared in.
                Defaults to a purely lexical ``normpath``.

        Returns:
            List of FileState objects covering every disk file and every
            DB-only (deleted) entry.
        """
        normalise = normalise_path or _lexical_normpath

        def hash_of(path: str) -> str:
            if compute_hash is None:
                raise ValueError("compute_hash is required to confirm a changed file")
            return compute_hash(path)

        # Index DB entries by normalised path
        db_by_path: dict[str, ImageMetadata] = {
            normalise(entry.file_info.path): entry for entry in db_entries
        }

        # Normalise disk paths for consistent comparison
        normalised_disk: dict[str, FileInfo] = {
            normalise(fi.path): fi for fi in disk_files.values()
        }

        states: list[FileState] = []

        # ---------------------------------------------------------------
        # Pass 1: process all disk files
        # ---------------------------------------------------------------
        for norm_path, fi in normalised_disk.items():
            db_entry = db_by_path.get(norm_path)

            if db_entry is None:
                # File not in DB → NEW. Not hashed here: extraction hashes it.
                states.append(
                    FileState(
                        file_path=norm_path,
                        state="NEW",
                        file_hash=None,
                        size_bytes=fi.size_bytes,
                        last_modified=fi.modified_time,
                    )
                )
                continue

            # File is in DB — try fast fingerprint check first
            stored_size = db_entry.file_info.size_bytes
            stored_hash = db_entry.file_hash
            stored_mtime = db_entry.file_info.modified_time

            size_same = fi.size_bytes == stored_size
            mtime_known = stored_mtime is not None
            mtime_same = mtime_known and fi.modified_time == stored_mtime

            if not force_rehash and size_same and (mtime_same or not mtime_known):
                # Fingerprint matches (or is a legacy record we trust on size alone).
                states.append(
                    FileState(
                        file_path=norm_path,
                        state="UNCHANGED",
                        file_hash=stored_hash,
                        size_bytes=fi.size_bytes,
                        last_modified=fi.modified_time,
                        refresh_fingerprint=not mtime_known,
                    )
                )
                continue

            # Size or mtime differs (or a rehash was forced) → hash to confirm
            try:
                current_hash = hash_of(norm_path)
            except OSError as exc:
                logger.warning("Cannot hash file %s: %s", norm_path, exc)
                continue

            if current_hash == stored_hash:
                # Stat changed but content is identical (touch, copy, metadata-only
                # edit): keep the record, but let the caller record the new stat.
                states.append(
                    FileState(
                        file_path=norm_path,
                        state="UNCHANGED",
                        file_hash=current_hash,
                        size_bytes=fi.size_bytes,
                        last_modified=fi.modified_time,
                        refresh_fingerprint=not (mtime_same and size_same),
                    )
                )
            else:
                states.append(
                    FileState(
                        file_path=norm_path,
                        state="MODIFIED",
                        file_hash=current_hash,
                        size_bytes=fi.size_bytes,
                        last_modified=fi.modified_time,
                        previous_hash=stored_hash,
                    )
                )

        # ---------------------------------------------------------------
        # Pass 2: find DELETED entries (in DB but not on disk)
        # ---------------------------------------------------------------
        disk_path_set = set(normalised_disk.keys())
        for norm_path, db_entry in db_by_path.items():
            if norm_path not in disk_path_set:
                states.append(
                    FileState(
                        file_path=norm_path,
                        state="DELETED",
                        file_hash=db_entry.file_hash,
                    )
                )

        return states
