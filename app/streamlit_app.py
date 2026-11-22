import json
import pathlib
import sys

import joblib
import pandas as pd
import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))      # so the unpickled pipeline can import VenueAverage
from features import PK_CITIES, add_derived  # noqa: E402


@st.cache_resource
def load():
    pipe = joblib.load(ROOT / "models" / "win_pipeline.joblib")
    meta = json.loads((ROOT / "models" / "meta.json").read_text())
    return pipe, meta


def build_row(meta, **kw):
    city = meta["venue_city"].get(kw["venue"], "Unknown")
    row = {
        "legal_balls": kw["overs"] * 6 + kw["balls"], "runs": kw["runs"], "wickets": kw["wickets"],
        "target": kw["target"], "runs_last12": kw["runs12"], "wkts_last12": kw["wkts12"],
        "batting_team": kw["chaser"], "bowling_team": kw["bowler"], "venue": kw["venue"],
        "toss_decision": kw["toss_decision"], "toss_winner_is_chaser": int(kw["toss_chaser"]),
        "in_pakistan": int(city in PK_CITIES),
    }
    row.update({k: kw[k] for k in meta["weather_features"]})
    return add_derived(pd.DataFrame([row]))[meta["feature_columns"]]


st.set_page_config(page_title="PSL Win Probability", layout="centered")
st.title("PSL chase: win probability")
st.caption("Probability that the chasing team wins, from the current match state.")
pipe, meta = load()

with st.form("state"):
    c1, c2 = st.columns(2)
    chaser = c1.selectbox("Chasing team", meta["teams"])
    bowler = c2.selectbox("Bowling team", [t for t in meta["teams"] if t != chaser] or meta["teams"])
    venue = st.selectbox("Venue", meta["venues"])
    c3, c4 = st.columns(2)
    toss_decision = c3.selectbox("Toss decision", ["field", "bat"])
    toss_chaser = c4.checkbox("Chasing team won the toss", value=True)
    target = st.number_input("Target", 40, 300, 170)
    c5, c6, c7 = st.columns(3)
    runs = c5.number_input("Runs scored", 0, 299, 60)
    wickets = c6.number_input("Wickets lost", 0, 9, 2)
    overs = c7.number_input("Overs completed", 0, 19, 8)
    c8, c9, c10 = st.columns(3)
    balls = c8.number_input("Balls in current over", 0, 5, 0)
    runs12 = c9.number_input("Runs, last 12 balls", 0, 72, 12)
    wkts12 = c10.number_input("Wickets, last 12 balls", 0, 4, 0)
    extra = {}
    if "temp_c" in meta["weather_features"]:
        extra["temp_c"] = st.slider("Temperature (C)", 5, 45, 27)
        extra["humidity"] = st.slider("Humidity (%)", 5, 100, 50)
    go = st.form_submit_button("Predict")

if go:
    errors = []
    if bowler == chaser:
        errors.append("Batting and bowling teams must differ.")
    if runs >= target:
        errors.append("Runs scored must be below the target (the chase would be over).")
    if runs12 > runs:
        errors.append("Runs in the last 12 balls cannot exceed the total score.")
    if wkts12 > wickets:
        errors.append("Wickets in the last 12 balls cannot exceed wickets lost.")
    if overs * 6 + balls >= 120:
        errors.append("The innings is over: fewer than 20 overs must be completed.")
    if errors:
        for e in errors:
            st.error(e)
    else:
        args = dict(chaser=chaser, bowler=bowler, venue=venue, toss_decision=toss_decision,
                    toss_chaser=toss_chaser, target=target, runs=runs, wickets=wickets,
                    overs=overs, balls=balls, runs12=runs12, wkts12=wkts12, **extra)
        p = float(pipe.predict_proba(build_row(meta, **args))[:, 1][0])
        st.metric(f"{chaser} win probability", f"{p:.0%}")
        st.progress(p)
        # explanatory chart: how the probability moves with the current score
        grid = list(range(max(0, runs - 40), min(target - 1, runs + 40) + 1, 2))
        curve = pd.DataFrame({
            "Runs scored so far": grid,
            "Win probability": [float(pipe.predict_proba(
                build_row(meta, **{**args, "runs": r, "runs12": min(runs12, r)}))[:, 1][0]) for r in grid],
        }).set_index("Runs scored so far")
        st.subheader("What-if: same situation, different score")
        st.line_chart(curve)
        st.caption(f"Model: {meta['model']}. Trained on PSL seasons up to the validation period.")
