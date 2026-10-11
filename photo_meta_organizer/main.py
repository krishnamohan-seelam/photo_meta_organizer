"""Command-line interface for Photo Meta Organizer.

Parses arguments, configures logging (at startup, not import: see
``infrastructure.logging_setup``) and dispatches to the application use cases.
Repositories and retrievers come from the shared composition root,
``application.composition``, so the CLI, the REST API and the desktop backend build
them the same way; parsing of search arguments lives in
``application.search_criteria``.

Example:
    $ python -m photo_meta_organizer.main --help
    $ python -m photo_meta_organizer.main index --path /photos --db photos.db
"""

import argparse
import logging
import sys
from typing import TYPE_CHECKING

from photo_meta_organizer import __version__
from photo_meta_organizer.application.interfaces import (
    ImageMetadataExtractor,
    ImageMetadataRepository,
    ImageRetriever,
)
from photo_meta_organizer.application.settings import Settings

if TYPE_CHECKING:
    from photo_meta_organizer.infrastructure.analysis.model_store import ModelStore

logger = logging.getLogger(__name__)


# ============================================================================
# FACTORIES — thin wrappers over application.composition
# ============================================================================


def build_retriever(args: argparse.Namespace) -> ImageRetriever:
    """Create the file retriever based on CLI arguments.

    Delegates to the shared factory so the CLI and the REST API index exactly the
    same set of files (images only).

    Phase 4: Will support S3Retriever, GoogleCloudStorageRetriever, etc.

    Args:
        args: Parsed CLI arguments containing --path.

    Returns:
        An ImageRetriever implementation.
    """
    from photo_meta_organizer.application.composition import build_local_retriever

    return build_local_retriever(args.path)


def build_extractor() -> ImageMetadataExtractor:
    """Create the metadata extractor.

    The extractor is stateless with no configuration — there's only
    one implementation needed. Phase 5 may add AI-based extractors.

    Returns:
        A stateless ImageMetadataExtractor implementation.
    """
    from photo_meta_organizer.infrastructure.extractors.disk_metadata_extractor import (
        DiskMetaDataExtractor,
    )

    return DiskMetaDataExtractor()


def build_repository(args: argparse.Namespace) -> ImageMetadataRepository:
    """Create the metadata repository based on CLI arguments.

    SQLite behind the repository port (ADR-001, PMO-08). A ``--db`` pointing at an
    existing legacy TinyDB JSON file is imported once into a sibling ``.db`` file;
    see ``application.composition.build_repository``.

    Args:
        args: Parsed CLI arguments containing --db.

    Returns:
        An ImageMetadataRepository implementation.
    """
    from photo_meta_organizer.application.composition import (
        build_repository as _build_repository,
    )

    return _build_repository(args.db)


# ============================================================================
# CLI COMMAND HANDLERS
# ============================================================================


def handle_index_command(args: argparse.Namespace) -> int:
    """Handle 'index' command — scan photos and extract metadata.

    Delegates to IndexPhotosUseCase or ParallelIndexPhotosUseCase for the full pipeline:
    retrieve → extract → persist.

    Args:
        args: Parsed CLI arguments (--path, --db, etc.).

    Returns:
        Exit code: 0 = success, 2 = some files failed (listed on stdout).
    """
    retriever = build_retriever(args)
    extractor = build_extractor()
    repository = build_repository(args)

    workers = getattr(args, "workers", 4)
    if workers > 1:
        from photo_meta_organizer.application.use_cases import (
            ParallelIndexPhotosUseCase,
        )
        from photo_meta_organizer.infrastructure.metrics import ProgressReporter

        report = ParallelIndexPhotosUseCase(
            retriever=retriever,
            extractor=extractor,
            repository=repository,
            num_workers=workers,
            progress_reporter=ProgressReporter(),
        ).run()
        print(f"Successfully indexed {len(report.indexed)} photos")
        if report.errors:
            print(f"Errors ({len(report.errors)}):")
            for err in report.errors:
                print(f"  x {err}")
        return 0 if not report.errors else 2

    from photo_meta_organizer.application.use_cases import IndexPhotosUseCase

    results = IndexPhotosUseCase(
        retriever=retriever,
        extractor=extractor,
        repository=repository,
    ).execute()
    print(f"Successfully indexed {len(results)} photos")
    return 0


