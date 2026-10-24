"""``analyze``: embed photos with the AI model and suggest tags (Phase 5, ADR-002)."""

import sys
from typing import TYPE_CHECKING, Annotated

import typer

from photo_meta_organizer.cli.common import (
    DbOption,
    fail,
    finish,
    open_library,
    print_errors,
    start,
)

if TYPE_CHECKING:
    from photo_meta_organizer.infrastructure.analysis.model_store import ModelStore


def analyze(
    ctx: typer.Context,
    db: DbOption = None,
    model_dir: Annotated[
        str | None,
        typer.Option(
            "--model-dir",
            help="Where the model is stored (default: $PMO_MODEL_DIR, else the per-user data "
            "folder)",
        ),
    ] = None,
    download: Annotated[
        bool,
        typer.Option(
            "--download", help="Download the model if it is not installed (asks first unless --yes)"
        ),
    ] = False,
    yes: Annotated[
        bool, typer.Option("--yes", help="Agree to the download without asking")
    ] = False,
    reanalyze: Annotated[
        bool,
        typer.Option("--reanalyze", help="Redo every photo, not just those without an embedding"),
    ] = False,
    retag: Annotated[
        bool,
        typer.Option(
            "--retag",
            help="Only recompute suggested tags from the stored embeddings (fast; opens no photos)",
        ),
    ] = False,
    no_tags: Annotated[
        bool, typer.Option("--no-tags", help="Embeddings only; suggest no tags")
    ] = False,
    limit: Annotated[
        int | None, typer.Option("--limit", help="Analyze at most this many photos in this run")
    ] = None,
    workers: Annotated[
        int, typer.Option("--workers", help="Photos decoded in parallel (default: 2)")
    ] = 2,
    threshold: Annotated[
        float,
        typer.Option(
            "--threshold", help="Least confidence (0-1) for a suggested tag (default: 0.05)"
        ),
    ] = 0.05,
) -> None:
    """Embed photos with the AI model and suggest tags (Phase 5).

    Computes an AI embedding for every photo that has none from the current model and
    suggests tags from a fixed vocabulary. Suggestions never change your own tags until
    you accept them. Runs on this computer; the model (about 305 MB) is downloaded once,
    and only with --download and your confirmation. Safe to interrupt and re-run.
    Exit code: 0 = success, 1 = could not start (model missing, not agreed, extra not
    installed), 2 = some files failed (listed on stdout).
    """
    from tqdm import tqdm

    from photo_meta_organizer.application import composition
    from photo_meta_organizer.application.use_cases.analyze_photos_use_case import (
        AnalyzePhotosUseCase,
        AnalyzeProgress,
    )
    from photo_meta_organizer.infrastructure.analysis.model_store import ModelUnavailableError

    settings = start(ctx, db, model_dir)
    store = composition.build_model_store(settings)
    try:
        if not store.is_installed() and not _install_model(store, download=download, yes=yes):
            finish(1)
        embedder = composition.build_embedder(store)
        tagger = None if no_tags else composition.build_tagger(settings, embedder)
        analysis = composition.build_analysis_repository(open_library(settings))
        use_case = AnalyzePhotosUseCase(
            analysis, embedder, tagger, workers=workers, tag_threshold=threshold
        )

        bar: tqdm | None = None
        last = 0

        def on_progress(progress: AnalyzeProgress) -> None:
            nonlocal bar, last
            if bar is None:
                bar = tqdm(total=progress.total, unit="photo", desc="Analyzing", disable=None)
            bar.update(progress.processed - last)
            last = progress.processed

        try:
            if retag:
                if tagger is None:
                    fail("--retag cannot be combined with --no-tags.")
                report = use_case.retag(progress=on_progress)
            else:
                report = use_case.run(reanalyze=reanalyze, limit=limit, progress=on_progress)
        finally:
            if bar is not None:
                bar.close()
    except ModelUnavailableError as err:
        fail(str(err))

    if report.total == 0 and retag:
        print("Nothing to retag: no photo has been analyzed yet.")
        finish(0)
    if report.total == 0:
        print("Nothing to analyze: every photo already has an embedding from this model.")
        finish(0)
    print(
        f"Analyzed {report.analyzed} photo(s) with {embedder.model_id}"
        + (f"; suggested tags for {report.tagged}." if tagger else ".")
    )
    print_errors(report.errors)
    finish(2 if report.errors else 0)


def _install_model(store: "ModelStore", *, download: bool, yes: bool) -> bool:
    """Download the AI model if the user agrees. Returns whether it is now installed."""
    from tqdm import tqdm

    manifest = store.manifest
    print(
        f"The AI features need a one-time download of {store.missing_bytes() / 1e6:.0f} MB:\n"
        f"  model:   {manifest.source}\n"
        f"  licence: {manifest.licence}\n"
        f"  into:    {store.directory}\n"
        "Only the model is downloaded (its server sees your IP address); your photos and "
        "library never leave this computer, and analysis runs offline afterwards."
    )
    if not download:
        print("Run again with --download to install it.")
        return False
    if not yes:
        if not sys.stdin.isatty():
            print(
                "Refusing to download without confirmation: pass --yes to agree.",
                file=sys.stderr,
            )
            return False
        if input("Download now? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Cancelled; nothing was downloaded.")
            return False
    with tqdm(
        total=store.missing_bytes(), unit="B", unit_scale=True, desc="Downloading", disable=None
    ) as bar:
        last = store.manifest.total_bytes - store.missing_bytes()

        def on_progress(done: int, total: int) -> None:
            nonlocal last
            bar.update(done - last)
            last = done

        store.download(progress=on_progress)
    return True
