"""Shared settings for the data collection scripts."""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

# ---------------------------------------------------------------------------
# Study period and market conventions
# ---------------------------------------------------------------------------
START_DATE = "2021-03-01"          # just after Winter Storm Uri (Feb 2021)
# Main analysis period (decision dates J). Open-Meteo's Previous Runs archive
# has 100 m wind forecasts only from 2024-02-17 and solar from 2024-01-20,
# so the main study starts when every weather variable is available.
# Data from START_DATE is kept for a temperature-only robustness check.
MODEL_START_DATE = "2024-02-16"
TIMEZONE = "America/Chicago"       # ERCOT runs on Central Prevailing Time
SETTLEMENT_POINT = "HB_HUBAVG"     # ERCOT Hub Average

# ---------------------------------------------------------------------------
# Weather forecast points (latitude, longitude)
# role = which mechanism the point stands for (see project doc, section 7)
# ---------------------------------------------------------------------------
WEATHER_POINTS = {
    # Wind (supply)
    "abilene":        {"lat": 32.45, "lon": -99.73,  "role": "wind"},
    "sweetwater":     {"lat": 32.47, "lon": -100.41, "role": "wind"},
    "amarillo":       {"lat": 35.22, "lon": -101.83, "role": "wind"},
    "corpus_christi": {"lat": 27.80, "lon": -97.40,  "role": "wind"},
    # Solar (supply)
    "midland":        {"lat": 32.00, "lon": -102.08, "role": "solar"},
    "fort_stockton":  {"lat": 30.89, "lon": -102.88, "role": "solar"},
    # Temperature (demand)
    "houston":        {"lat": 29.76, "lon": -95.37,  "role": "demand"},
    "dallas":         {"lat": 32.78, "lon": -96.80,  "role": "demand"},
    "san_antonio":    {"lat": 29.42, "lon": -98.49,  "role": "demand"},
    "austin":         {"lat": 30.27, "lon": -97.74,  "role": "demand"},
}

# Population weights for the demand points: 2020 Census metro (MSA) population,
# in millions. Open modelling choice (project doc, section 11) - change if needed.
POPULATION_WEIGHTS = {
    "dallas": 7.64,       # Dallas-Fort Worth-Arlington
    "houston": 7.12,      # Houston-The Woodlands-Sugar Land
    "san_antonio": 2.56,  # San Antonio-New Braunfels
    "austin": 2.28,       # Austin-Round Rock-Georgetown
}

# Open-Meteo weather model and variables
WEATHER_MODEL = "gfs_global"
WEATHER_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_100m",
    "shortwave_radiation",
]
# Lead times to download. previous_day2 = forecast made 48h before the valid
# hour, so every hour of J+1 was forecast before the 10:00 CT cutoff on day J.
# previous_day1 is kept for robustness checks only (it can leak for J+1
# afternoon hours: those 24h-ahead forecasts were made after 10:00 on day J).
LEAD_DAYS = [1, 2]

# Henry Hub natural gas
GAS_TICKER = "NG=F"   # front-month NYMEX futures on Yahoo Finance