def handle_search_command(args: argparse.Namespace) -> int:
    """Handle 'search' command — query indexed photos.

    Args:
        args: Parsed CLI arguments (--camera, --date, --sort, etc.).

    Returns:
        Exit code (0 = success, non-zero = error).
    """
    from tabulate import tabulate

    from photo_meta_organizer.application.search_criteria import (
        date_bounds,
        parse_location,
        parse_tags,
    )
    from photo_meta_organizer.application.use_cases import (
        SearchPhotosQuery,
        SearchPhotosUseCase,
    )

    try:
        date_start, date_end = date_bounds(
            date=getattr(args, "date", None),
            date_from=getattr(args, "date_from", None),
            date_to=getattr(args, "date_to", None),
        )
        location = parse_location(
            getattr(args, "location", None),
            lat=getattr(args, "lat", None),
            lon=getattr(args, "lon", None),
            radius_km=getattr(args, "radius", None),
        )
        tags_list = parse_tags(getattr(args, "tags", None))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    repository = build_repository(args)

    # --camera used to set both camera_make and camera_model and rely on a
    # since-removed sentinel (PMO-09) that treated an equal make/model as "search
    # either field"; search_term now covers that (it also matches file name/path,
    # which --camera never claimed to search, but this CLI flag has no separate
    # "search anything" option, so the broader match is the closer fit).
    query = SearchPhotosQuery(
        date_start=date_start,
        date_end=date_end,
        search_term=getattr(args, "camera", None),
        location_lat=location.latitude if location else None,
        location_lon=location.longitude if location else None,
        radius_km=location.radius_km if location else None,
        tags=tags_list,
        sort_by=getattr(args, "sort", "captured_at"),
        sort_order=getattr(args, "order", "asc"),
        page=getattr(args, "page", 1),
        page_size=getattr(args, "page_size", 50),
    )

    use_case = SearchPhotosUseCase(repository=repository)
    result = use_case.execute(query)

    print(
        f"\nSearch Results (Page {result.page} of {result.total_pages} | "
        f"Total: {result.total_count}):\n"
    )

    if not result.items:
        print("No photos found matching the search criteria.")
        return 0

    table_data = []
    for item in result:
        exif = item.exif
        cam = f"{exif.camera_make or ''} {exif.camera_model or ''}".strip() or "Unknown"
        dt_str = exif.captured_at.strftime("%Y-%m-%d %H:%M") if exif and exif.captured_at else "N/A"
        size_mb = (item.file_info.size_bytes or 0) / (1024 * 1024)
        size_str = f"{size_mb:.2f} MB"
        loc_str = (
            f"{exif.location.latitude:.4f}, {exif.location.longitude:.4f}"
            if exif and exif.location
            else "N/A"
        )
        labels_str = ", ".join(item.labels) if item.labels else ""

        table_data.append(
            [
                item.file_info.name,
                dt_str,
                cam,
                size_str,
                loc_str,
                labels_str,
            ]
        )

    headers = [
        "Filename",
        "Captured At",
        "Camera Make/Model",
        "Size",
        "GPS (Lat, Lon)",
        "Labels",
    ]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    print(f"\nDisplaying {len(result.items)} item(s) on Page {result.page}.\n")
    return 0


