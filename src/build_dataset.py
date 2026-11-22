"""Turn Cricsheet JSON matches into one row per second-innings ball state."""
import json
import pathlib
import sys
from collections import deque

import pandas as pd

from features import PK_CITIES, add_derived

RAW_DIR = pathlib.Path("data/raw/psl_json")
WEATHER_CSV = pathlib.Path("data/external/weather.csv")
OUT = pathlib.Path("data/processed/ball_states.csv")
NOT_A_WICKET = {"retired hurt", "retired not out"}


def parse_match(path: pathlib.Path):
    m = json.loads(path.read_text())
    info, innings = m["info"], m["innings"]
    winner = info.get("outcome", {}).get("winner")
    if winner is None or len(innings) < 2:          # no result / tie / abandoned
        return []
    inn1, inn2 = innings[0], innings[1]             # ignore super overs
    tgt = inn2.get("target", {})
    if float(tgt.get("overs", 20)) != 20:           # skip rain-shortened (DLS) chases
        return []
    first_total = sum(d["runs"]["total"] for o in inn1["overs"] for d in o["deliveries"])
    target = tgt.get("runs", first_total + 1)
    chaser, bowler_team = inn2["team"], inn1["team"]
    toss = info.get("toss", {})
    city = info.get("city") or "Unknown"
    base = dict(
        match_id=path.stem, date=info["dates"][0], season=str(info["season"]),
        venue=info["venue"], city=city, batting_team=chaser, bowling_team=bowler_team,
        toss_decision=toss.get("decision", "unknown"),
        toss_winner_is_chaser=int(toss.get("winner") == chaser),
        in_pakistan=int(city in PK_CITIES),
        first_innings_total=first_total, target=target,
        chaser_won=int(winner == chaser),
    )
    rows, runs, wkts, legal = [], 0, 0, 0
    last12 = deque(maxlen=12)
    done = False
    for over in inn2["overs"]:
        for d in over["deliveries"]:
            extras = d.get("extras", {})
            legal += 0 if ("wides" in extras or "noballs" in extras) else 1
            w = sum(1 for x in d.get("wickets", []) if x["kind"] not in NOT_A_WICKET)
            runs += d["runs"]["total"]
            wkts += w
            last12.append((d["runs"]["total"], w))
            if runs >= target or wkts >= 10 or legal >= 120:
                done = True                          # outcome decided: do not emit (label leakage)
                break
            rows.append({**base, "legal_balls": legal, "runs": runs, "wickets": wkts,
                         "runs_last12": sum(r for r, _ in last12),
                         "wkts_last12": sum(x for _, x in last12)})
        if done:
            break
    return rows


def main():
    files = sorted(RAW_DIR.glob("*.json"))
    if not files:
        sys.exit(f"No JSON files in {RAW_DIR}. Run src/download_data.py first.")
    rows = [r for f in files for r in parse_match(f)]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    if WEATHER_CSV.exists():                         # optional second source
        wx = pd.read_csv(WEATHER_CSV, parse_dates=["date"])
        df = df.merge(wx, on=["city", "date"], how="left")
    df = add_derived(df)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"{len(files)} files -> {df['match_id'].nunique()} usable matches, {len(df)} ball states")
    print(df["chaser_won"].value_counts(normalize=True).round(3).to_dict())


if __name__ == "__main__":
    main()
