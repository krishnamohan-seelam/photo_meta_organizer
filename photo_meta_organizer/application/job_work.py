"""Adapters that turn use cases into ``JobManager`` work functions (PMO-18)."""

from photo_meta_organizer.application.jobs import JobContext, JobOutcome, Work
from photo_meta_organizer.application.use_cases.parallel_index_photos_use_case import (
    IndexProgress,
    ParallelIndexPhotosUseCase,
)
from photo_meta_organizer.application.use_cases.synchronize_metadata_use_case import (
    SynchronizeMetadataUseCase,
)


def index_work(use_case: ParallelIndexPhotosUseCase, folder_path: str) -> Work:
    """Run ``use_case`` as a job: progress per file, cooperative cancel, errors reported."""

    def work(ctx: JobContext) -> JobOutcome:
        def on_progress(p: IndexProgress) -> None:
            ctx.report_progress(total=p.total, processed=p.processed, failed=p.failed)

        report = use_case.run(
            progress=on_progress,
            should_cancel=ctx.cancel_requested,
            show_progress_bar=False,
        )
        indexed, failed = len(report.indexed), len(report.errors)
        if report.cancelled:
            message = f"Cancelled after indexing {indexed} photo(s) from '{folder_path}'."
        else:
            message = f"Indexed {indexed} photo(s) from '{folder_path}'."
        if failed:
            message += f" {failed} file(s) failed."
        return JobOutcome(
            message=message,
            counts={"total": report.total, "indexed": indexed, "failed": failed},
            errors=report.errors,
            cancelled=report.cancelled,
        )

    return work


def sync_work(
    use_case: SynchronizeMetadataUseCase,
    folder_path: str,
    *,
    cleanup_deleted: bool,
    reprocess_modified: bool,
    index_new: bool,
    dry_run: bool,
    rehash: bool,
) -> Work:
    """Run an incremental sync of ``folder_path`` as a job, scoped to that folder."""

    def work(ctx: JobContext) -> JobOutcome:
        def on_progress(done: int, total: int) -> None:
            # Sync collects its errors in the result, so the live count stays 0;
            # the job's final failed_count comes from counts["failed"].
            ctx.report_progress(total=total, processed=done, failed=0)

        result = use_case.execute(
            cleanup_deleted=cleanup_deleted,
            reprocess_modified=reprocess_modified,
            index_new=index_new,
            dry_run=dry_run,
            rehash=rehash,
            scope_root=folder_path,
            progress=on_progress,
            should_cancel=ctx.cancel_requested,
        )
        failures = len(result.errors)
        prefix = "[DRY RUN] " if dry_run else ""
        verb = "Cancelled sync" if result.cancelled else "Synced"
        message = (
            f"{prefix}{verb} '{folder_path}': {result.new_files} new, "
            f"{result.modified_files} modified, {result.deleted_entries} deleted, "
            f"{result.unchanged_files} unchanged."
        )
        if failures:
            message += f" {failures} error(s)."
        return JobOutcome(
            message=message,
            counts={
                "new": result.new_files,
                "modified": result.modified_files,
                "deleted": result.deleted_entries,
                "unchanged": result.unchanged_files,
                "fingerprints_refreshed": result.fingerprints_refreshed,
                "failed": failures,
            },
            errors=result.errors,
            cancelled=result.cancelled,
        )

    return work
