"""Optional second source: evening temperature and humidity per match city and date (Open-Meteo, CC BY 4.0)."""
import pathlib
import time

import pandas as pd
import requests

STATES = pathlib.Path("data/processed/ball_states.csv")
OUT = pathlib.Path("data/external/weather.csv")
API = "https://archive-api.open-meteo.com/v1/archive"

# Add any city that shows up in your data. Check with: df["city"].unique()
COORDS = {
    "Lahore": (31.52, 74.36), "Karachi": (24.86, 67.01), "Rawalpindi": (33.60, 73.04),
    "Multan": (30.16, 71.52), "Dubai": (25.20, 55.27), "Sharjah": (25.35, 55.42),
    "Abu Dhabi": (24.45, 54.38),
}


def fetch_city(city, lat, lon, start, end):
    params = dict(latitude=lat, longitude=lon, start_date=start, end_date=end,
                  hourly="temperature_2m,relative_humidity_2m", timezone="auto")
    for attempt in range(5):                               # retry politely on rate limits / server errors
        r = requests.get(API, params=params, timeout=60)
        status = getattr(r, "status_code", 200)
        if status == 429 or status >= 500:
            time.sleep(2 ** attempt)
            continue
        break
    r.raise_for_status()
    h = pd.DataFrame(r.json()["hourly"])
    h["time"] = pd.to_datetime(h["time"])
    h = h[h["time"].dt.hour.between(16, 22)]               # evening, when matches are played
    d = h.groupby(h["time"].dt.normalize()).agg(
        temp_c=("temperature_2m", "mean"), humidity=("relative_humidity_2m", "mean")).reset_index()
    d.columns = ["date", "temp_c", "humidity"]
    d.insert(0, "city", city)
    return d


def main():
    df = pd.read_csv(STATES, parse_dates=["date"], usecols=["city", "date"]).drop_duplicates()
    parts = []
    for city, g in df.groupby("city"):
        if city not in COORDS:
            print("No coordinates for", city, "- add it to COORDS")
            continue
        for year, gy in g.groupby(g["date"].dt.year):      # one small request per city per year
            parts.append(fetch_city(city, *COORDS[city], gy["date"].min().date(), gy["date"].max().date()))
            time.sleep(0.3)
    out = pd.concat(parts).drop_duplicates(["city", "date"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(len(out), "city-days saved to", OUT)


if __name__ == "__main__":
    main()