def handle_stats_command(args: argparse.Namespace) -> int:
    """Handle 'stats' command — show library statistics.

    Args:
        args: Parsed CLI arguments (--db, etc.).

    Returns:
        Exit code (0 = success, non-zero = error).
    """
    from collections import Counter

    from tabulate import tabulate

    try:
        repository = build_repository(args)
        all_metadata = repository.list_all()
        total_photos = len(all_metadata)

        total_bytes = 0
        mime_counts: Counter[str] = Counter()
        camera_counts: Counter[str] = Counter()
        dates = []

        for item in all_metadata:
            if hasattr(item, "file_info") and item.file_info:
                total_bytes += getattr(item.file_info, "size_bytes", 0)
                mime_counts[getattr(item.file_info, "mime_type", "unknown")] += 1
            if hasattr(item, "exif") and item.exif:
                make = getattr(item.exif, "camera_make", "") or ""
                model = getattr(item.exif, "camera_model", "") or ""
                cam_name = f"{make} {model}".strip() or "Unknown"
                camera_counts[cam_name] += 1
                if item.exif.captured_at:
                    dates.append(item.exif.captured_at)

        # Format size in human-readable units
        size_mb = total_bytes / (1024 * 1024)
        size_str = f"{size_mb / 1024:.2f} GB" if size_mb >= 1024 else f"{size_mb:.2f} MB"

        date_range_str = "N/A"
        if dates:
            min_date = min(dates).strftime("%Y-%m-%d")
            max_date = max(dates).strftime("%Y-%m-%d")
            date_range_str = f"{min_date} to {max_date}"

        print("\n=======================================================")
        print("       PHOTO META ORGANIZER - LIBRARY STATISTICS       ")
        print("=======================================================")
        print(f" Database File         : {args.db}")
        print(f" Total Photos Indexed  : {total_photos}")
        print(f" Total Storage Size    : {size_str} ({total_bytes:,} bytes)")
        print(f" Date Range            : {date_range_str}")

        if mime_counts:
            print("\nFormat Distribution:")
            format_table = [[mime, count] for mime, count in mime_counts.most_common()]
            print(tabulate(format_table, headers=["Format", "Count"], tablefmt="simple"))

        if camera_counts:
            print("\nCamera Distribution:")
            camera_table = [[cam, count] for cam, count in camera_counts.most_common()]
            print(
                tabulate(
                    camera_table,
                    headers=["Camera Make/Model", "Count"],
                    tablefmt="simple",
                )
            )

        print("=======================================================\n")
    except Exception as e:
        logger.error("Failed to read statistics: %s", e)
        print(f"Error reading statistics: {e}")
        return 1
    return 0


def handle_sync_command(args: argparse.Namespace) -> int:
    """Handle 'sync' command — incremental metadata synchronization.

    Detects NEW, MODIFIED, DELETED, and UNCHANGED files by comparing
    the metadata DB against the current disk state.  Only changed files
    are processed, making this significantly faster than a full reindex
    for large libraries with few changes.

    Args:
        args: Parsed CLI arguments (--path, --db, sync flags).

    Returns:
        Exit code (0 = success, non-zero = error).
    """
    from photo_meta_organizer.application.use_cases import SynchronizeMetadataUseCase

    retriever = build_retriever(args)
    extractor = build_extractor()
    repository = build_repository(args)

    use_case = SynchronizeMetadataUseCase(
        retriever=retriever,
        extractor=extractor,
        repository=repository,
    )

    result = use_case.execute(
        cleanup_deleted=args.cleanup_deleted,
        reprocess_modified=args.reprocess_modified,
        index_new=args.index_new,
        dry_run=args.dry_run,
        rehash=args.rehash,
        reextract=args.reextract,
        # Only records under --path take part, so --cleanup-deleted can never
        # remove photos indexed from another folder.
        scope_root=args.path,
    )

    prefix = "[DRY RUN] " if args.dry_run else ""
    print(
        f"{prefix}Sync complete in {result.duration_seconds:.2f}s: "
        f"+{result.new_files} new, "
        f"~{result.modified_files} modified, "
        f"-{result.deleted_entries} deleted, "
        f"{result.unchanged_files} unchanged"
    )
    if result.fingerprints_refreshed:
        verb = "would record" if args.dry_run else "recorded"
        print(f"  ({verb} size/mtime for {result.fingerprints_refreshed} unchanged file(s))")
    if result.errors:
        print(f"Errors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  x {err}")
    return 0 if not result.errors else 2


def handle_dedupe_command(args: argparse.Namespace) -> int:
    """Handle 'dedupe' command — merge records that share a file path.

    Dry-run by default; pass --apply to write.
    """
    from photo_meta_organizer.application.use_cases import DedupePathsUseCase

    repository = build_repository(args)
    result = DedupePathsUseCase(repository).execute(apply=args.apply)

    if not result.groups:
        print("No duplicate paths found.")
        return 0
    extra = sum(len(g.drop) for g in result.groups)
    label = "Merged" if args.apply else "Would merge (dry run; pass --apply to write)"
    print(f"{label}: {extra} extra record(s) across {len(result.groups)} path(s)")
    for group in result.groups[:50]:
        print(f"  {group.path}  keep {group.keep.file_hash[:12]}, drop {len(group.drop)}")
    if len(result.groups) > 50:
        print(f"  ... and {len(result.groups) - 50} more")
    if args.apply:
        print(f"Removed {result.removed} record(s).")
    return 0


