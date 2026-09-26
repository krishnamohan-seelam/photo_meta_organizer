"""Adapters that turn use cases into ``JobManager`` work functions (PMO-18)."""

from photo_meta_organizer.application.jobs import JobContext, JobOutcome, Work
from photo_meta_organizer.application.use_cases.parallel_index_photos_use_case import (
    IndexProgress,
    ParallelIndexPhotosUseCase,
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
