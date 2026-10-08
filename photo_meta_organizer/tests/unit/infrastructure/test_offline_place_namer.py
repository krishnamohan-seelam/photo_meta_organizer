"""OfflinePlaceNamer: nearest-city lookup over the bundled GeoNames table."""

import gzip

import pytest

from photo_meta_organizer.application.interfaces.place_namer import PlaceNamer
from photo_meta_organizer.infrastructure.geo.offline_place_namer import OfflinePlaceNamer


@pytest.fixture(scope="module")
def namer() -> OfflinePlaceNamer:
    return OfflinePlaceNamer()


def test_satisfies_the_port(namer):
    assert isinstance(namer, PlaceNamer)


@pytest.mark.parametrize(
    ("lat", "lon", "expected"),
    [
        (35.68, 139.65, "Tokyo, Japan"),
        (35.01, 135.76, "Kyoto, Japan"),
        (37.77, -122.42, "San Francisco, United States"),
        (51.51, -0.13, "London, United Kingdom"),
        (-33.87, 151.21, "Sydney, Australia"),
    ],
)
def test_names_the_nearest_city(namer, lat, lon, expected):
    assert namer.name(lat, lon) == expected


def test_country_scope_drops_the_city(namer):
    assert namer.name(35.68, 139.65, "country") == "Japan"


def test_country_scope_reaches_further_than_city_scope(namer):
    # Middle of the Sahara: no city within city range, a country within country range.
    assert namer.name(24.0, 12.0) is None
    assert namer.name(24.0, 12.0, "country") is not None


def test_open_ocean_has_no_name(namer):
    assert namer.name(-45.0, -130.0, "country") is None


def test_wraps_across_the_antimeridian(namer):
    # Suva (Fiji) sits near 178E; a point just east of the date line is still Fiji.
    assert namer.name(-18.14, -179.9, "country") == "Fiji"


def test_loads_a_custom_table(tmp_path):
    table = tmp_path / "c.tsv.gz"
    with gzip.open(table, "wt", encoding="utf-8") as out:
        out.write("Testville\t10.0\t20.0\tTestland\t1000\n")
    custom = OfflinePlaceNamer(table)
    assert custom.name(10.1, 20.1) == "Testville, Testland"
    assert custom.name(40.0, 20.0) is None