def handle_prune_command(args: argparse.Namespace) -> int:
    """Handle 'prune' command — remove records for non-image files.

    Dry-run by default; pass --apply to delete.
    """
    from photo_meta_organizer.application.use_cases import PruneNonImagesUseCase

    repository = build_repository(args)
    result = PruneNonImagesUseCase(repository).execute(apply=args.apply)

    if not result.candidates:
        print("No non-image records found.")
        return 0
    label = "Removed" if args.apply else "Would remove (dry run; pass --apply to delete)"
    print(f"{label}: {len(result.candidates)} record(s)")
    for record in result.candidates[:50]:
        print(f"  {record.file_info.path}")
    if len(result.candidates) > 50:
        print(f"  ... and {len(result.candidates) - 50} more")
    if args.apply:
        print(f"Deleted {result.removed} record(s).")
    return 0


def _install_model(store: "ModelStore", args: argparse.Namespace) -> bool:
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
    if not args.download:
        print("Run again with --download to install it.")
        return False
    if not args.yes:
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
        last = 0

        def on_progress(done: int, total: int) -> None:
            nonlocal last
            bar.update(done - last)
            last = done

        before = store.manifest.total_bytes - store.missing_bytes()
        last = before
        store.download(progress=on_progress)
    return True


def handle_analyze_command(args: argparse.Namespace) -> int:
    """Handle 'analyze' command: embed photos with the AI model and suggest tags.

    Incremental: only photos with no embedding from the current model are processed, so it is
    safe to interrupt and re-run. Exit code: 0 = success, 1 = could not start (model missing,
    not agreed, extra not installed), 2 = some files failed (listed on stdout).
    """
    from tqdm import tqdm

    from photo_meta_organizer.application import composition
    from photo_meta_organizer.application.use_cases.analyze_photos_use_case import (
        AnalyzePhotosUseCase,
        AnalyzeProgress,
    )
    from photo_meta_organizer.infrastructure.analysis.model_store import ModelUnavailableError

    settings = Settings.from_env(model_dir=getattr(args, "model_dir", None))
    store = composition.build_model_store(settings)
    try:
        if not store.is_installed() and not _install_model(store, args):
            return 1
        embedder = composition.build_embedder(store)
        tagger = None if args.no_tags else composition.build_tagger(settings, embedder)
        repository = build_repository(args)
        analysis = composition.build_analysis_repository(repository)
        use_case = AnalyzePhotosUseCase(
            analysis,
            embedder,
            tagger,
            workers=args.workers,
            tag_threshold=args.threshold,
        )

        bar: tqdm | None = None
        last = 0

        def on_progress(p: AnalyzeProgress) -> None:
            nonlocal bar, last
            if bar is None:
                bar = tqdm(total=p.total, unit="photo", desc="Analyzing", disable=None)
            bar.update(p.processed - last)
            last = p.processed

        try:
            if args.retag:
                if tagger is None:
                    print("Error: --retag cannot be combined with --no-tags.", file=sys.stderr)
                    return 1
                report = use_case.retag(progress=on_progress)
            else:
                report = use_case.run(
                    reanalyze=args.reanalyze, limit=args.limit, progress=on_progress
                )
        finally:
            if bar is not None:
                bar.close()
    except ModelUnavailableError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    if report.total == 0 and args.retag:
        print("Nothing to retag: no photo has been analyzed yet.")
        return 0
    if report.total == 0:
        print("Nothing to analyze: every photo already has an embedding from this model.")
        return 0
    print(
        f"Analyzed {report.analyzed} photo(s) with {embedder.model_id}"
        + (f"; suggested tags for {report.tagged}." if tagger else ".")
    )
    if report.errors:
        print(f"Errors ({len(report.errors)}):")
        for failure in report.errors:
            # ASCII only: a redirected Windows console cannot encode a cross mark.
            print(f"  x {failure}")
        return 2
    return 0


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================


DB_HELP = "Path to metadata database file (default: $PMO_DB, else photos.db)"


