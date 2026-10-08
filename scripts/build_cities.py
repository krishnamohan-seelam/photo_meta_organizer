"""Build the offline place-name table used by the Map view.

Downloads GeoNames' ``cities15000`` and ``countryInfo`` (CC BY 4.0, https://www.geonames.org)
and writes ``photo_meta_organizer/infrastructure/geo/cities.tsv.gz``: one line per city
(``name<TAB>lat<TAB>lon<TAB>country<TAB>population``). The result is committed, so running
the app needs no network and no extra dependency. Re-run only to refresh the data:

    python -m scripts.build_cities
"""

import gzip
import io
import urllib.request
import zipfile
from pathlib import Path

_BASE = "https://download.geonames.org/export/dump/"
_OUT = Path(__file__).resolve().parent.parent / "photo_meta_organizer/infrastructure/geo"


def _fetch(name: str) -> bytes:
    with urllib.request.urlopen(_BASE + name, timeout=60) as response:  # noqa: S310
        return response.read()


def main() -> None:
    countries: dict[str, str] = {}
    for line in _fetch("countryInfo.txt").decode("utf-8").splitlines():
        if line and not line.startswith("#"):
            fields = line.split("\t")
            countries[fields[0]] = fields[4]

    with zipfile.ZipFile(io.BytesIO(_fetch("cities15000.zip"))) as archive:
        rows = archive.read("cities15000.txt").decode("utf-8").splitlines()

    lines = []
    for row in rows:
        f = row.split("\t")
        # geonameid, name, asciiname, alternates, lat, lon, ..., country(8), ..., population(14)
        lines.append("\t".join([f[1], f[4], f[5], countries.get(f[8], f[8]), f[14]]))

    _OUT.mkdir(parents=True, exist_ok=True)
    with gzip.open(_OUT / "cities.tsv.gz", "wt", encoding="utf-8", compresslevel=9) as out:
        out.write("\n".join(lines) + "\n")
    print(f"wrote {len(lines)} cities, {len(countries)} countries")


if __name__ == "__main__":
    main()
