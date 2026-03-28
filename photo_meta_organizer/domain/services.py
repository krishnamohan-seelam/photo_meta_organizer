"""Domain services for image metadata processing.

This module contains domain services that encapsulate business logic
which doesn't naturally belong to a single entity or value object.

Domain services are:
- Stateless (no internal state between calls)
- Depend only on domain models (no infrastructure dependencies)
- Contain business rules expressed in domain language
"""

import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional

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
        camera_make: Optional[str],
        camera_model: Optional[str],
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
    4. DB entries whose path is not on disk → **DELETED**.

    This is a pure domain service: no I/O, fully testable.
    The caller is responsible for computing hashes when requested
    (injected as a callable so the service stays dependency-free).
    """

    def analyze_changes(
        self,
        disk_files: Dict[str, FileInfo],
        db_entries: List[ImageMetadata],
        compute_hash: Optional[callable] = None,
    ) -> List[FileState]:
        """Classify every file as NEW / MODIFIED / UNCHANGED / DELETED.

        Args:
            disk_files: Mapping of normalised path → FileInfo from disk scan.
            db_entries: All ImageMetadata records currently in the DB.
            compute_hash: Callable that accepts a file path (str) and returns
                its SHA-256 hex digest.  Defaults to the built-in SHA-256
                implementation when None.

        Returns:
            List of FileState objects covering every disk file and every
            DB-only (deleted) entry.
        """
        if compute_hash is None:
            compute_hash = self._sha256

        # Index DB entries by normalised path
        db_by_path: Dict[str, ImageMetadata] = {
            str(Path(entry.file_info.path).resolve()): entry
            for entry in db_entries
        }

        # Normalise disk paths for consistent comparison
        normalised_disk: Dict[str, FileInfo] = {
            str(Path(fi.path).resolve()): fi for fi in disk_files.values()
        }

        states: List[FileState] = []

        # ---------------------------------------------------------------
        # Pass 1: process all disk files
        # ---------------------------------------------------------------
        for norm_path, fi in normalised_disk.items():
            db_entry = db_by_path.get(norm_path)

            if db_entry is None:
                # File not in DB → NEW (compute hash for extraction)
                try:
                    current_hash = compute_hash(norm_path)
                except OSError as exc:
                    logger.warning("Cannot hash new file %s: %s", norm_path, exc)
                    current_hash = None
                states.append(
                    FileState(
                        file_path=norm_path,
                        state="NEW",
                        file_hash=current_hash,
                        size_bytes=fi.size_bytes,
                        last_modified=fi.modified_time,
                    )
                )
                continue

            # File is in DB — try fast fingerprint check first
            stored_size = db_entry.file_info.size_bytes
            stored_hash = db_entry.file_hash

            if fi.size_bytes == stored_size:
                # Size matches → assume UNCHANGED (skip hashing)
                states.append(
                    FileState(
                        file_path=norm_path,
                        state="UNCHANGED",
                        file_hash=stored_hash,
                        size_bytes=fi.size_bytes,
                        last_modified=fi.modified_time,
                    )
                )
                continue

            # Size differs → compute hash to confirm modification
            try:
                current_hash = compute_hash(norm_path)
            except OSError as exc:
                logger.warning("Cannot hash file %s: %s", norm_path, exc)
                continue

            if current_hash == stored_hash:
                # Sizes differ but content is identical (e.g. metadata-only edit)
                states.append(
                    FileState(
                        file_path=norm_path,
                        state="UNCHANGED",
                        file_hash=current_hash,
                        size_bytes=fi.size_bytes,
                        last_modified=fi.modified_time,
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

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sha256(file_path: str) -> str:
        """Compute SHA-256 hex digest for the file at *file_path*.

        Reads in 64 KiB chunks to avoid loading large images into RAM.

        Args:
            file_path: Absolute path to the file.

        Returns:
            Lowercase hex string of the SHA-256 digest.

        Raises:
            OSError: If the file cannot be read.
        """
        h = hashlib.sha256()
        with open(file_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
