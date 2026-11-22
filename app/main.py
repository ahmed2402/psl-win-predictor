"""FastAPI backend: serves the HTML front end and predicts the chasing team's win probability."""
import datetime
import json
import logging
import pathlib
import sys
import urllib.request

import joblib
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel, Field, model_validator

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))      # the pickled pipeline references psl_pipeline.clip_rates
from features import COORDS, NUMERIC, add_derived  # noqa: E402

PIPE = joblib.load(ROOT / "models" / "win_pipeline.joblib")
META = json.loads((ROOT / "models" / "meta.json").read_text())
# Training median of dew point, as learned by the pipeline's imputer: used when the live fetch fails.
DEW_MEDIAN = round(float(PIPE.named_steps["prep"].named_transformers_["num"]
                         .named_steps["imp"].statistics_[NUMERIC.index("dew_point_c")]), 1)
FORECAST_API = "https://api.open-meteo.com/v1/forecast"
_dew_cache: dict[tuple[str, str], float] = {}
log = logging.getLogger("uvicorn.error")

app = FastAPI(title="PSL Chase Win Predictor")


def evening_dew(city: str) -> float | None:
    """Today's mean dew point, 16:00-22:00 local time (the same window as the training data).
    Returns None if Open-Meteo can't be reached."""
    # shortcut: "today" is the server's UTC date; fine for a demo, use the city's timezone if ever exact.
    day = datetime.date.today().isoformat()
    if (city, day) in _dew_cache:
        return _dew_cache[(city, day)]
    lat, lon = COORDS[city]
    url = (f"{FORECAST_API}?latitude={lat}&longitude={lon}&hourly=dew_point_2m"
           f"&timezone=auto&start_date={day}&end_date={day}")
    req = urllib.request.Request(url, headers={"User-Agent": "psl-chase-predictor/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            hourly = json.load(r)["hourly"]
    except (OSError, ValueError, KeyError) as e:
        log.warning("Open-Meteo dew fetch failed for %s: %r", city, e)
        return None
    vals = [v for t, v in zip(hourly["time"], hourly["dew_point_2m"]) if 16 <= int(t[11:13]) <= 22 and v is not None]
    if not vals:
        return None
    _dew_cache[(city, day)] = round(sum(vals) / len(vals), 1)
    return _dew_cache[(city, day)]


class MatchState(BaseModel):
    batting_team: str
    bowling_team: str
    city: str
    target: int = Field(ge=1, le=400)
    runs: int = Field(ge=0, le=400)
    wickets: int = Field(ge=0, le=9)
    overs: int = Field(ge=0, le=19, description="completed overs")
    balls: int = Field(ge=0, le=5, description="legal balls in the current over")
    runs_last12: int = Field(ge=0, le=100)
    wkts_last12: int = Field(ge=0, le=9)

    @model_validator(mode="after")
    def check_consistent(self):
        errors = []
        if self.batting_team not in META["teams"] or self.bowling_team not in META["teams"]:
            errors.append("Unknown team.")
        if self.batting_team == self.bowling_team:
            errors.append("Batting and bowling teams must be different.")
        if self.city not in COORDS:
            errors.append(f"City must be one of: {', '.join(COORDS)}.")
        if self.runs >= self.target:
            errors.append("Runs scored must be below the target (otherwise the chase is already won).")
        if self.runs_last12 > self.runs:
            errors.append("Runs in the last 12 balls cannot exceed the total score.")
        if self.wkts_last12 > self.wickets:
            errors.append("Wickets in the last 12 balls cannot exceed wickets lost.")
        if errors:
            raise ValueError(" ".join(errors))
        return self


class CurvePoint(BaseModel):
    runs: int
    win_probability: float


class Contribution(BaseModel):
    feature: str
    value: float
    effect: float   # push on the log-odds vs an average training situation


class Prediction(BaseModel):
    batting_team: str
    win_probability: float
    dew_point_c: float
    dew_source: str
    what_if: list[CurvePoint]
    contributions: list[Contribution]


def model_rows(s: MatchState, dew: float, runs_values: list[int]) -> pd.DataFrame:
    """Raw form fields -> the 8 model inputs, through the same add_derived used to build the training data."""
    raw = pd.DataFrame({"legal_balls": s.overs * 6 + s.balls, "runs": runs_values, "wickets": s.wickets,
                        "target": s.target, "wkts_last12": s.wkts_last12, "dew_point_c": dew,
                        "runs_last12": [min(s.runs_last12, r) for r in runs_values]})
    return add_derived(raw)[NUMERIC].astype(float)


def contributions(row: pd.DataFrame) -> list[Contribution]:
    model = PIPE.named_steps["model"]
    if not hasattr(model, "coef_"):           # only linear models have per-feature effects
        return []
    scaled = PIPE[:-1].transform(row)[0]      # after clipping, imputing and scaling
    return [Contribution(feature=f, value=round(float(v), 2), effect=round(float(c * x), 3))
            for f, v, c, x in zip(NUMERIC, row.iloc[0], model.coef_[0], scaled)]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/meta")
def meta() -> dict:
    return {"teams": META["teams"], "cities": list(COORDS), "model": META["model"],
            "features": NUMERIC, "test_metrics": META["test_metrics"][META["model"]]}


@app.post("/predict")
def predict(state: MatchState) -> Prediction:
    live = evening_dew(state.city)
    dew = live if live is not None else DEW_MEDIAN
    grid = list(range(max(0, state.runs - 30), min(state.target - 1, state.runs + 30) + 1, 2))
    if state.runs not in grid:
        grid = sorted(grid + [state.runs])
    rows = model_rows(state, dew, grid)
    probs = PIPE.predict_proba(rows)[:, 1]
    current = rows.iloc[[grid.index(state.runs)]]
    return Prediction(
        batting_team=state.batting_team,
        win_probability=round(float(probs[grid.index(state.runs)]), 4),
        dew_point_c=dew,
        dew_source="live (Open-Meteo, today 16:00-22:00)" if live is not None
        else "live weather unavailable: training median used",
        what_if=[CurvePoint(runs=r, win_probability=round(float(p), 4)) for r, p in zip(grid, probs)],
        contributions=contributions(current),
    )


app.frontend("/", directory=ROOT / "app" / "static")
