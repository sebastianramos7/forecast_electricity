# Weather forecasts and next-day electricity prices in Texas (ERCOT)

Python Project, Magistère BFA 2, Université Paris-Dauphine (PSL).

**Research question.** How much do weather forecasts improve the prediction of
next-day electricity prices in Texas (ERCOT), beyond price history, calendar
effects and gas prices?

**Target.** Daily average day-ahead price of the ERCOT Hub Average (`HB_HUBAVG`)
for day J+1, in $/MWh, predicted on day J before 10:00 Texas time (the
day-ahead bid deadline).

## Data sources

| Data | Source | Script |
|---|---|---|
| Day-ahead prices, hourly, `HB_HUBAVG` | ERCOT: annual file NP4-180-ER (Historical DAM Load Zone and Hub Prices) + Public API report NP4-190-CD (DAM Settlement Point Prices) | `src/ercot_prices.py` |
| Weather forecasts (not observations) | Open-Meteo Previous Runs API, GFS model, 10 points in Texas | `src/weather_forecasts.py` |
| Natural gas | Henry Hub: NYMEX futures `NG=F` (Yahoo Finance) and EIA daily spot `RNGWHHD` | `src/gas_prices.py` |
| Holidays | Python package `holidays` (US + Texas) | `src/build_dataset.py` |

Known coverage limits:
- The ERCOT Public API only serves filtered queries from mid-December 2023, so
  earlier years come from the annual NP4-180-ER files.
- Open-Meteo archives most previous-run forecasts from January 2024; only GFS
  2 m temperature goes back to March 2021. `weather_forecasts.py` prints the
  first available date of each variable.

**Study period.** Raw data start in March 2021, but the main analysis uses
decision dates from **2024-02-16** (`MODEL_START_DATE` in `src/config.py`),
the first day with all weather forecasts available (about 1,000 days). The
2021-2024 data are used only for a temperature-only robustness check.

## Setup

```bash
git clone <repo-url>
cd projet-ercot
conda env create -f environment.yml      # or: pip install -r requirements.txt
conda activate projet-ercot
cp .env.example .env                      # then fill in your ERCOT credentials
```

ERCOT credentials: create a free account on https://apiexplorer.ercot.com and
subscribe to the Public API to get a subscription key. The `.env` file is in
`.gitignore` and is never pushed.

## Reproduce the data

Run from the repository root:

```bash
python src/ercot_prices.py        # data/raw/ercot_dam_hourly.csv
python src/weather_forecasts.py   # data/raw/weather_forecast_hourly.csv.gz
python src/gas_prices.py          # data/raw/gas_henry_hub_daily.csv
python src/build_dataset.py       # data/processed/dataset_daily.csv
```

## No look-ahead rules

Every feature of row J must be known on day J before 10:00 CT:
- prices of J and earlier only (the DAM price of J was set on J-1);
- gas close of J-1 at the latest (the gas market has not closed at 10:00 on J);
- weather forecasts made 48 h before the valid hour (`_previous_day2`): for
  J+1 afternoon hours, a 24 h-ahead forecast was issued after the 10:00 cutoff
  on J, so `_previous_day1` is kept only as a robustness check;
- calendar of J+1 is always known.

## Repository structure

```
projet-ercot/
├── data/
│   ├── raw/          downloaded data (as returned by the sources)
│   └── processed/    modelling table
├── notebooks/        exploration and models
├── src/              collection and dataset scripts
├── .env.example      template for ERCOT credentials (.env itself is ignored)
├── environment.yml
└── requirements.txt
```
