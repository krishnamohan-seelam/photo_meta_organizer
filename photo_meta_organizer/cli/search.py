"""``search``: query the library and print one page as a table."""

from typing import Annotated, Literal

import typer

from photo_meta_organizer.cli.common import (
    DbOption,
    camera_label,
    fail,
    finish,
    open_library,
    start,
)

SortField = Literal["captured_at", "size_bytes", "camera_model", "file_name"]
SortOrder = Literal["asc", "desc"]


def search(
    ctx: typer.Context,
    db: DbOption = None,
    date: Annotated[
        str | None, typer.Option("--date", help="One month or day (YYYY-MM or YYYY-MM-DD)")
    ] = None,
    date_from: Annotated[
        str | None, typer.Option("--date-from", help="Start date (YYYY-MM[-DD], inclusive)")
    ] = None,
    date_to: Annotated[
        str | None,
        typer.Option("--date-to", help="End date (YYYY-MM[-DD], whole day inclusive)"),
    ] = None,
    camera: Annotated[
        str | None, typer.Option("--camera", help="Filter by camera make/model")
    ] = None,
    location: Annotated[
        str | None, typer.Option("--location", help="Filter by location (lat,lon,radius_km)")
    ] = None,
    lat: Annotated[float | None, typer.Option("--lat", help="Latitude for radius search")] = None,
    lon: Annotated[float | None, typer.Option("--lon", help="Longitude for radius search")] = None,
    radius: Annotated[
        float | None, typer.Option("--radius", help="Radius in km for location search")
    ] = None,
    tags: Annotated[
        str | None, typer.Option("--tags", help="Filter by tags (comma-separated)")
    ] = None,
    sort: Annotated[
        SortField, typer.Option("--sort", help="Field to sort by (default: captured_at)")
    ] = "captured_at",
    order: Annotated[SortOrder, typer.Option("--order", help="Sort order (default: asc)")] = "asc",
    page: Annotated[int, typer.Option("--page", help="Page number (default: 1)")] = 1,
    page_size: Annotated[
        int, typer.Option("--page-size", help="Results per page (default: 50)")
    ] = 50,
) -> None:
    """Search indexed photos (Phase 3).

    A date or location that cannot be read is an error (exit code 2).
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

    settings = start(ctx, db)
    try:
        date_start, date_end = date_bounds(date=date, date_from=date_from, date_to=date_to)
        area = parse_location(location, lat=lat, lon=lon, radius_km=radius)
        tags_list = parse_tags(tags)
    except ValueError as exc:
        fail(str(exc), 2)

    # --camera used to set both camera_make and camera_model and rely on a
    # since-removed sentinel (PMO-09) that treated an equal make/model as "search
    # either field"; search_term now covers that (it also matches file name/path,
    # which --camera never claimed to search, but this CLI flag has no separate
    # "search anything" option, so the broader match is the closer fit).
    query = SearchPhotosQuery(
        date_start=date_start,
        date_end=date_end,
        search_term=camera,
        location_lat=area.latitude if area else None,
        location_lon=area.longitude if area else None,
        radius_km=area.radius_km if area else None,
        tags=tags_list,
        sort_by=sort,
        sort_order=order,
        page=page,
        page_size=page_size,
    )
    result = SearchPhotosUseCase(repository=open_library(settings)).execute(query)

    print(
        f"\nSearch Results (Page {result.page} of {result.total_pages} | "
        f"Total: {result.total_count}):\n"
    )
    if not result.items:
        print("No photos found matching the search criteria.")
        finish(0)

    rows = []
    for item in result:
        exif = item.exif
        captured = exif.captured_at.strftime("%Y-%m-%d %H:%M") if exif.captured_at else "N/A"
        size = f"{(item.file_info.size_bytes or 0) / (1024 * 1024):.2f} MB"
        gps = (
            f"{exif.location.latitude:.4f}, {exif.location.longitude:.4f}"
            if exif.location
            else "N/A"
        )
        labels = ", ".join(item.labels)
        rows.append([item.file_info.name, captured, camera_label(exif), size, gps, labels])

    headers = ["Filename", "Captured At", "Camera Make/Model", "Size", "GPS (Lat, Lon)", "Labels"]
    print(tabulate(rows, headers=headers, tablefmt="grid"))
    print(f"\nDisplaying {len(result.items)} item(s) on Page {result.page}.\n")
    finish(0)
