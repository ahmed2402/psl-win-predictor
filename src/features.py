"""Feature definitions shared by training and the Streamlit app (prevents train/serve skew)."""
import numpy as np
import pandas as pd

PK_CITIES = {"Lahore", "Karachi", "Rawalpindi", "Multan", "Islamabad", "Faisalabad"}

# Raw state columns produced by build_dataset.py / entered in the app
RAW_STATE = ["legal_balls", "runs", "wickets", "target", "runs_last12", "wkts_last12"]

NUMERIC = [
    "over", "ball_in_over", "runs", "wickets", "balls_left", "wickets_left",
    "runs_needed", "target", "crr", "rrr", "rr_gap", "runs_last12", "wkts_last12",
    "is_powerplay", "is_death", "toss_winner_is_chaser", "in_pakistan",
    "venue_avg_first",  # added inside the Pipeline by VenueAverage
]
WEATHER = ["temp_c", "humidity", "dew_point_c"]  # second source (Open-Meteo)
CATEGORICAL = ["batting_team", "bowling_team", "venue", "toss_decision"]


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
