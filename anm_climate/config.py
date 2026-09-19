from pathlib import Path
import os
import re

BASE_URL = "https://odp.meteoromania.ro/station_data_series/climate/daily/"
ATTRIBUTION = "Administratia Nationala de Meteorologie (ANM) / MeteoRomania Open Data Portal"
DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "data" / "anm"
STATION_PATTERN = re.compile(r"0-\d+-\d+-\d+")
FIELDS = ("wsi", "an", "luna", "zi", "ff", "p", "r", "ta", "tn", "tx")
MEASURES = {
    "ta": "tmean_c", "tn": "tmin_c", "tx": "tmax_c", "r": "precip_mm",
    "ff": "wind_mean_ms", "p": "pressure_msl_hpa",
}


def readonly_uri(path):
    uri = Path(path).resolve().as_uri() + '?mode=ro'
    # Vercel serves a verified, checkpointed snapshot on a read-only filesystem.
    # Immutable mode prevents WAL databases from trying to create -shm/-wal files.
    if os.environ.get('VERCEL') == '1':
        uri += '&immutable=1'
    return uri

def validate_identity(station, year):
    if not STATION_PATTERN.fullmatch(station):
        raise ValueError("Invalid WIGOS station ID")
    if not 1800 <= year <= 2200:
        raise ValueError("Year must be between 1800 and 2200")
    return station, year

def archive_url(station, year):
    validate_identity(station, year)
    return f"{BASE_URL}{station}/{station}_{year}.zip"

def prepare(root):
    root = Path(root)
    for name in ("raw", "extracted", "processed", "logs", "processed/listings"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root
