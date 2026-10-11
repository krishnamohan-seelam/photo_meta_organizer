"""Export endpoints (PMO-28): original files as a ZIP, metadata as JSON.

Endpoints:
    POST /api/export/zip   - Stream a ZIP of the selected photos' original files
    POST /api/export/json  - Metadata of the selected photos (or the whole library)

The ZIP is streamed as it is built (entries are stored, not compressed: photos are
already compressed), so server memory stays flat however large the selection. Photos
that are not in the library or whose file is gone are skipped, counted in the
``X-Export-Skipped`` header and listed in ``export_report.txt`` inside the archive.
``X-Export-Bytes`` is the total size of the files, so a client can show progress.
"""

import io
import json
import os
import time
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePath

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse

from photo_meta_organizer.api.dependencies import get_repository
from photo_meta_organizer.api.routes.photos_router import _to_response
from photo_meta_organizer.api.schemas import ExportJsonRequest, ExportZipRequest
from photo_meta_organizer.application.interfaces.image_repository import (
    ImageMetadataRepository,
)

export_router = APIRouter(prefix="/api/export", tags=["export"])

# Upper bound on the files in one ZIP. The browser holds the download (in memory or
# spilled to disk) before saving it, so keep one export to a sane size.
MAX_ZIP_BYTES = 4 * 1024**3
_CHUNK = 1024 * 1024
REPORT_NAME = "export_report.txt"


@dataclass(frozen=True)
class _Entry:
    path: str
    arcname: str
    size: int


@export_router.post("/zip", summary="Download the selected photos as a ZIP")
def export_zip(
    request: ExportZipRequest,
    repository: ImageMetadataRepository = Depends(get_repository),
) -> StreamingResponse:
    """Stream a ZIP of the original files; unknown or missing photos are reported."""
    entries: list[_Entry] = []
    skipped: list[str] = []
    used_names: set[str] = set()
    for file_hash in dict.fromkeys(request.photo_hashes):  # de-duplicated, order kept
        metadata = repository.get_by_filehash(file_hash)
        if metadata is None:
            skipped.append(f"{file_hash}: not in the library")
            continue
        path = metadata.file_info.path
        try:
            size = os.path.getsize(path)
        except OSError:
            skipped.append(f"{path}: file is missing")
            continue
        entries.append(_Entry(path, _unique_name(metadata.file_info.name, used_names), size))

    if not entries:
        raise HTTPException(
            status_code=404,
            detail="None of the selected photos could be exported (files missing or not indexed).",
        )
    total = sum(e.size for e in entries)
    if total > MAX_ZIP_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Export too large: {total / 1024**3:.1f} GB selected, the limit is "
                f"{MAX_ZIP_BYTES / 1024**3:.0f} GB. Export fewer photos at a time."
            ),
        )

    filename = _stamp("photos") + ".zip"
    return StreamingResponse(
        _zip_stream(entries, skipped),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Export-Files": str(len(entries)),
            "X-Export-Skipped": str(len(skipped)),
            "X-Export-Bytes": str(total),
        },
    )


@export_router.post("/json", summary="Download photo metadata as JSON")
def export_json(
    request: ExportJsonRequest,
    repository: ImageMetadataRepository = Depends(get_repository),
) -> Response:
    """Metadata of the selected photos, or of the whole library when none are given."""
    if request.photo_hashes:
        found = (repository.get_by_filehash(h) for h in dict.fromkeys(request.photo_hashes))
        records = [m for m in found if m is not None]
    else:
        records = repository.list_all()
    body = json.dumps(
        [_to_response(m).model_dump(mode="json") for m in records], indent=2, ensure_ascii=False
    )
    filename = _stamp("photo-metadata") + ".json"
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _zip_stream(entries: list[_Entry], skipped: list[str]) -> Iterator[bytes]:
    """Yield the ZIP as it is written; a file that vanished meanwhile is reported."""
    sink = _Sink()
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for entry in entries:
            try:
                source = open(entry.path, "rb")
            except OSError:
                skipped.append(f"{entry.path}: file is missing")
                continue
            with source:
                info = zipfile.ZipInfo(entry.arcname, _zip_time(entry.path))
                with archive.open(info, "w", force_zip64=True) as target:
                    while chunk := source.read(_CHUNK):
                        target.write(chunk)
                        yield sink.drain()
            yield sink.drain()
        if skipped:
            lines = ["These selected photos were not exported:", "", *skipped, ""]
            archive.writestr(REPORT_NAME, "\n".join(lines))
    yield sink.drain()


class _Sink(io.RawIOBase):
    """Write-only, unseekable buffer that ``zipfile`` streams into."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[bytes] = []

    def writable(self) -> bool:
        return True

    def write(self, data: bytes | bytearray | memoryview) -> int:  # type: ignore[override]
        self._chunks.append(bytes(data))
        return len(data)

    def drain(self) -> bytes:
        data = b"".join(self._chunks)
        self._chunks.clear()
        return data


def _unique_name(name: str, used: set[str]) -> str:
    """``name``, or ``name (2)``, ``name (3)``... if an earlier entry took it (case-insensitive)."""
    stem, suffix = PurePath(name).stem, PurePath(name).suffix
    candidate, n = name, 1
    while candidate.lower() in used:
        n += 1
        candidate = f"{stem} ({n}){suffix}"
    used.add(candidate.lower())
    return candidate


def _zip_time(path: str) -> tuple[int, int, int, int, int, int]:
    try:
        stamp = time.localtime(os.path.getmtime(path))
    except OSError:
        stamp = time.localtime()
    y, mo, d, h, mi, s = stamp[:6]
    return max((y, mo, d, h, mi, s), (1980, 1, 1, 0, 0, 0))  # ZIP cannot store earlier dates


def _stamp(prefix: str) -> str:
    return f"{prefix}-{datetime.now():%Y%m%d-%H%M%S}"
