"""Download Henry Hub natural gas prices (daily).

Two sources (open modelling choice, project doc section 11):
  - "futures" (default): NYMEX front-month futures NG=F from Yahoo Finance (yfinance)
  - "spot": EIA Henry Hub daily spot price, series RNGWHHD (official US
    government data, https://www.eia.gov/dnav/ng/hist/rngwhhdD.htm)

Output: data/raw/gas_henry_hub_daily.csv  (date, gas_futures and/or gas_spot, $/MMBtu)
Only closes are stored here. The "close of J-1" shift is done later, when the
dataset is built, so the raw file stays raw.

Usage:
    python src/gas_prices.py                # both sources
    python src/gas_prices.py --source futures
"""

import argparse

import pandas as pd
import requests
import yfinance as yf

from config import GAS_TICKER, RAW_DIR, START_DATE

EIA_XLS_URL = "https://www.eia.gov/dnav/ng/hist_xls/RNGWHHDd.xls"
OUT_FILE = RAW_DIR / "gas_henry_hub_daily.csv"


def get_futures(start: str) -> pd.Series:
    hist = yf.Ticker(GAS_TICKER).history(start=start, auto_adjust=False)
    s = hist["Close"]
    s.index = s.index.tz_localize(None).normalize()   # keep the trading date only
    return s.rename("gas_futures")


def get_spot(start: str) -> pd.Series:
    r = requests.get(EIA_XLS_URL, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    # Sheet "Data 1": 2 title rows, then Date | price
    df = pd.read_excel(r.content, sheet_name="Data 1", skiprows=2)
    df.columns = ["date", "gas_spot"]
    df["date"] = pd.to_datetime(df["date"])
    s = df.set_index("date")["gas_spot"]
    return s[s.index >= start]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default=START_DATE)
    p.add_argument("--source", choices=["futures", "spot", "both"], default="both")
    args = p.parse_args()

    series = []
    if args.source in ("futures", "both"):
        series.append(get_futures(args.start))
    if args.source in ("spot", "both"):
        try:
            series.append(get_spot(args.start))
        except Exception as e:  # EIA file unavailable: keep the futures only
            print(f"[gas] EIA spot download failed ({e}); futures only")

    df = pd.concat(series, axis=1).sort_index()
    df.index.name = "date"
    df.to_csv(OUT_FILE)
    print(f"Saved {len(df):,} rows to {OUT_FILE} ({df.index.min().date()} -> {df.index.max().date()})")
    print(df.tail())


if __name__ == "__main__":
    main()
