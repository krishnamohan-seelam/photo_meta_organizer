"""Where the AI model lives on disk, and the one place that downloads it.

Nothing is fetched unless a caller asks (`download`), and callers ask only after the user has
agreed. Each file is streamed to a ``.part`` file, checked against the manifest's size and SHA-256,
and only then renamed into place, so a half-finished or tampered download is never loaded and an
interrupted one leaves no file that looks complete.
"""

import hashlib
import logging
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from photo_meta_organizer.infrastructure.analysis.model_manifest import ModelFile, ModelManifest

logger = logging.getLogger(__name__)

_CHUNK = 1024 * 1024
_ALLOWED_SCHEMES = ("https", "file")  # file: only for tests that serve from a temp directory


class ModelUnavailableError(RuntimeError):
    """The model is not installed, or could not be downloaded or verified."""


class DownloadCancelled(Exception):
    """The caller asked the download to stop."""


class ModelStore:
    def __init__(self, root: Path, manifest: ModelManifest) -> None:
        self.manifest = manifest
        self.directory = Path(root) / manifest.model_id

    def path(self, name: str) -> Path:
        return self.directory / name

    # ---- status

    def _is_present(self, f: ModelFile) -> bool:
        p = self.path(f.name)
        return p.is_file() and p.stat().st_size == f.size

    def missing_files(self) -> list[ModelFile]:
        return [f for f in self.manifest.files if not self._is_present(f)]

    def missing_bytes(self) -> int:
        return sum(f.size for f in self.missing_files())

    def is_installed(self) -> bool:
        return not self.missing_files()

    def require_installed(self) -> None:
        if not self.is_installed():
            raise ModelUnavailableError(
                "The AI model is not installed "
                f"({self.missing_bytes() / 1e6:.0f} MB to download). "
                "Run `python -m photo_meta_organizer.main analyze --download` to install it."
            )

    # ---- download

    def download(
        self,
        progress: Callable[[int, int], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> None:
        """Fetch every missing file. ``progress(done_bytes, total_bytes)`` covers the whole model.

        Raises :class:`ModelUnavailableError` (unreachable, wrong size or checksum) or
        :class:`DownloadCancelled`; in either case nothing partial is left behind.
        """
        total = self.manifest.total_bytes
        done = total - self.missing_bytes()
        self.directory.mkdir(parents=True, exist_ok=True)
        for f in self.missing_files():
            if should_cancel and should_cancel():
                raise DownloadCancelled()
            done = self._fetch(f, done, total, progress, should_cancel)
        if progress:
            progress(total, total)

    def _fetch(
        self,
        f: ModelFile,
        done: int,
        total: int,
        progress: Callable[[int, int], None] | None,
        should_cancel: Callable[[], bool] | None,
    ) -> int:
        if urlparse(f.url).scheme not in _ALLOWED_SCHEMES:
            raise ModelUnavailableError(f"refusing to download {f.name} from {f.url!r}")
        target = self.path(f.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        digest = hashlib.sha256()
        received = 0
        logger.info("Downloading %s (%.0f MB)", f.name, f.size / 1e6)
        try:
            request = urllib.request.Request(f.url, headers={"User-Agent": "photo-meta-organizer"})
            with (
                urllib.request.urlopen(request, timeout=30) as response,
                part.open("wb") as out,
            ):  # noqa: S310
                while chunk := response.read(_CHUNK):
                    if should_cancel and should_cancel():
                        raise DownloadCancelled()
                    out.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
                    if progress:
                        progress(done + received, total)
            if received != f.size or digest.hexdigest() != f.sha256:
                raise ModelUnavailableError(
                    f"{f.name} failed its checksum (got {received} bytes); "
                    "the download was discarded."
                )
            os.replace(part, target)
        except (urllib.error.URLError, OSError) as err:
            raise ModelUnavailableError(f"Could not download {f.name}: {err}") from err
        finally:
            part.unlink(missing_ok=True)
        return done + received
