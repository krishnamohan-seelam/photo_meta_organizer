"""Each kind of job's work, built from the parameters stored with the job (ADR-003 R5a).

The routes that start a job and ``POST /api/jobs/{id}/resume`` both go through
:func:`work_for`, so a resumed job runs exactly as it was started. Resuming is cheap
because the work is idempotent: a scan skips files it already has unchanged, and an
analysis takes only photos without an embedding (a ``reanalyze`` redoes everything).
"""

from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException

from photo_meta_organizer.api.dependencies import Services
from photo_meta_organizer.application.composition import build_scan
from photo_meta_organizer.application.job_work import ScanJobKind, analyze_work, scan_work
from photo_meta_organizer.application.jobs import JobContext, JobOutcome, Work
from photo_meta_organizer.application.use_cases.analyze_photos_use_case import (
    AnalyzePhotosUseCase,
)
from photo_meta_organizer.application.use_cases.scan_library import ScanOptions
from photo_meta_organizer.infrastructure.analysis import runtime
from photo_meta_organizer.infrastructure.analysis.model_store import DownloadCancelled, ModelStore

RUNTIME_HINT = (
    "The AI features need the optional 'ai' extra (onnxruntime and tokenizers): "
    "`uv sync --extra ai`, or `pip install photo-meta-organizer[ai]`."
)


def work_for(kind: str, folder_path: str, params: Mapping[str, Any], services: Services) -> Work:
    """The work of a ``kind`` job on ``folder_path`` with ``params``.

    Raises:
        HTTPException: 503 without the AI extra, 409 when the AI model's state does not
            allow the job, 400 for a kind this version does not know.
    """
    if kind in ("index", "sync"):
        scan_kind: ScanJobKind = "index" if kind == "index" else "sync"
        scan = build_scan(folder_path, services.repository)
        return scan_work(scan, folder_path, ScanOptions(**params), kind=scan_kind)
    if kind == "analyze":
        require_runtime()
        require_model(services)
        tagger = services.tagger if (params.get("tags", True) or params.get("retag")) else None
        use_case = AnalyzePhotosUseCase(services.analysis, services.embedder, tagger)
        return analyze_work(
            use_case,
            reanalyze=bool(params.get("reanalyze", False)),
            limit=params.get("limit"),
            retag=bool(params.get("retag", False)),
        )
    if kind == "model-download":
        if services.model_store.is_installed():
            raise HTTPException(status_code=409, detail="The model is already installed.")
        return download_work(services.model_store)
    raise HTTPException(status_code=400, detail=f"Jobs of kind '{kind}' cannot be run.")


def require_runtime() -> None:
    """Raise 503 unless the optional ``ai`` extra (onnxruntime, tokenizers) is installed."""
    if not runtime.ai_runtime_installed():
        raise HTTPException(status_code=503, detail=RUNTIME_HINT)


def require_model(services: Services) -> None:
    """Raise 409 unless the AI model has been downloaded."""
    if not services.model_store.is_installed():
        raise HTTPException(
            status_code=409,
            detail="The AI model is not installed yet. Download it first "
            "(POST /api/analysis/model/download).",
        )


def download_work(store: ModelStore) -> Work:
    """Work that downloads the model, reporting bytes done out of the total."""

    def work(ctx: JobContext) -> JobOutcome:
        def on_progress(done: int, total: int) -> None:
            ctx.report_progress(total=total, processed=done, failed=0)

        try:
            store.download(progress=on_progress, should_cancel=ctx.cancel_requested)
        except DownloadCancelled:
            return JobOutcome(
                message="Download cancelled; nothing partial was kept.", cancelled=True
            )
        return JobOutcome(
            message=f"Installed the model ({store.manifest.total_bytes / 1e6:.0f} MB).",
            counts={"bytes": store.manifest.total_bytes},
        )

    return work
