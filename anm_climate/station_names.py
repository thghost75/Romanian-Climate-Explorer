"""Verified names missing from the ANM locations catalogue.

Exact WIGOS matches from WMO OSCAR/Surface, retrieved 2026-09-21:
https://oscar.wmo.int/surface/rest/api/search/station?territoryName=ROU

Keep these fallbacks with the application so daily observation snapshots cannot
erase them. Preserve names supplied by the snapshot whenever they are available.
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
