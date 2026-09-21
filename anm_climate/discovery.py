"""Directory-only discovery. Never requests a ZIP or one HEAD per archive."""
import csv
import calendar
import http.client
import io
import json
import logging
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, unquote
from .config import BASE_URL, STATION_PATTERN, ATTRIBUTION, prepare
from .http import atomic_json, utc_now

LOG = logging.getLogger(__name__)

class ListingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.entries = []
        self.active = None
        self.after_link = False

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.active = {"href": dict(attrs).get("href", ""), "label": "", "tail": ""}
            self.entries.append(self.active)
            self.after_link = False

    def handle_endtag(self, tag):
        if tag == "a":
            self.after_link = True

    def handle_data(self, data):
        if self.active is not None:
            self.active["tail" if self.after_link else "label"] += data

def entries(html):
    parser = ListingParser()
    parser.feed(html)
    return parser.entries

def size_info(tail):
    # Nginx/Apache directory index: date time size. K/M/G labels are rounded.
    match = re.search(r"(\d+(?:\.\d+)?)([KMGT]?)\s*$", tail.strip(), re.I)
    if not match:
        return None, None, False
    number, unit = match.groups()
    scale = 1024 ** ("KMGT".find(unit.upper()) + 1) if unit else 1
    return number + unit, round(float(number) * scale), not bool(unit)

def discover(root, client, refresh=False):
    root = prepare(root)
    listing_root = root / "processed" / "listings"
    base = client.listing(BASE_URL, listing_root / "stations.json", refresh)
    stations = set()
    for item in entries(base["html"]):
        url = urljoin(BASE_URL, item["href"])
        suffix = unquote(url.removeprefix(BASE_URL)).rstrip("/")
        if url.startswith(BASE_URL) and STATION_PATTERN.fullmatch(suffix) and not urlparse(url).query:
            stations.add(suffix)
    if not stations:
        raise ValueError("No station directories found; source format may have changed")
    catalog, archives, errors = [], [], []
    for index, station in enumerate(sorted(stations), 1):
        url = f"{BASE_URL}{station}/"
        try:
            page = client.listing(url, listing_root / f"{station}.json", refresh)
            by_year = {}
            for item in entries(page["html"]):
                archive = urljoin(url, item["href"])
                if not archive.startswith(url):
                    continue
                name = unquote(archive.removeprefix(url))
                match = re.fullmatch(re.escape(station) + r"_(\d{4})\.zip", name)
                if not match:
                    continue
                year = int(match[1])
                if year in by_year:
                    raise ValueError(f"Duplicate archive year in listing: {year}")
                label, size, exact = size_info(item["tail"])
                by_year[year] = {
                    "station_id": station, "year": year, "url": archive,
                    "size_label": label, "estimated_bytes": size, "size_is_exact": exact,
                    "listing_fetched_at": page["fetched_at"],
                }
            years = sorted(by_year)
            if not years:
                raise ValueError("No yearly ZIPs found")
            gaps = sorted(set(range(years[0], years[-1] + 1)) - set(years))
            catalog.append({
                "station_id": station, "station_name": None, "latitude": None, "longitude": None,
                "elevation_m": None, "first_year": years[0], "last_year": years[-1],
                "years_available": len(years), "available_years": years, "missing_years": gaps,
                "zip_count": len(years),
                "estimated_archive_bytes": sum(a["estimated_bytes"] or 0 for a in by_year.values()),
                "archives_with_known_size": sum(a["estimated_bytes"] is not None for a in by_year.values()),
                "listing_fetched_at": page["fetched_at"], "discovery_error": None,
            })
            archives.extend(by_year.values())
            LOG.info("Discovered %d/%d %s: %d ZIPs (%d-%d)", index, len(stations), station, len(years), years[0], years[-1])
        except (OSError, ValueError, RuntimeError, http.client.HTTPException) as error:
            client.error("discover-station", url, error)
            errors.append({"station_id": station, "error": str(error)})
            catalog.append({
                "station_id": station, "station_name": None, "latitude": None, "longitude": None,
                "elevation_m": None, "first_year": None, "last_year": None, "years_available": None,
                "available_years": [], "missing_years": [], "zip_count": None,
                "estimated_archive_bytes": None, "archives_with_known_size": None,
                "listing_fetched_at": None, "discovery_error": str(error),
            })
    years = [a["year"] for a in archives]
    summary = {
        "attribution": ATTRIBUTION, "source_url": BASE_URL, "generated_at": utc_now(),
        "station_count": len(stations), "successful_station_count": len(stations) - len(errors),
        "failed_station_count": len(errors), "earliest_year": min(years) if years else None,
        "latest_year": max(years) if years else None, "zip_count": len(archives),
        "estimated_archive_bytes": sum(a["estimated_bytes"] or 0 for a in archives),
        "archives_with_known_size": sum(a["estimated_bytes"] is not None for a in archives),
        "stations_with_missing_years": sum(bool(s["missing_years"]) for s in catalog),
        "missing_station_years": sum(len(s["missing_years"]) for s in catalog),
        "potential_daily_rows_upper_bound": sum(366 if calendar.isleap(y) else 365 for y in years),
        "complete_discovery": not errors,
        "size_note": "Directory K/M/G sizes use 1024-based units and are rounded estimates. Unknown sizes excluded.",
        "gap_note": "Missing yearly ZIPs between each station's first and last listed year; not daily-data completeness.",
        "cache_note": "Each station has its own listing fetch time. Re-run with --refresh for a fresh snapshot.",
    }
    manifest = {"summary": summary, "stations": catalog, "archives": archives, "errors": errors}
    atomic_json(root / "processed" / "discovery.json", manifest)
    write_csv(root / "station_catalog.csv", catalog)
    write_csv(root / "archive_catalog.csv", archives)
    lines = [
        "# ANM archive discovery", "", f"Source: {BASE_URL}", f"Attribution: {ATTRIBUTION}", "",
        f"- Stations: {len(stations)} ({len(errors)} listing failures)",
        f"- Available years: {summary['earliest_year']}–{summary['latest_year']}",
        f"- ZIP archives: {len(archives):,}",
        f"- Estimated compressed bytes: {summary['estimated_archive_bytes']:,} ({summary['estimated_archive_bytes']/1024**2:.1f} MiB)",
        f"- Archives with readable sizes: {summary['archives_with_known_size']:,}",
        f"- Stations with internal missing years: {summary['stations_with_missing_years']}",
        f"- Missing station-years: {summary['missing_station_years']:,}", "",
        summary["size_note"], "", summary["gap_note"], "",
        "Station names/coordinates are enriched from the official ANM locations endpoint in station_catalog.csv. Unmatched values remain NULL; see metadata_report.json.", "",
        "| Station | First | Last | ZIPs | Missing years |",
        "|---|---:|---:|---:|---|",
    ]
    lines += [f"| {s['station_id']} | {s['first_year']} | {s['last_year']} | {s['zip_count']} | {', '.join(map(str, s['missing_years'])) or ('Discovery failed' if s['discovery_error'] else 'None')} |" for s in catalog]
    (root / "processed" / "discovery_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest

def write_csv(path, rows):
    if not rows:
        return
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    for row in rows:
        writer.writerow({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in row.items()})
    temporary = path.with_suffix(".csv.tmp")
    temporary.write_text(output.getvalue(), encoding="utf-8")
    temporary.replace(path)

