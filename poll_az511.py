"""Publish Arizona rest-area truck counts. The developer key stays in the environment."""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENDPOINT = "https://az511.com/api/v2/get/restareas"
OUTPUT = Path("data/az511_latest.json")


def select_sites(rows: list[dict], polled_at: str) -> dict:
    sites = []
    for row in rows:
        if str(row.get("Status") or "").strip().lower() != "open":
            continue
        try:
            available = int(str(row["AvailableTruckSpaces"]).strip())
            capacity = int(str(row["TotalTruckSpaces"]).strip())
            latitude = float(row["Latitude"])
            longitude = float(row["Longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if capacity <= 0 or available < 0 or available > capacity:
            continue
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            continue
        name = str(row.get("Name") or "").strip()
        site_id = str(row.get("Id") or "").strip()
        if not name or not site_id:
            continue
        location = str(row.get("Location") or "").strip()
        sites.append(
            {
                "id": site_id,
                "name": name,
                "latitude": latitude,
                "longitude": longitude,
                "location": location,
                "available": available,
                "capacity": capacity,
                "status": "Open",
            }
        )
    return {"source": "Arizona AZ511", "polled_at_utc": polled_at, "sites": sites}


def fetch_rows(api_key: str) -> list[dict]:
    query = urllib.parse.urlencode({"key": api_key, "format": "json"})
    request = urllib.request.Request(
        f"{ENDPOINT}?{query}",
        headers={"User-Agent": "ParkAlive/az511", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError("unexpected_payload")
    return [row for row in payload if isinstance(row, dict)]


def main() -> int:
    api_key = os.environ.get("AZ511_API_KEY", "").strip()
    if not api_key:
        print("missing_secret")
        return 1
    polled_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    document = select_sites(fetch_rows(api_key), polled_at)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"sites={len(document['sites'])} polled_at={polled_at}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
