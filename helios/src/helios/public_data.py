"""Download and validate published aggregate estimates; never generate observations."""
import csv
import datetime as dt
import hashlib
import io
import json
import math
from pathlib import Path
import urllib.request
import zipfile

PRODUCT = "13100905"
SOURCE_URL = "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1310090501"
DOWNLOAD_URL = "https://www150.statcan.gc.ca/n1/tbl/csv/13100905-eng.zip"
METADATA_URL = "https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata"
LICENCE_URL = "https://www.statcan.gc.ca/en/terms-conditions/open-licence"
FIRST_YEAR = 2022
INDICATORS = {
    "access": "Has a regular healthcare provider",
    "diabetes": "Diabetes",
    "blood_pressure": "High blood pressure",
    "mental_health": "Perceived mental health, fair or poor",
    "anxiety": "Anxiety disorder",
    "mood": "Mood disorder",
    "obesity": "Body mass index, adjusted self-reported, obese",
    "smoking": "Current smoker, daily or occasional",
}
FLAGS = {"": "Published", "E": "Use with caution", "F": "Too unreliable to publish",
         "x": "Suppressed for confidentiality", "..": "Not available", "...": "Not applicable"}
REQUIRED = {"REF_DATE", "GEO", "Age group", "Sex", "Indicators", "Characteristics",
            "VALUE", "STATUS", "VECTOR", "UOM", "SCALAR_FACTOR"}


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    temporary.replace(path)


def download(cache, offline=False):
    """Keep an authentic raw source cache. Errors never substitute fabricated data."""
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    archive, meta_path = cache / "statcan.zip", cache / "metadata.json"
    if offline:
        if not archive.exists() or not meta_path.exists():
            raise ValueError("No official source cache. Run once online before using --offline.")
        raw = archive.read_bytes()
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    else:
        with urllib.request.urlopen(DOWNLOAD_URL, timeout=120) as response:
            raw = response.read()
        request = urllib.request.Request(METADATA_URL, data=b'[{"productId":13100905}]',
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.load(response)
        if not result or result[0].get("status") != "SUCCESS":
            raise ValueError("Official metadata request failed")
        metadata = result[0]["object"]
        # Validate before replacing a previously working cache.
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if "13100905.csv" not in z.namelist():
                raise ValueError("Official archive is missing its data table")
        if str(metadata.get("productId")) != PRODUCT:
            raise ValueError("Metadata identifies a different table")
        temporary = archive.with_suffix(".tmp")
        temporary.write_bytes(raw)
        temporary.replace(archive)
        atomic_json(meta_path, metadata)
    return raw, metadata


def number(row):
    flag = row["STATUS"]
    if flag not in FLAGS:
        raise ValueError(f"Unknown source quality flag: {flag!r}")
    if flag not in ("", "E") or not row["VALUE"].strip():
        return None
    value = float(row["VALUE"])
    if not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError("Percentage outside the valid range")
    return value


def parse_archive(raw):
    lookup = {label: key for key, label in INDICATORS.items()}
    fields = {"Percent": "value", "Low 95% confidence interval, percent": "low",
              "High 95% confidence interval, percent": "high"}
    grouped, source_rows, seen = {}, 0, set()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        with z.open("13100905.csv") as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
            if not REQUIRED.issubset(reader.fieldnames or []):
                raise ValueError("Source schema changed: required columns are missing")
            for row in reader:
                source_rows += 1
                if (row["Indicators"] not in lookup or row["Characteristics"] not in fields
                        or int(row["REF_DATE"]) < FIRST_YEAR):
                    continue
                if row["UOM"] != "Percent" or row["SCALAR_FACTOR"] != "units":
                    raise ValueError("Unexpected percentage units or scaling")
                key = (row["REF_DATE"], row["GEO"], row["Age group"], row["Sex"], lookup[row["Indicators"]])
                field = fields[row["Characteristics"]]
                if (key, field) in seen:
                    raise ValueError("Duplicate source estimate")
                seen.add((key, field))
                record = grouped.setdefault(key, dict(year=key[0], geography=key[1], age=key[2],
                                                      sex=key[3], indicator=key[4]))
                record[field] = number(row)
                record[field + "_status"] = row["STATUS"]
                record[field + "_vector"] = row["VECTOR"]
    rows = []
    for key, record in sorted(grouped.items()):
        if not all(field in record for field in fields.values()):
            raise ValueError("An estimate or confidence interval row is missing")
        value, low, high = record["value"], record["low"], record["high"]
        if value is None:
            # Suppressed estimates cannot leak through interval bounds.
            record["low"] = record["high"] = None
            record["quality"] = "unavailable"
        elif low is None or high is None:
            record["quality"] = "caution"
        elif not low <= value <= high:
            raise ValueError("Confidence interval does not contain the source estimate")
        else:
            record["quality"] = "caution" if any(record[f + "_status"] == "E" for f in fields.values()) else "published"
        rows.append(record)
    if not rows or {r["indicator"] for r in rows} != set(INDICATORS):
        raise ValueError("Source does not contain all governed indicators")
    return rows, source_rows


def build_payload(raw, metadata):
    rows, source_rows = parse_archive(raw)
    notes = [{"id": n["footnoteId"], "text": n["footnotesEn"], "link": n["link"]}
             for n in metadata.get("footnote", [])]
    dimensions = {key: sorted({r[key] for r in rows}) for key in ("year", "geography", "age", "sex")}
    return {
        "schema_version": 1,
        "source": {
            "publisher": "Statistics Canada", "table": "13-10-0905-01",
            "title": metadata["cubeTitleEn"], "url": SOURCE_URL, "download_url": DOWNLOAD_URL,
            "licence_url": LICENCE_URL, "release_date": metadata["releaseTime"].split("T")[0],
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "first_year": dimensions["year"][0], "latest_year": dimensions["year"][-1],
            "source_rows": source_rows, "notes": notes,
            "attribution": "Adapted from Statistics Canada, Health indicator statistics, annual estimates, "
                           + dimensions["year"][0] + "-" + dimensions["year"][-1]
                           + ". This does not constitute an endorsement by Statistics Canada of this product.",
        },
        "indicators": INDICATORS, "dimensions": dimensions, "flags": FLAGS, "rows": rows,
        "quality": {q: sum(r["quality"] == q for r in rows) for q in ("published", "caution", "unavailable")},
        "limitations": [
            "Published survey estimates, not live clinical events. National estimates exclude the territories.",
            "Adults aged 18 and over. Estimates exclude non-response categories from their denominators.",
            "2022 introduced a redesigned questionnaire and collection method; earlier cycles are excluded here.",
            "The regular healthcare provider question changed in 2024; comparisons with earlier years require caution.",
            "Confidence intervals are the publisher's survey intervals. Population estimates are not respondent counts.",
            "Differences shown are descriptive; no causal or statistical-significance claims are inferred.",
        ],
    }
