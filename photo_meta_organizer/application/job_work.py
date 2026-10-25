"""Adapters that turn use cases into ``JobManager`` work functions (PMO-18)."""

from typing import Literal

from photo_meta_organizer.application.jobs import JobContext, JobOutcome, Work
from photo_meta_organizer.application.use_cases.analyze_photos_use_case import (
    AnalyzePhotosUseCase,
    AnalyzeProgress,
)
from photo_meta_organizer.application.use_cases.scan_library import ScanLibrary, ScanOptions
from photo_meta_organizer.domain.models import SyncResult

ScanJobKind = Literal["index", "sync"]


def scan_work(
    use_case: ScanLibrary, folder_path: str, options: ScanOptions, *, kind: ScanJobKind = "sync"
) -> Work:
    """Run a scan of ``folder_path`` as a job, scoped to that folder (ADR-003 R4).

    ``kind`` only picks how the outcome is worded: ``index`` reports photos indexed
    (``total``/``indexed``/``failed``), ``sync`` reports every kind of change.
    """

    def work(ctx: JobContext) -> JobOutcome:
        def on_progress(done: int, total: int) -> None:
            # The scan collects its errors in the result, so the live count stays 0;
            # the job's final failed_count comes from counts["failed"].
            ctx.report_progress(total=total, processed=done, failed=0)

        result = use_case.execute(
            options,
            scope_root=folder_path,
            progress=on_progress,
            should_cancel=ctx.cancel_requested,
        )
        if kind == "index":
            return _index_outcome(result, folder_path)
        return _sync_outcome(result, folder_path, options.dry_run)

    return work


def _index_outcome(result: SyncResult, folder_path: str) -> JobOutcome:
    indexed = result.indexed_files
    failed = len(result.errors)
    if result.cancelled:
        message = f"Cancelled after indexing {indexed} photo(s) from '{folder_path}'."
    else:
        message = f"Indexed {indexed} photo(s) from '{folder_path}'."
    if failed:
        message += f" {failed} file(s) failed."
    return JobOutcome(
        message=message,
        counts={
            "total": indexed + result.unchanged_files + failed,
            "indexed": indexed,
            "failed": failed,
        },
        errors=result.errors,
        cancelled=result.cancelled,
    )


def _sync_outcome(result: SyncResult, folder_path: str, dry_run: bool) -> JobOutcome:
    failures = len(result.errors)
    prefix = "[DRY RUN] " if dry_run else ""
    verb = "Cancelled sync" if result.cancelled else "Synced"
    message = (
        f"{prefix}{verb} '{folder_path}': {result.new_files} new, "
        f"{result.modified_files} modified, {result.deleted_entries} deleted, "
        f"{result.unchanged_files} unchanged."
    )
    if result.missing_files:
        message += f" {result.missing_files} missing."
    if failures:
        message += f" {failures} error(s)."
    return JobOutcome(
        message=message,
        counts={
            "new": result.new_files,
            "modified": result.modified_files,
            "deleted": result.deleted_entries,
            "missing": result.missing_files,
            "found_again": result.found_again,
            "unchanged": result.unchanged_files,
            "ignored": result.ignored_files,
            "fingerprints_refreshed": result.fingerprints_refreshed,
            "failed": failures,
        },
        errors=result.errors,
        cancelled=result.cancelled,
    )


def analyze_work(
    use_case: AnalyzePhotosUseCase,
    *,
    reanalyze: bool = False,
    limit: int | None = None,
    retag: bool = False,
) -> Work:
    """Run AI analysis of the library as a job: progress per photo, cooperative cancel."""

    def work(ctx: JobContext) -> JobOutcome:
        def on_progress(p: AnalyzeProgress) -> None:
            ctx.report_progress(total=p.total, processed=p.processed, failed=p.failed)

        if retag:
            report = use_case.retag(progress=on_progress, should_cancel=ctx.cancel_requested)
        else:
            report = use_case.run(
                reanalyze=reanalyze,
                limit=limit,
                progress=on_progress,
                should_cancel=ctx.cancel_requested,
            )
        failed = len(report.errors)
        verb = "Cancelled after analysing" if report.cancelled else "Analysed"
        message = f"{verb} {report.analyzed} photo(s)."
        if report.tagged:
            message += f" Suggested tags for {report.tagged}."
        if failed:
            message += f" {failed} file(s) failed."
        return JobOutcome(
            message=message,
            counts={
                "total": report.total,
                "analyzed": report.analyzed,
                "tagged": report.tagged,
                "failed": failed,
            },
            errors=report.errors,
            cancelled=report.cancelled,
        )

    return work
