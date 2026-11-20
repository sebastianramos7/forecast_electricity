"""Download ERCOT day-ahead (DAM) hourly prices for the Hub Average (HB_HUBAVG).

Two official ERCOT sources, because neither covers the whole period alone:

1. NP4-180-ER "Historical DAM Load Zone and Hub Prices": one file per calendar
   year (zip -> xlsx, one sheet per month). Public, no login needed.
   Used for 2021 -> last complete year.
2. NP4-190-CD "DAM Settlement Point Prices" through the ERCOT Public API
   (account + subscription key on apiexplorer.ercot.com). The API only serves
   filtered queries from mid-December 2023, so it is used for recent days.

Output: data/raw/ercot_dam_hourly.csv, one row per delivery hour:
    delivery_date, hour_ending (1-24), repeated_hour (DST fall-back), price ($/MWh)

Usage:
    python src/ercot_prices.py                 # annual files + API for recent days
    python src/ercot_prices.py --no-api        # annual files only
    python src/ercot_prices.py --api-only --start 2024-01-01
"""

import argparse
import io
import os
import time
import zipfile
from datetime import date, timedelta

import pandas as pd
import requests
from dotenv import load_dotenv

from config import RAW_DIR, SETTLEMENT_POINT, START_DATE

# --- ERCOT endpoints ---------------------------------------------------------
# Annual file (MIS public reports). 13060 = report type id of NP4-180-ER.
MIS_DOC_LIST_URL = "https://www.ercot.com/misapp/servlets/IceDocListJsonWS"
MIS_DOWNLOAD_URL = "https://www.ercot.com/misdownload/servlets/mirDownload"
NP4_180_ER_REPORT_TYPE_ID = 13060

# Public API (token from ERCOT's Azure B2C login, see developer.ercot.com)
TOKEN_URL = (
    "https://ercotb2c.b2clogin.com/ercotb2c.onmicrosoft.com/"
    "B2C_1_PUBAPI-ROPC-FLOW/oauth2/v2.0/token"
)
CLIENT_ID = "fec253ea-0d06-4272-a5e6-b478baeecd70"
API_URL = "https://api.ercot.com/api/public-reports/np4-190-cd/dam_stlmnt_pnt_prices"

HEADERS = {"User-Agent": "Mozilla/5.0 (student project, Universite Paris-Dauphine)"}
OUT_FILE = RAW_DIR / "ercot_dam_hourly.csv"
ANNUAL_DIR = RAW_DIR / "ercot_annual"


