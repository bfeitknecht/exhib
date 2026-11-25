"""Place names for GPS coordinates, offline.

The table is GeoNames cities1000 (every place with 1000 or more people;
https://www.geonames.org, CC BY 4.0), cut to lat, lon, name and country.
No coordinate leaves the pod: the lookup is a nearest-neighbour search in
memory, on a 1-degree grid.

Refresh the table: download cities1000.zip and countryInfo.txt from
https://download.geonames.org/export/dump/. data/places.tsv.gz holds one
row per place, `lat<TAB>lon<TAB>name<TAB>country code` (4 decimals), without
feature codes PPLX, PPLH, PPLQ, PPLW, PPLCH (city districts, historical and
abandoned places). data/countries.tsv holds `code<TAB>name`.
"""

from __future__ import annotations

import gzip
import math
from functools import cache
from pathlib import Path

DATA = Path(__file__).with_name("data")
# Farther than this from any listed place: no name (open sea, wilderness).
MAX_KM = 30.0

Place = tuple[float, float, str, str]


@cache
def _grid() -> dict[tuple[int, int], list[Place]]:
    grid: dict[tuple[int, int], list[Place]] = {}
    with gzip.open(DATA / "places.tsv.gz", "rt", encoding="utf-8") as rows:
        for row in rows:
            if row.startswith("#"):
                continue
            lat, lon, name, country = row.rstrip("\n").split("\t")
            place = (float(lat), float(lon), name, country)
            grid.setdefault((math.floor(place[0]), math.floor(place[1])), []).append(
                place
            )
    return grid


@cache
def _countries() -> dict[str, str]:
    lines = (DATA / "countries.tsv").read_text(encoding="utf-8").splitlines()
    return dict(line.split("\t", 1) for line in lines if not line.startswith("#"))


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Equirectangular: exact enough for "which town is nearest".
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return 6371.0 * math.hypot(x, y)


def nearest(lat: float, lon: float) -> tuple[str, str] | None:
    """(place, country) nearest to lat/lon, or None if nothing is close."""
    grid = _grid()
    best, best_km = None, MAX_KM
    cell_lat, cell_lon = math.floor(lat), math.floor(lon)
    for dlat in (-1, 0, 1):
        for dlon in (-1, 0, 1):
            cell = (cell_lat + dlat, (cell_lon + dlon + 180) % 360 - 180)
            for place in grid.get(cell, ()):
                km = _km(lat, lon, place[0], place[1])
                if km < best_km:
                    best, best_km = place, km
    if best is None:
        return None
    return best[2], _countries().get(best[3], best[3])
