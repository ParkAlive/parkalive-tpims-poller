"""Park Alive — TPIMS poller + weather logger (US runners, GitHub Actions).

Fetches dynamic+static TPIMS feeds for IL, IN, KY, MN, OH, normalizes rows,
appends to daily CSV, keeps one raw snapshot per state per day. THEN, for each
site, records the CURRENT weather from NWS (api.weather.gov, free) so every
occupancy reading can be paired with the weather of that moment.

Veracity rule: store what the feeds say, never invent.
Weather is fail-soft: if it errors, TPIMS collection is unaffected.
"""

from __future__ import annotations

import csv
import gzip
import json
import sys
import time
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

# Normalized TPIMS columns (Data Exchange Spec V2.2, defensive extraction)
COLUMNS = [
    "polled_at_utc", "state", "site_id", "time_stamp", "reported_available",
    "capacity", "trend", "open", "trust_data", "low_threshold",
]

# --- Weather (NWS) -----------------------------------------------------------
NWS_HEADERS = {
    "User-Agent": "ParkAlive/1.0 (parkalive.app@gmail.com; weather logger)",
    "Accept": "application/geo+json",
}
WEATHER_COLUMNS = [
    "polled_at_utc", "state", "site_id", "lat", "lng", "temp_f", "short_forecast",
    "precip_pct", "wind_mph", "snow", "ice", "is_rain", "is_heavy_rain",
    "state_severe_alert", "m_weather_delta",
]
# Truck-parking-relevant severe events (mirror of engine NWS allow-list).
SEVERE_EVENTS = {
    "Winter Storm Warning", "Ice Storm Warning", "Blizzard Warning",
    "Tornado Warning", "Severe Thunderstorm Warning", "High Wind Warning",
    "Dense Fog Advisory", "Flood Warning",
}
MAX_WEATHER_POINTS = 600  # safety cap on NWS calls per run


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