# =============================================================================
# 1. Annual files NP4-180-ER
# =============================================================================
def list_annual_files() -> pd.DataFrame:
    """Return the list of NP4-180-ER files posted by ERCOT (one per year)."""
    r = requests.get(
        MIS_DOC_LIST_URL,
        params={"reportTypeId": NP4_180_ER_REPORT_TYPE_ID},
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    docs = r.json()["ListDocsByRptTypeRes"]["DocumentList"]
    rows = [d["Document"] for d in docs]
    out = pd.DataFrame(rows)[["DocID", "FriendlyName", "PublishDate"]]
    # FriendlyName looks like "DAMLZHBSPP_2023" -> extract the year
    out["year"] = out["FriendlyName"].str.extract(r"(\d{4})").astype(int)
    return out.sort_values("year")


def parse_annual_file(content: bytes) -> pd.DataFrame:
    """Read the zip -> xlsx (one sheet per month) and keep HB_HUBAVG."""
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        xlsx_name = [n for n in z.namelist() if n.lower().endswith(".xlsx")][0]
        sheets = pd.read_excel(z.open(xlsx_name), sheet_name=None)  # dict of DataFrames
    df = pd.concat(sheets.values(), ignore_index=True)
    df = df[df["Settlement Point"] == SETTLEMENT_POINT]
    return pd.DataFrame({
        "delivery_date": pd.to_datetime(df["Delivery Date"]).dt.date,
        # "01:00" ... "24:00" -> 1 ... 24
        "hour_ending": df["Hour Ending"].astype(str).str[:2].astype(int),
        "repeated_hour": df["Repeated Hour Flag"].eq("Y"),
        "price": df["Settlement Point Price"].astype(float),
    })


def download_annual(start_year: int, refresh_current_year: bool = True) -> pd.DataFrame:
    """Download every annual file from start_year. Past years are cached."""
    ANNUAL_DIR.mkdir(parents=True, exist_ok=True)
    files = list_annual_files()
    files = files[files["year"] >= start_year]
    this_year = date.today().year
    frames = []
    for _, f in files.iterrows():
        cache = ANNUAL_DIR / f"dam_{SETTLEMENT_POINT}_{f['year']}.csv"
        is_current = f["year"] == this_year
        if cache.exists() and not (is_current and refresh_current_year):
            print(f"[annual] {f['year']}: cached")
            frames.append(pd.read_csv(cache, parse_dates=["delivery_date"]))
            continue
        print(f"[annual] {f['year']}: downloading DocID {f['DocID']} ...")
        r = requests.get(MIS_DOWNLOAD_URL, params={"doclookupId": f["DocID"]},
                         headers=HEADERS, timeout=120)
        r.raise_for_status()
        df = parse_annual_file(r.content)
        df.to_csv(cache, index=False)
        frames.append(pd.read_csv(cache, parse_dates=["delivery_date"]))
        time.sleep(1)  # be polite with ERCOT servers
    return pd.concat(frames, ignore_index=True)


# =============================================================================
# 2. Public API NP4-190-CD
# =============================================================================
def get_token(username: str, password: str) -> str:
    """Get an id_token (valid about 1 hour) from ERCOT's login service."""
    r = requests.post(TOKEN_URL, data={
        "username": username,
        "password": password,
        "grant_type": "password",
        "scope": f"openid {CLIENT_ID} offline_access",
        "client_id": CLIENT_ID,
        "response_type": "id_token",
    }, timeout=30)
    r.raise_for_status()
    return r.json()["id_token"]


def download_api(start: date, end: date) -> pd.DataFrame:
    """Hourly HB_HUBAVG prices between two delivery dates (inclusive)."""
    load_dotenv()
    user = os.getenv("ERCOT_USERNAME")
    pwd = os.getenv("ERCOT_PASSWORD")
    key = os.getenv("ERCOT_SUBSCRIPTION_KEY")
    if not all([user, pwd, key]):
        raise RuntimeError("Missing ERCOT_USERNAME / ERCOT_PASSWORD / "
                           "ERCOT_SUBSCRIPTION_KEY in the .env file")
    headers = {
        "Authorization": f"Bearer {get_token(user, pwd)}",
        "Ocp-Apim-Subscription-Key": key,
    }
    params = {
        "deliveryDateFrom": start.isoformat(),
        "deliveryDateTo": end.isoformat(),
        "settlementPoint": SETTLEMENT_POINT,
        "size": 10000,
        "page": 1,
    }
    rows, total_pages = [], 1
    while params["page"] <= total_pages:
        r = requests.get(API_URL, headers=headers, params=params, timeout=60)
        if r.status_code == 429:          # rate limit: wait and retry
            time.sleep(10)
            continue
        r.raise_for_status()
        js = r.json()
        total_pages = js["_meta"]["totalPages"]
        fields = [f["name"] for f in js["fields"]]
        rows += [dict(zip(fields, row)) for row in js["data"]]
        print(f"[api] page {params['page']}/{total_pages}: {len(js['data'])} rows")
        params["page"] += 1
        time.sleep(2)
    if not rows:
        return pd.DataFrame(columns=["delivery_date", "hour_ending", "repeated_hour", "price"])
    df = pd.DataFrame(rows)
    return pd.DataFrame({
        "delivery_date": pd.to_datetime(df["deliveryDate"]),
        "hour_ending": df["hourEnding"].astype(str).str[:2].astype(int),
        "repeated_hour": df["DSTFlag"].astype(str).str.upper().isin(["Y", "TRUE"]),
        "price": df["settlementPointPrice"].astype(float),
    })


# =============================================================================
# Main
# =============================================================================
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default=START_DATE)
    p.add_argument("--no-api", action="store_true", help="annual files only")
    p.add_argument("--api-only", action="store_true", help="API only (from Dec 2023)")
    args = p.parse_args()
    start = date.fromisoformat(args.start)

    frames = []
    if not args.api_only:
        frames.append(download_annual(start.year))
    if not args.no_api:
        # fill the gap between the last annual date and tomorrow
        last = max(f["delivery_date"].max() for f in frames).date() if frames else start - timedelta(days=1)
        api_start = max(last + timedelta(days=1), start)
        api_end = date.today() + timedelta(days=1)   # DAM for tomorrow is out ~13:30 CT
        if api_start <= api_end:
            print(f"[api] {api_start} -> {api_end}")
            frames.append(download_api(api_start, api_end))

    df = pd.concat(frames, ignore_index=True)
    df["delivery_date"] = pd.to_datetime(df["delivery_date"]).dt.date
    df = df[df["delivery_date"] >= start]
    df = (df.drop_duplicates(["delivery_date", "hour_ending", "repeated_hour"], keep="last")
            .sort_values(["delivery_date", "hour_ending", "repeated_hour"]))
    df.to_csv(OUT_FILE, index=False)

    # quick sanity checks
    per_day = df.groupby("delivery_date").size()
    print(f"\nSaved {len(df):,} rows to {OUT_FILE}")
    print(f"Days: {per_day.size}  from {per_day.index.min()} to {per_day.index.max()}")
    print("Hours per day (expect 24, plus one 23 and one 25 per year for DST):")
    print(per_day.value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()
