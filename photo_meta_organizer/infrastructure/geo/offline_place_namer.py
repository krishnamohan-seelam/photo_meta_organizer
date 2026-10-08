"""Nearest-city place names from a bundled GeoNames extract (no network, no extra dependency).

The table (``cities.tsv.gz``, built by ``scripts/build_cities.py``) holds every city of
15,000+ inhabitants. Lookups bucket cities into 1° cells and scan only the cells near the
query point.
"""

import gzip
import math
import threading
from pathlib import Path

from photo_meta_organizer.application.interfaces.place_namer import PlaceScope
from photo_meta_organizer.domain.geo import haversine_distance_km

_DEFAULT_TABLE = Path(__file__).with_name("cities.tsv.gz")
_KM_PER_DEGREE = 111.0
# How far the nearest city may be and still name the point.
_MAX_KM: dict[str, float] = {"city": 75.0, "country": 600.0}

# Within this distance the biggest city wins over the nearest: GeoNames lists wards and
# suburbs ("Eifuku") that are closer to a point in Tokyo than Tokyo's own centre is.
_METRO_KM = 20.0

_City = tuple[str, float, float, str, int]  # name, latitude, longitude, country, population


class OfflinePlaceNamer:
    def __init__(self, table: Path | None = None) -> None:
        self._table = table or _DEFAULT_TABLE
        self._cells: dict[tuple[int, int], list[_City]] | None = None
        self._load_lock = threading.Lock()

    def _load(self) -> dict[tuple[int, int], list[_City]]:
        """Parse the table on first use, so building the app stays cheap."""
        with self._load_lock:
            if self._cells is None:
                cells: dict[tuple[int, int], list[_City]] = {}
                with gzip.open(self._table, "rt", encoding="utf-8") as lines:
                    for line in lines:
                        name, lat, lon, country, population = line.rstrip("\n").split("\t")
                        city = (name, float(lat), float(lon), country, int(population))
                        cells.setdefault(_cell(city[1], city[2]), []).append(city)
                self._cells = cells
            return self._cells

    def name(self, latitude: float, longitude: float, scope: PlaceScope = "city") -> str | None:
        max_km = _MAX_KM[scope]
        city = self._nearest(latitude, longitude, max_km)
        if city is None:
            return None
        return city[3] if scope == "country" else f"{city[0]}, {city[3]}"

    def _nearest(self, latitude: float, longitude: float, max_km: float) -> _City | None:
        lat_span = math.ceil(max_km / _KM_PER_DEGREE)
        cos_lat = max(math.cos(math.radians(latitude)), 0.01)
        lon_span = min(180, math.ceil(max_km / (_KM_PER_DEGREE * cos_lat)))
        cells = self._load()
        row, col = _cell(latitude, longitude)
        nearest: _City | None = None
        nearest_km = max_km
        biggest: _City | None = None
        for d_row in range(-lat_span, lat_span + 1):
            for d_col in range(-lon_span, lon_span + 1):
                key = (row + d_row, (col + d_col) % 360)
                for city in cells.get(key, ()):
                    km = haversine_distance_km(latitude, longitude, city[1], city[2])
                    if km <= nearest_km:
                        nearest, nearest_km = city, km
                    if km <= _METRO_KM and (biggest is None or city[4] > biggest[4]):
                        biggest = city
        return biggest or nearest


def _cell(latitude: float, longitude: float) -> tuple[int, int]:
    return int(math.floor(latitude)), int(math.floor(longitude + 180.0)) % 360
