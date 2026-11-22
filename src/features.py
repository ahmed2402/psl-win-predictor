"""Feature definitions shared by training and the Streamlit app (prevents train/serve skew)."""
import numpy as np
import pandas as pd

PK_CITIES = {"Lahore", "Karachi", "Rawalpindi", "Multan", "Islamabad", "Faisalabad"}
# Every city in the Cricsheet data (checked 2026-11-22). Used by weather.py (history) and the API (live dew).
COORDS = {
    "Lahore": (31.52, 74.36), "Karachi": (24.86, 67.01), "Rawalpindi": (33.60, 73.04),
    "Multan": (30.16, 71.52), "Dubai": (25.20, 55.27), "Sharjah": (25.35, 55.42),
    "Abu Dhabi": (24.45, 54.38),
}

# Model inputs chosen from the EDA decision table (notebooks/01_eda.ipynb).
# The dataset keeps all 25 candidate features; dropped ones were redundant, drifting or memorisable.
# Venue, target and toss were tested and dropped: their effect is already in the live state
# (target is inside runs_needed/rrr), and venue behaviour drifts between eras (EDA section 11).
NUMERIC = [
    "balls_left", "runs_needed", "wickets", "rrr", "crr", "runs_last12", "wkts_last12",
    "dew_point_c",  # second data source (Open-Meteo); dew helps chasing sides at night
]
RATE_CAP = 36.0  # six off every ball: above this the chaser never won (EDA section 3)


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Compute derived match-state columns from the raw ones."""
    df = df.copy()
    df["over"] = df["legal_balls"] // 6
    df["ball_in_over"] = df["legal_balls"] % 6
    df["balls_left"] = 120 - df["legal_balls"]
    df["wickets_left"] = 10 - df["wickets"]
    df["runs_needed"] = df["target"] - df["runs"]
    df["crr"] = np.where(df["legal_balls"] > 0, df["runs"] * 6 / df["legal_balls"].clip(lower=1), 0.0)
    df["rrr"] = df["runs_needed"] * 6 / df["balls_left"].clip(lower=1)
    df["rr_gap"] = df["crr"] - df["rrr"]
    df["is_powerplay"] = (df["over"] < 6).astype(int)
    df["is_death"] = (df["over"] >= 16).astype(int)
    return df