def main() -> int:
    """Main entry point for the application.

    Parses CLI arguments and dispatches to the appropriate command handler.

    Returns:
        Exit code passed to sys.exit().
    """
    parser = argparse.ArgumentParser(
        prog="photo-meta-organizer",
        description=(
            "High-performance metadata indexing and organization system "
            "for large photo libraries (20GB+)"
        ),
        epilog="For more info: https://github.com/krishnamohan-seelam/photo_meta_organizer",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level (default: INFO)",
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        help=(
            "Write a rotating photo_meta_organizer.log here "
            "(default: $PMO_LOG_DIR, else no log file)"
        ),
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Index command (Phase 1)
    index_parser = subparsers.add_parser(
        "index",
        help="Index photos and extract metadata",
    )
    index_parser.add_argument(
        "--path",
        required=True,
        help="Path to photos directory",
    )
    index_parser.add_argument(
        "--db",
        default=None,
        help=DB_HELP,
    )
    index_parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of worker threads (Phase 2 — default: 4)",
    )
    index_parser.set_defaults(func=handle_index_command)

    # Search command (Phase 3)
    search_parser = subparsers.add_parser(
        "search",
        help="Search indexed photos (Phase 3)",
    )
    search_parser.add_argument("--db", default=None, help=DB_HELP)
    search_parser.add_argument("--date", help="One month or day (YYYY-MM or YYYY-MM-DD)")
    search_parser.add_argument("--date-from", help="Start date (YYYY-MM[-DD], inclusive)")
    search_parser.add_argument("--date-to", help="End date (YYYY-MM[-DD], whole day inclusive)")
    search_parser.add_argument("--camera", help="Filter by camera make/model")
    search_parser.add_argument("--location", help="Filter by location (lat,lon,radius_km)")
    search_parser.add_argument("--lat", type=float, help="Latitude for radius search")
    search_parser.add_argument("--lon", type=float, help="Longitude for radius search")
    search_parser.add_argument("--radius", type=float, help="Radius in km for location search")
    search_parser.add_argument("--tags", help="Filter by tags (comma-separated)")
    search_parser.add_argument(
        "--sort",
        default="captured_at",
        choices=["captured_at", "size_bytes", "camera_model", "file_name"],
        help="Field to sort by (default: captured_at)",
    )
    search_parser.add_argument(
        "--order",
        default="asc",
        choices=["asc", "desc"],
        help="Sort order (default: asc)",
    )
    search_parser.add_argument("--page", type=int, default=1, help="Page number (default: 1)")
    search_parser.add_argument(
        "--page-size", type=int, default=50, help="Results per page (default: 50)"
    )
    search_parser.set_defaults(func=handle_search_command)

    # Sync command (Phase 1.5 — Metadata Sync)
    sync_parser = subparsers.add_parser(
        "sync",
        help="Incrementally sync metadata DB with disk state",
        description=(
            "Detect and process changes (new, modified, deleted) between "
            "the metadata DB and current disk contents. Much faster than "
            "a full 'index' for large libraries with few changes."
        ),
    )
    sync_parser.add_argument(
        "--path",
        required=True,
        help="Path to photos directory",
    )
    sync_parser.add_argument(
        "--db",
        default=None,
        help=DB_HELP,
    )
    sync_parser.add_argument(
        "--cleanup-deleted",
        action="store_true",
        default=False,
        help="Remove DB entries for files no longer on disk (default: off)",
    )
    sync_parser.add_argument(
        "--no-reprocess",
        dest="reprocess_modified",
        action="store_false",
        default=True,
        help="Skip re-extraction of modified files",
    )
    sync_parser.add_argument(
        "--no-index",
        dest="index_new",
        action="store_false",
        default=True,
        help="Skip indexing of new files",
    )
    sync_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Analyse changes but do NOT write anything (preview mode)",
    )
    sync_parser.add_argument(
        "--rehash",
        action="store_true",
        default=False,
        help=(
            "Hash every file already in the DB instead of trusting size+mtime. Slow, but "
            "catches an edit that kept both size and mtime"
        ),
    )
    sync_parser.add_argument(
        "--reextract",
        action="store_true",
        default=False,
        help=(
            "Re-extract every file already in the DB (keeps ratings, flags and labels). "
            "Slow; repairs records from older versions, e.g. capture dates taken from "
            "the file's modification time"
        ),
    )
    sync_parser.set_defaults(
        func=handle_sync_command,
        cleanup_deleted=False,
        reprocess_modified=True,
        index_new=True,
        dry_run=False,
        rehash=False,
        reextract=False,
    )

    # Prune command (PMO-04)
    prune_parser = subparsers.add_parser(
        "prune",
        help="Remove records for non-image files from the database",
        description=(
            "Older versions of the REST API indexed every file in a folder. This removes "
            "records whose file is not an image. Dry run unless --apply is given."
        ),
    )
    prune_parser.add_argument("--db", default=None, help=DB_HELP)
    prune_parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Actually delete (default: dry run)",
    )
    prune_parser.set_defaults(func=handle_prune_command)

    # Dedupe command (PMO-05)
    dedupe_parser = subparsers.add_parser(
        "dedupe",
        help="Merge records that share a file path (left by older versions of sync)",
        description=(
            "Before PMO-05 an edited file was saved under its new hash and the old record "
            "stayed behind. This keeps the newest record per path and merges the rating, "
            "flag and labels of the others into it. Dry run unless --apply is given."
        ),
    )
    dedupe_parser.add_argument("--db", default=None, help=DB_HELP)
    dedupe_parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Actually merge (default: dry run)",
    )
    dedupe_parser.set_defaults(func=handle_dedupe_command)

    # Analyze command (Phase 5, ADR-002)
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Embed photos with the AI model and suggest tags (Phase 5)",
        description=(
            "Computes an AI embedding for every photo that has none from the current model and "
            "suggests tags from a fixed vocabulary. Suggestions never change your own tags until "
            "you accept them. Runs on this computer; the model (about 305 MB) is downloaded once, "
            "and only with --download and your confirmation. Safe to interrupt and re-run."
        ),
    )
    analyze_parser.add_argument("--db", default=None, help=DB_HELP)
    analyze_parser.add_argument(
        "--model-dir",
        default=None,
        help="Where the model is stored (default: $PMO_MODEL_DIR, else .cache/models)",
    )
    analyze_parser.add_argument(
        "--download",
        action="store_true",
        default=False,
        help="Download the model if it is not installed (asks first unless --yes)",
    )
    analyze_parser.add_argument(
        "--yes", action="store_true", default=False, help="Agree to the download without asking"
    )
    analyze_parser.add_argument(
        "--reanalyze",
        action="store_true",
        default=False,
        help="Redo every photo, not just those without an embedding",
    )
    analyze_parser.add_argument(
        "--retag",
        action="store_true",
        default=False,
        help="Only recompute suggested tags from the stored embeddings (fast; opens no photos)",
    )
    analyze_parser.add_argument(
        "--no-tags", action="store_true", default=False, help="Embeddings only; suggest no tags"
    )
    analyze_parser.add_argument(
        "--limit", type=int, default=None, help="Analyze at most this many photos in this run"
    )
    analyze_parser.add_argument(
        "--workers", type=int, default=2, help="Photos decoded in parallel (default: 2)"
    )
    analyze_parser.add_argument(
        "--threshold",
        type=float,
        default=0.05,
        help="Least confidence (0-1) for a suggested tag (default: 0.05)",
    )
    analyze_parser.set_defaults(func=handle_analyze_command)

    # Stats command (Phase 2)
    stats_parser = subparsers.add_parser(
        "stats",
        help="Show library statistics (Phase 2)",
    )
    stats_parser.add_argument("--db", default=None, help=DB_HELP)
    stats_parser.set_defaults(func=handle_stats_command)

    try:
        args = parser.parse_args()
        # Same precedence as the API and desktop backend: flag > environment > default.
        settings = Settings.from_env(db_path=getattr(args, "db", None), log_dir=args.log_dir)
        if hasattr(args, "db"):
            args.db = str(settings.db_path)

        from photo_meta_organizer.infrastructure.logging_setup import configure_logging

        configure_logging(args.log_level, settings.log_dir)
        logger.debug("Starting Photo Meta Organizer (log level: %s)", args.log_level)

        # If no command specified, print help
        if not hasattr(args, "func"):
            parser.print_help()
            return 0

        # Dispatch to command handler
        logger.debug("Executing command: %s", args.command)
        return int(args.func(args))

    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
