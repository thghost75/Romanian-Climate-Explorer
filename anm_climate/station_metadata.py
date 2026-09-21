"""Verified station metadata missing from the ANM locations catalogue.

Exact WIGOS matches from WMO OSCAR/Surface, retrieved 2026-09-21:
https://oscar.wmo.int/surface/rest/api/search/station?territoryName=ROU

Keep these fallbacks with the application so daily observation snapshots cannot
erase them. Preserve metadata supplied by the snapshot whenever it is available.
"""

WMO_STATION_NAMES = {
    "0-20000-0-15000": "DARABANI",
    "0-20000-0-15004": "SIGHETUL MARMATIEI",
    "0-20000-0-15007": "RADAUTI",
    "0-20000-0-15025": "STANCA STEFANESTI",
    "0-20000-0-15199": "SANNICOLAUL MARE",
    "0-20000-0-15245": "JIMBOLIA",
    "0-20000-0-15289": "BANLOC",
    "0-20000-0-15360": "SULINA",
    "0-20000-0-15387": "SFANTU GHEORGHE DELTA",
    "0-20000-0-15465": "BAILESTI",
    "0-20000-0-15469": "CARACAL",
    "0-20000-0-15475": "OLTENITA",
    "0-20000-0-15479": "ADAMCLISI",
    "0-20000-0-15482": "CALAFAT",
    "0-20000-0-15489": "ALEXANDRIA",
    "0-20000-0-15490": "TURNU-MAGURELE",
    "0-20000-0-15491": "GIURGIU",
    "0-20000-0-15494": "BECHET",
    "0-20000-0-15498": "ZIMNICEA",
    "0-20000-0-15499": "MANGALIA",
}


def resolve_station_name(station_id, name):
    return name or WMO_STATION_NAMES.get(station_id)


# Latitude, longitude pairs; current registry locations, not historical relocations.
WMO_STATION_COORDINATES = {
    "0-20000-0-15000": (48.1949023042, 26.5734788625),
    "0-20000-0-15004": (47.9393033412, 23.9043359391),
    "0-20000-0-15007": (47.8378604586, 25.8904494353),
    "0-20000-0-15025": (47.832254341, 27.2197246685),
    "0-20000-0-15199": (46.0712862547, 20.601560025),
    "0-20000-0-15245": (45.7811111, 20.7023580223),
    "0-20000-0-15289": (45.3827010758, 21.1363985692),
    "0-20000-0-15360": (45.1623111, 29.7268286),
    "0-20000-0-15387": (44.897648531, 29.5991076409),
    "0-20000-0-15465": (44.0292658083, 23.3312240839),
    "0-20000-0-15469": (44.1001209118, 24.3573089316),
    "0-20000-0-15475": (44.0746935582, 26.637136824),
    "0-20000-0-15479": (44.0882700719, 27.965626028),
    "0-20000-0-15482": (43.9848998035, 22.9460524002),
    "0-20000-0-15489": (43.9779209155, 25.3528455408),
    "0-20000-0-15490": (43.7602777778, 24.8783333333),
    "0-20000-0-15491": (43.8751663023, 25.9327409543),
    "0-20000-0-15494": (43.7897215766, 23.9441860197),
    "0-20000-0-15498": (43.661515743, 25.3536153412),
    "0-20000-0-15499": (43.816124375, 28.5874503506),
}


def resolve_station_coordinates(station_id, latitude, longitude):
    if latitude is None and longitude is None:
        return WMO_STATION_COORDINATES.get(station_id, (None, None))
    return latitude, longitude
