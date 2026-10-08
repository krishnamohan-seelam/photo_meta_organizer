"""Map helpers shared by the API and the repositories (no I/O)."""

from photo_meta_organizer.application.interfaces.place_namer import PlaceScope

# A marker should cover roughly this many pixels of a 256 px map tile.
_CLUSTER_PIXELS = 64
_TILE_PIXELS = 256
_MIN_ZOOM, _MAX_ZOOM = 0, 20


def cell_degrees_for_zoom(zoom: int) -> float:
    """Side, in degrees, of the grid cell that clusters photos at a Web-Mercator zoom level.

    A tile spans ``360 / 2**zoom`` degrees of longitude; a cell is the part of it that a
    ~64 px marker covers, so clusters keep a constant on-screen size as the user zooms.
    """
    clamped = max(_MIN_ZOOM, min(_MAX_ZOOM, zoom))
    return float(360.0 / (2**clamped) * _CLUSTER_PIXELS / _TILE_PIXELS)


# Above this cell size a cluster spans a region, so a city name would mislead.
_COUNTRY_CELL_DEGREES = 2.0


def place_scope_for_zoom(zoom: int) -> PlaceScope:
    """Label clusters by country when zoomed far out and by city when zoomed in."""
    return "country" if cell_degrees_for_zoom(zoom) > _COUNTRY_CELL_DEGREES else "city"
