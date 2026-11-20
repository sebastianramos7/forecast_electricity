"""Download archived weather FORECASTS (not observed weather) from Open-Meteo.

API: Previous Runs API (https://open-meteo.com/en/docs/previous-runs-api), free,
no key. A variable named `temperature_2m_previous_day2` is the value that was
forecast 48 hours before the valid hour. Using day 2 means every hour of J+1
was forecast before the 10:00 CT decision time on day J (no look-ahead bias).

Coverage warning (from Open-Meteo's docs): most variables are archived from
January 2024 only; GFS 2 m temperature goes back to March 2021. The script
prints the first non-empty date of every column so you can check.

Output: data/raw/weather_forecast_hourly.csv.gz
    time (local Texas time), point, <variable>_previous_dayN ...

Usage:
    python src/weather_forecasts.py
    python src/weather_forecasts.py --points amarillo --start 2024-01-01   # quick test
"""

import argparse
import time
from datetime import date, timedelta

import pandas as pd
import requests

from config import (LEAD_DAYS, RAW_DIR, START_DATE, TIMEZONE, WEATHER_MODEL,
                    WEATHER_POINTS, WEATHER_VARIABLES)

API_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
OUT_FILE = RAW_DIR / "weather_forecast_hourly.csv.gz"
CACHE_DIR = RAW_DIR / "weather"


def hourly_columns() -> list[str]:
    return [f"{v}_previous_day{d}" for v in WEATHER_VARIABLES for d in LEAD_DAYS]


def fetch_point(lat: float, lon: float, start: date, end: date) -> pd.DataFrame:
    """One API call: hourly forecasts for one point between two dates."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(hourly_columns()),
        "models": WEATHER_MODEL,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "timezone": TIMEZONE,
        "wind_speed_unit": "ms",   # m/s instead of km/h
    }
    for attempt in range(5):
        r = requests.get(API_URL, params=params, timeout=120)
        if r.status_code == 429:   # too many requests: wait, then retry
            wait = 60 * (attempt + 1)
            print(f"   rate limited, waiting {wait}s")
            time.sleep(wait)
            continue
        if r.status_code == 400:
            raise RuntimeError(f"Open-Meteo error: {r.json().get('reason')}")
        r.raise_for_status()
        break
    df = pd.DataFrame(r.json()["hourly"])
    df["time"] = pd.to_datetime(df["time"])
    return df


def yearly_chunks(start: date, end: date):
    """Split [start, end] into calendar-year pieces (smaller API calls)."""
    cur = start
    while cur <= end:
        stop = min(date(cur.year, 12, 31), end)
        yield cur, stop
        cur = stop + timedelta(days=1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default=START_DATE)
    p.add_argument("--end", default=(date.today() + timedelta(days=2)).isoformat())
    p.add_argument("--points", nargs="*", default=list(WEATHER_POINTS))
    args = p.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    this_year = date.today().year

    frames = []
    for name in args.points:
        pt = WEATHER_POINTS[name]
        for a, b in yearly_chunks(start, end):
            cache = CACHE_DIR / f"{name}_{a}_{b}.csv"
            if cache.exists() and a.year < this_year:   # past years never change
                df = pd.read_csv(cache, parse_dates=["time"])
            else:
                print(f"[weather] {name}: {a} -> {b}")
                df = fetch_point(pt["lat"], pt["lon"], a, b)
                df.to_csv(cache, index=False)
                time.sleep(1)
            df["point"] = name
            frames.append(df)

    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(["point", "time"], keep="last").sort_values(["point", "time"])
    out.to_csv(OUT_FILE, index=False)
    print(f"\nSaved {len(out):,} rows to {OUT_FILE}")

    # Coverage check: first date with data, and share of missing values
    print("\nFirst non-empty date and % missing, by variable (all points pooled):")
    for col in hourly_columns():
        s = out.dropna(subset=[col])
        first = s["time"].min().date() if len(s) else "never"
        print(f"  {col:40s} first: {first}   missing: {out[col].isna().mean():.1%}")


if __name__ == "__main__":
    main()
