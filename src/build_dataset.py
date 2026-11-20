"""Build the modelling table: one row per decision day J (Texas, before 10:00 CT).

Target: average day-ahead HB_HUBAVG price of day J+1 ($/MWh).

Features (only information known on day J before 10:00 CT):
  Controls (no weather)
    price_d0      average DAM price of J (set on J-1)
    price_d6      average DAM price of J-6 (same weekday as J+1)
    price_ma7     average DAM price over J-6 ... J
    gas_futures / gas_spot   Henry Hub close of the last trading day <= J-1
    dow_target    weekday of J+1 (0 = Monday)
    holiday_target   1 if J+1 is a US or Texas holiday
  Weather forecasts for J+1 (suffix _d2 = made 48h ahead, _d1 = 24h ahead)
    wind_mean     mean 100 m wind speed (m/s), wind points
    solar_sum     daily sum of shortwave radiation (Wh/m2), solar points
    temp_mean, temp_max   population-weighted temperature (C)
    cdd, hdd      cooling / heating degree-days, base 18 C
    humidity_houston      mean relative humidity in Houston (%)

Output: data/processed/dataset_daily.csv
Usage:  python src/build_dataset.py
"""

import holidays
import pandas as pd

from config import LEAD_DAYS, POPULATION_WEIGHTS, PROCESSED_DIR, RAW_DIR, WEATHER_POINTS

BASE_TEMP = 18.0


# --- Prices -----------------------------------------------------------------
def daily_prices() -> pd.Series:
    h = pd.read_csv(RAW_DIR / "ercot_dam_hourly.csv", parse_dates=["delivery_date"])
    # mean over all hours of the day -> also works for 23h and 25h DST days
    d = h.groupby("delivery_date")["price"].mean()
    d.index.name = "date"
    return d.asfreq("D")   # full calendar, a missing day shows up as NaN


# --- Gas ----------------------------------------------------------------------
def gas_known_on(calendar: pd.DatetimeIndex) -> pd.DataFrame:
    g = pd.read_csv(RAW_DIR / "gas_henry_hub_daily.csv", parse_dates=["date"], index_col="date")
    g = g.reindex(g.index.union(calendar)).sort_index().ffill()  # weekends/holidays: last close
    return g.shift(1).reindex(calendar)                         # value of J-1 for row J


# --- Weather ------------------------------------------------------------------
def daily_weather(lead: int) -> pd.DataFrame:
    """Daily weather forecast features indexed by VALID date D."""
    w = pd.read_csv(RAW_DIR / "weather_forecast_hourly.csv.gz", parse_dates=["time"])
    w["date"] = w["time"].dt.normalize()
    sfx = f"_previous_day{lead}"
    roles = {k: v["role"] for k, v in WEATHER_POINTS.items()}
    w["role"] = w["point"].map(roles)

    out = pd.DataFrame()

    wind = w[w["role"] == "wind"].groupby(["date", "point"])[f"wind_speed_100m{sfx}"].mean()
    out["wind_mean"] = wind.groupby("date").mean()

    # min_count=20: a day with too few hours is set to NaN instead of a fake low sum
    solar = (w[w["role"] == "solar"].groupby(["date", "point"])[f"shortwave_radiation{sfx}"]
             .sum(min_count=20))
    out["solar_sum"] = solar.groupby("date").mean()

    dem = w[w["role"] == "demand"]
    t = dem.groupby(["date", "point"])[f"temperature_2m{sfx}"].agg(["mean", "max"])
    weights = pd.Series(POPULATION_WEIGHTS)
    for stat in ["mean", "max"]:
        piv = t[stat].unstack("point")                 # rows = date, columns = city
        # weighted average over the cities that have a value that day
        num = (piv * weights).sum(axis=1, min_count=1)
        den = piv.notna().mul(weights).sum(axis=1)
        out[f"temp_{stat}"] = num / den
    out["cdd"] = (out["temp_mean"] - BASE_TEMP).clip(lower=0)
    out["hdd"] = (BASE_TEMP - out["temp_mean"]).clip(lower=0)

    hum = w[w["point"] == "houston"].groupby("date")[f"relative_humidity_2m{sfx}"].mean()
    out["humidity_houston"] = hum

    return out.add_suffix(f"_d{lead}")


# --- Assemble -------------------------------------------------------------------
def main():
    price = daily_prices()
    cal = price.index

    df = pd.DataFrame(index=cal)
    df["target_date"] = cal + pd.Timedelta(days=1)
    df["target"] = price.shift(-1)                    # price of J+1
    df["price_d0"] = price                            # price of J
    df["price_d6"] = price.shift(6)                   # price of J-6
    df["price_ma7"] = price.rolling(7).mean()         # J-6 ... J (no J+1 inside)

    df = df.join(gas_known_on(cal))

    years = range(cal.min().year, cal.max().year + 2)
    tx_holidays = holidays.US(state="TX", years=years)
    df["dow_target"] = df["target_date"].dt.dayofweek
    df["holiday_target"] = df["target_date"].dt.date.map(lambda d: int(d in tx_holidays))

    # weather is indexed by valid date D = J+1 -> join on target_date
    for lead in LEAD_DAYS:
        wx = daily_weather(lead)
        df = df.join(wx, on="target_date")

    df = df.dropna(subset=["target"])
    df.index.name = "date"
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = PROCESSED_DIR / "dataset_daily.csv"
    df.to_csv(out)

    print(f"Saved {len(df):,} rows x {df.shape[1]} columns to {out}")
    print(f"Period: {df.index.min().date()} -> {df.index.max().date()}")
    print("\nShare of missing values by column:")
    print(df.isna().mean().map("{:.1%}".format).to_string())


if __name__ == "__main__":
    main()
