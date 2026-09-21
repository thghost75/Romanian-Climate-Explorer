"""Conservative screening flags; suspicious finite values are retained."""
import calendar
from collections import Counter
from datetime import date, timedelta
from .config import MEASURES

BOUNDS = {
    "tmean_c": (-60, 60), "tmin_c": (-60, 60), "tmax_c": (-60, 60),
    "wind_mean_ms": (0, 100), "pressure_msl_hpa": (850, 1100), "precip_mm": (0, 1000),
}

def flags_for(row):
    flags = []
    for name, (low, high) in BOUNDS.items():
        value = row[name]
        if value is not None and not low <= value <= high:
            flags.append(f"{name}:outside_screening_bounds[{low},{high}]")
    low, high, avg = row["tmin_c"], row["tmax_c"], row["tmean_c"]
    if low is not None and high is not None and low > high:
        flags.append("tmin_above_tmax")
    if low is not None and high is not None and avg is not None and not low <= avg <= high:
        flags.append("tmean_outside_daily_extremes")
    return flags

def summarize(parsed, station, year):
    rows = parsed["rows"]
    dates = Counter(r["date"] for r in rows)
    start, end = date(year, 1, 1), date(year + 1, 1, 1)
    expected = {(start + timedelta(days=i)).isoformat() for i in range((end - start).days)}
    missing = {name: sum(r[name] is None for r in rows) for name in MEASURES.values()}
    minimums = [r["tmin_c"] for r in rows if r["tmin_c"] is not None]
    maximums = [r["tmax_c"] for r in rows if r["tmax_c"] is not None]
    precipitation = [r["precip_mm"] for r in rows if r["precip_mm"] is not None]
    examples = []
    # Include ordinary, trace, missing and suspicious rows when present.
    picks = rows[:3]
    for predicate in (
        lambda r: r["precip_trace"],
        lambda r: any(r[n] is None for n in MEASURES.values()),
        lambda r: bool(r["quality_flags"]),
    ):
        match = next((r for r in rows if predicate(r)), None)
        if match and match not in picks:
            picks.append(match)
    for row in picks:
        examples.append({"source_member": row["source_member"], "source_line": row["source_line"],
                         "raw": row["raw"], "normalized": {k: v for k, v in row.items() if k != "raw"}})
    return {
        "station_id": station, "year": year, "monthly_files": len(parsed["files"]),
        "daily_observations": len(rows), "unique_dates": len(dates),
        "date_start": min(dates) if dates else None, "date_end": max(dates) if dates else None,
        "expected_days": len(expected), "coverage_percent": round(100 * len(expected & dates.keys()) / len(expected), 2),
        "missing_dates": sorted(expected - dates.keys()), "unexpected_dates": sorted(dates.keys() - expected),
        "duplicate_dates": {k: n for k, n in dates.items() if n > 1},
        "min_temperature_c": min(minimums) if minimums else None,
        "max_temperature_c": max(maximums) if maximums else None,
        "precipitation_sum_mm_trace_as_zero": round(sum(precipitation), 3) if precipitation else None,
        "precipitation_observed_days": len(precipitation),
        "trace_precipitation_days": sum(r["precip_trace"] is True for r in rows),
        "missing_values_by_variable": missing,
        "flagged_rows": sum(bool(r["quality_flags"]) for r in rows),
        "flags": dict(Counter(flag for r in rows for flag in r["quality_flags"])),
        "exact_duplicate_source_rows": len(parsed.get("exact_duplicate_rows", [])),
        "exact_duplicate_provenance": parsed.get("exact_duplicate_rows", []),
        "rejected_rows": parsed["rejected_rows"], "file_issues": parsed["file_issues"],
        "raw_vs_normalized_examples": examples,
        "note": "Trace rain contributes zero to the reported sum. Missing rain is excluded; observed-day count is given. Screening is not independent meteorological certification.",
    }

