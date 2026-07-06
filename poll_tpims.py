"""Park Alive — TPIMS poller (5 open MAASTO feeds, no registration).

Runs on GitHub Actions (US runners). Fetches dynamic+static TPIMS feeds for
IL, IN, KY, MN, OH, normalizes rows, appends to daily CSV, keeps one raw
snapshot per state per day. Veracity rule: store what the feed says, never invent.
"""

from __future__ import annotations

import csv
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

FEEDS = {
    "IL": {
        "dynamic": "https://truckparking.travelmidwest.com/TPIMS_Dynamic.json",
        "static": "https://truckparking.travelmidwest.com/TPIMS_Static.json",
    },
    "IN": {
        "dynamic": "https://content.trafficwise.org/json/tpims.json",
        "static": "https://content.trafficwise.org/json/rest_area.json",
    },
    "KY": {
        "dynamic": "http://www.trimarc.org/dat/tpims/TPIMS_Dynamic.json",
        "static": "http://www.trimarc.org/dat/tpims/TPIMS_Static.json",
    },
    "MN": {
        "dynamic": "http://iris.dot.state.mn.us/iris/TPIMS_dynamic",
        "static": "http://iris.dot.state.mn.us/iris/TPIMS_static",
    },
    "OH": {
        "dynamic": "http://ipsens.webhop.biz/ODOT/MaastoDataFeeds/TPIMS/Dynamic",
        "static": "http://ipsens.webhop.biz/ODOT/MaastoDataFeeds/TPIMS/Static",
    },
}

HEADERS = {"User-Agent": "ParkAlive/1.0 (parkalive.app@gmail.com; TPIMS research poller)"}

# Normalized columns (TPIMS Data Exchange Spec V2.2, defensive extraction)
COLUMNS = [
    "polled_at_utc", "state", "site_id", "time_stamp", "reported_available",
    "capacity", "trend", "open", "trust_data", "low_threshold",
]


def _get(d: dict, *names):
    """Case/format-insensitive field lookup."""
    low = {k.lower().replace("_", ""): v for k, v in d.items()}
    for n in names:
        v = low.get(n.lower().replace("_", ""))
        if v is not None:
            return v
    return None


def _rows_from_payload(payload) -> list[dict]:
    if isinstance(payload, dict):
        for key in ("parkingAreaList", "sites", "data", "results", "features"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            payload = [payload]
    return [r for r in payload if isinstance(r, dict)]


def fetch(url: str) -> tuple[object | None, str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=60)
        r.raise_for_status()
        return r.json(), ""
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def main() -> int:
    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    day_dir = DATA / day
    day_dir.mkdir(parents=True, exist_ok=True)

    csv_path = day_dir / "tpims_dynamic.csv"
    new_file = not csv_path.exists()
    errors: list[str] = []
    total = 0

    with csv_path.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        if new_file:
            w.writeheader()

        for state, urls in FEEDS.items():
            payload, err = fetch(urls["dynamic"])
            if payload is None:
                errors.append(f"{state} dynamic: {err}")
                continue

            # one raw snapshot per state per day (first successful poll)
            raw_path = day_dir / f"raw_{state}_dynamic.json.gz"
            if not raw_path.exists():
                with gzip.open(raw_path, "wt") as gz:
                    json.dump(payload, gz)

            for r in _rows_from_payload(payload):
                w.writerow({
                    "polled_at_utc": stamp,
                    "state": state,
                    "site_id": _get(r, "siteId", "id", "site"),
                    "time_stamp": _get(r, "timeStamp", "timestamp", "lastUpdated"),
                    "reported_available": _get(r, "reportedAvailable", "available", "availableSpaces", "spacesAvailable"),
                    "capacity": _get(r, "capacity", "totalSpaces"),
                    "trend": _get(r, "trend"),
                    "open": _get(r, "open", "isOpen"),
                    "trust_data": _get(r, "trustData", "trust"),
                    "low_threshold": _get(r, "lowThreshold"),
                })
                total += 1

            # static feed: refresh once per day
            static_path = day_dir / f"static_{state}.json.gz"
            if not static_path.exists():
                spayload, serr = fetch(urls["static"])
                if spayload is not None:
                    with gzip.open(static_path, "wt") as gz:
                        json.dump(spayload, gz)
                elif serr:
                    errors.append(f"{state} static: {serr}")

    log = day_dir / "poll_log.txt"
    with log.open("a") as fh:
        fh.write(f"{stamp} rows={total} errors={'; '.join(errors) or 'none'}\n")

    print(f"{stamp} — {total} rows appended. Errors: {errors or 'none'}")
    # Exit 0 even with partial errors: we want the commit of whatever succeeded.
    return 0 if total > 0 or not errors else 1


if __name__ == "__main__":
    sys.exit(main())
