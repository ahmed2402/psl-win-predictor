"""Second data source: evening temperature, humidity and dew point per match city and date (Open-Meteo, CC BY 4.0)."""
import json
import pathlib
import sys
import time

import pandas as pd
import requests

from build_dataset import RAW_DIR, venue_city

OUT = pathlib.Path("data/external/weather.csv")
API = "https://archive-api.open-meteo.com/v1/archive"

# Every city in the Cricsheet data (checked 2026-11-22). A new city must be added here.
COORDS = {
    "Lahore": (31.52, 74.36), "Karachi": (24.86, 67.01), "Rawalpindi": (33.60, 73.04),
    "Multan": (30.16, 71.52), "Dubai": (25.20, 55.27), "Sharjah": (25.35, 55.42),
    "Abu Dhabi": (24.45, 54.38),
}


def fetch_city(city, lat, lon, start, end):
    params = dict(latitude=lat, longitude=lon, start_date=start, end_date=end,
                  hourly="temperature_2m,relative_humidity_2m,dew_point_2m", timezone="auto")
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
        temp_c=("temperature_2m", "mean"), humidity=("relative_humidity_2m", "mean"),
        dew_point_c=("dew_point_2m", "mean")).reset_index()
    d.columns = ["date", "temp_c", "humidity", "dew_point_c"]
    d.insert(0, "city", city)
    return d


def main():
    infos = [json.loads(f.read_text())["info"] for f in RAW_DIR.glob("*.json")]
    df = pd.DataFrame({"city": [venue_city(i)[1] for i in infos],
                       "date": pd.to_datetime([i["dates"][0] for i in infos])}).drop_duplicates()
    missing = set(df["city"]) - set(COORDS)
    if missing:
        sys.exit(f"No coordinates for {missing}: add them to COORDS")
    parts = []
    for city, g in df.groupby("city"):
        for year, gy in g.groupby(g["date"].dt.year):      # one small request per city per year
            parts.append(fetch_city(city, *COORDS[city], gy["date"].min().date(), gy["date"].max().date()))
            time.sleep(0.3)
    out = pd.concat(parts).drop_duplicates(["city", "date"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(len(out), "city-days saved to", OUT)


if __name__ == "__main__":
    main()
