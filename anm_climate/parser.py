"""Parse monthly CSVs after their metadata preamble, retaining provenance."""
import csv
import io
import json
import math
import re
from datetime import date
from pathlib import Path
from zipfile import ZipFile
from .config import FIELDS, MEASURES, validate_identity
from .downloader import validate_zip
from .validation import flags_for

# Text missing markers only. No undocumented numeric sentinel is guessed.
MISSING = {"", "na", "n/a", "null", "nan", "none"}

def parser_signature(missing_codes=()):
    return "2;missing_codes=" + json.dumps(sorted(str(c).strip().casefold() for c in missing_codes))


def parse_archive(path, station, year, extracted_dir=None, missing_codes=()):
    validate_identity(station, year)
    validate_zip(path)
    missing_codes = {str(code).strip().casefold() for code in missing_codes}
    result = {"parser_version": parser_signature(missing_codes), "rows": [], "files": [], "rejected_rows": [], "file_issues": [], "exact_duplicate_rows": []}
    with ZipFile(path) as archive:
        for member in sorted(archive.infolist(), key=lambda m: m.filename):
            if member.is_dir():
                continue
            blob = archive.read(member)
            if extracted_dir is not None:
                destination = Path(extracted_dir) / member.filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(blob)  # preserve metadata and source bytes
            if not member.filename.lower().endswith(".csv"):
                result["file_issues"].append({"file": member.filename, "issue": "non_csv_member_preserved"})
                continue
            encoding = "utf-8-sig"
            try:
                text = blob.decode(encoding)
            except UnicodeDecodeError:
                encoding = "cp1250"
                text = blob.decode(encoding)
                result["file_issues"].append({"file": member.filename, "issue": "decoded_cp1250"})
            lines = text.splitlines()
            header_at = None
            delimiter = None
            for i, line in enumerate(lines):
                for sep in (",", ";", "\t"):
                    cols = [value.strip().casefold() for value in next(csv.reader([line], delimiter=sep))]
                    if len(cols) == len(set(cols)) and set(FIELDS).issubset(cols):
                        header_at, delimiter = i, sep
                        break
                if header_at is not None:
                    break
            if header_at is None:
                raise ValueError(f"CSV header not found: {member.filename}")
            reader = csv.DictReader(io.StringIO("\n".join(lines[header_at:])), delimiter=delimiter)
            reader.fieldnames = [name.strip().casefold() for name in reader.fieldnames]
            month_match = re.fullmatch(re.escape(station) + rf"_{year}_(\d{{1,2}})\.csv", Path(member.filename).name, flags=re.I)
            expected_month = int(month_match[1]) if month_match else None
            count = 0
            preamble_lines = {line.strip() for line in lines[:header_at] if line.strip()}
            for raw in reader:
                line_number = header_at + reader.line_num
                provenance = {"source_member": member.filename, "source_line": line_number, "raw": raw}
                source_line_text = lines[line_number - 1].strip() if line_number <= len(lines) else ""
                if source_line_text in preamble_lines:
                    continue  # repeated metadata remains byte-for-byte in extracted files
                if all((raw.get(field) or "").strip().casefold() == field for field in FIELDS):
                    result["file_issues"].append({"file": member.filename, "line": line_number,
                                                 "issue": "repeated_metadata_and_header_block"})
                    continue
                if None in raw or any(raw.get(field) is None for field in FIELDS):
                    result["rejected_rows"].append({**provenance, "issue": "incorrect_column_count"})
                    continue
                raw = {k: v.strip() if v is not None else v for k, v in raw.items()}
                provenance["raw"] = raw
                try:
                    day = date(int(raw["an"]), int(raw["luna"]), int(raw["zi"]))
                except (ValueError, TypeError) as error:
                    result["rejected_rows"].append({**provenance, "issue": f"invalid_date:{error}"})
                    continue
                if raw["wsi"] != station or day.year != year or expected_month is not None and day.month != expected_month:
                    result["rejected_rows"].append({**provenance, "issue": "station_year_or_member_month_mismatch"})
                    continue
                row = {"station_id": station, "date": day.isoformat(), **provenance, "quality_flags": []}
                for source, normalized in MEASURES.items():
                    token = raw[source]
                    if token.casefold() in MISSING | missing_codes:
                        value = None
                    else:
                        try:
                            value = float(token.replace(",", ".") if delimiter != "," else token)
                            if not math.isfinite(value):
                                raise ValueError("nonfinite")
                        except ValueError:
                            value = None
                            row["quality_flags"].append(f"{source}:unparseable_or_nonfinite:{token}")
                    row[normalized] = value
                rain = row["precip_mm"]
                row["precip_raw"] = rain
                row["precip_trace"] = None if rain is None else rain == -1
                if rain == -1:
                    row["precip_mm"] = 0.0
                row["quality_flags"].extend(flags_for(row))
                result["rows"].append(row)
                count += 1
            result["files"].append({"file": member.filename, "encoding": encoding, "header_line": header_at + 1,
                                    "delimiter": delimiter, "parsed_rows": count,
                                    "metadata_preamble": "\n".join(lines[:header_at])})
    if not result["files"]:
        raise ValueError("No monthly CSV files found")
    unique_rows = []
    first_by_date = {}
    for row in result["rows"]:
        key = (row["station_id"], row["date"])
        first = first_by_date.get(key)
        if first is not None and row["raw"] == first["raw"]:
            result["exact_duplicate_rows"].append({**row, "duplicate_of_member": first["source_member"],
                                                   "duplicate_of_line": first["source_line"]})
        else:
            unique_rows.append(row)
            first_by_date.setdefault(key, row)
    result["rows"] = unique_rows
    return result