def _wfetch(url: str) -> object | None:
    try:
        r = requests.get(url, headers=NWS_HEADERS, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception:  # noqa: BLE001
        return None


def _valid_latlng(lat, lng) -> tuple[float, float] | None:
    try:
        la, ln = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    if 15 < la < 72 and -170 < ln < -50:  # plausible continental/AK US
        return la, ln
    return None


def _find_coords(obj) -> tuple[float, float] | None:
    """Recursively search a record for a plausible (lat, lng) pair."""
    if isinstance(obj, dict):
        c = _valid_latlng(_get(obj, "latitude", "lat"),
                          _get(obj, "longitude", "lon", "lng", "long"))
        if c:
            return c
        # GeoJSON point: coordinates = [lng, lat]
        coords = obj.get("coordinates")
        if (isinstance(coords, list) and len(coords) >= 2
                and all(isinstance(x, (int, float)) for x in coords[:2])):
            c = _valid_latlng(coords[1], coords[0])
            if c:
                return c
        for v in obj.values():
            r = _find_coords(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_coords(v)
            if r:
                return r
    return None


def _classify(short: str):
    s = (short or "").lower()
    snow = any(w in s for w in ("snow", "blizzard", "flurr", "wintry"))
    ice = any(w in s for w in ("ice", "freezing", "sleet"))
    heavy = any(w in s for w in ("heavy rain", "thunderstorm", "hail"))
    rain = any(w in s for w in ("rain", "showers", "drizzle"))
    return snow, ice, rain, heavy


def _m_weather_delta(severe, snow, ice, heavy, rain) -> float:
    if severe:
        return 0.20
    if snow or ice:
        return 0.15
    if heavy:
        return 0.10
    if rain:
        return 0.05
    return 0.0


def _load_grid_cache() -> dict:
    p = DATA / "nws_grid_cache.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _save_grid_cache(cache: dict) -> None:
    (DATA / "nws_grid_cache.json").write_text(json.dumps(cache))


def collect_weather(day_dir: Path, stamp: str, present_states: list[str]) -> tuple[int, str]:
    """For each TPIMS site (coords from today's static snapshots), log current NWS
    weather. Returns (rows_written, note). Never raises."""
    # 1) sites with coordinates from static snapshots
    sites: list[tuple[str, str, float, float]] = []  # state, site_id, lat, lng
    for state in present_states:
        sp = day_dir / f"static_{state}.json.gz"
        if not sp.exists():
            continue
        try:
            with gzip.open(sp, "rt") as gz:
                payload = json.load(gz)
        except Exception:  # noqa: BLE001
            continue
        for rec in _rows_from_payload(payload):
            coords = _find_coords(rec)
            if not coords:
                continue
            sid = _get(rec, "siteId", "id", "site") or ""
            sites.append((state, str(sid), round(coords[0], 4), round(coords[1], 4)))

    if not sites:
        return 0, "no site coordinates in static feeds"

    # 2) per-state severe alerts (one call per state)
    state_severe: dict[str, bool] = {}
    for state in present_states:
        data = _wfetch(f"https://api.weather.gov/alerts/active?area={state}")
        events = set()
        if isinstance(data, dict):
            for f in data.get("features", []):
                ev = (f.get("properties") or {}).get("event")
                if ev:
                    events.add(ev)
        state_severe[state] = bool(events & SEVERE_EVENTS)
        time.sleep(0.2)

    # 3) unique points -> resolve grid (cached) -> current hourly weather
    cache = _load_grid_cache()
    point_wx: dict[tuple[float, float], dict] = {}
    unique_points = list({(la, ln) for _, _, la, ln in sites})[:MAX_WEATHER_POINTS]
    for la, ln in unique_points:
        key = f"{la},{ln}"
        hourly_url = cache.get(key)
        if not hourly_url:
            pts = _wfetch(f"https://api.weather.gov/points/{la},{ln}")
            if isinstance(pts, dict):
                hourly_url = (pts.get("properties") or {}).get("forecastHourly")
                if hourly_url:
                    cache[key] = hourly_url
            time.sleep(0.2)
        if not hourly_url:
            continue
        hr = _wfetch(hourly_url)
        time.sleep(0.2)
        try:
            per = hr["properties"]["periods"][0]
        except (TypeError, KeyError, IndexError):
            continue
        short = per.get("shortForecast") or ""
        precip = (per.get("probabilityOfPrecipitation") or {}).get("value")
        wind = per.get("windSpeed") or ""
        wind_mph = None
        for tok in str(wind).split():
            if tok.isdigit():
                wind_mph = int(tok)
                break
        point_wx[(la, ln)] = {
            "temp_f": per.get("temperature"),
            "short_forecast": short,
            "precip_pct": precip,
            "wind_mph": wind_mph,
        }
    _save_grid_cache(cache)

    # 4) write one weather row per site
    wx_path = day_dir / "weather.csv"
    new_file = not wx_path.exists()
    written = 0
    with wx_path.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=WEATHER_COLUMNS)
        if new_file:
            w.writeheader()
        for state, sid, la, ln in sites:
            wx = point_wx.get((la, ln))
            if not wx:
                continue
            snow, ice, rain, heavy = _classify(wx["short_forecast"])
            severe = state_severe.get(state, False)
            w.writerow({
                "polled_at_utc": stamp,
                "state": state,
                "site_id": sid,
                "lat": la,
                "lng": ln,
                "temp_f": wx["temp_f"],
                "short_forecast": wx["short_forecast"],
                "precip_pct": wx["precip_pct"],
                "wind_mph": wx["wind_mph"],
                "snow": snow,
                "ice": ice,
                "is_rain": rain,
                "is_heavy_rain": heavy,
                "state_severe_alert": severe,
                "m_weather_delta": _m_weather_delta(severe, snow, ice, heavy, rain),
            })
            written += 1
    return written, f"{len(unique_points)} points, {len(sites)} sites"


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
    present_states: list[str] = []

    with csv_path.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        if new_file:
            w.writeheader()

        for state, urls in FEEDS.items():
            payload, err = fetch(urls["dynamic"])
            if payload is None:
                errors.append(f"{state} dynamic: {err}")
                continue
            present_states.append(state)

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

            # static feed: refresh once per day (also used by the weather step)
            static_path = day_dir / f"static_{state}.json.gz"
            if not static_path.exists():
                spayload, serr = fetch(urls["static"])
                if spayload is not None:
                    with gzip.open(static_path, "wt") as gz:
                        json.dump(spayload, gz)
                elif serr:
                    errors.append(f"{state} static: {serr}")

    # --- weather (fail-soft: never breaks TPIMS collection above) ---
    wx_rows, wx_note = 0, ""
    try:
        wx_rows, wx_note = collect_weather(day_dir, stamp, present_states)
    except Exception as e:  # noqa: BLE001
        wx_note = f"weather error: {type(e).__name__}: {e}"

    log = day_dir / "poll_log.txt"
    with log.open("a") as fh:
        fh.write(
            f"{stamp} rows={total} weather_rows={wx_rows} "
            f"weather=({wx_note}) errors={'; '.join(errors) or 'none'}\n"
        )

    print(f"{stamp} — {total} TPIMS rows, {wx_rows} weather rows. "
          f"weather=({wx_note}) errors={errors or 'none'}")
    return 0 if total > 0 or not errors else 1


if __name__ == "__main__":
    sys.exit(main())
