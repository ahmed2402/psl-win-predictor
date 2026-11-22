"""Generate synthetic matches in Cricsheet JSON structure, for dry-running the code only."""
import json
import pathlib
import random
import sys

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "data/raw/psl_json")
OUT.mkdir(parents=True, exist_ok=True)
random.seed(7)
TEAMS = {"Lahore Qalandars": 1.0, "Karachi Kings": 0.0, "Islamabad United": 0.5,
         "Peshawar Zalmi": 0.2, "Quetta Gladiators": -0.2, "Multan Sultans": 0.6}
VENUES = [("Gaddafi Stadium, Lahore", "Lahore", 175), ("National Stadium, Karachi", "Karachi", 160),
          ("Rawalpindi Cricket Stadium", "Rawalpindi", 170), ("Multan Cricket Stadium", "Multan", 165),
          ("Dubai International Cricket Stadium", "Dubai", 155), ("Sharjah Cricket Stadium", "Sharjah", 150)]
SEASONS = [str(y) for y in range(2016, 2026)]


def ball(strength, venue_par, balls_left):
    r = random.random()
    if r < 0.045 - 0.01 * strength:
        return {"runs": {"batter": 0, "extras": 0, "total": 0}, "wickets": [{"kind": "caught", "player_out": "x"}]}, True
    if r < 0.085:
        e = random.choice(["wides", "noballs"])
        return {"runs": {"batter": 0, "extras": 1, "total": 1}, "extras": {e: 1}}, False
    boost = 0.015 * strength + (venue_par - 160) / 1500 + (0.03 if balls_left < 24 else 0)
    p = [0.36 - boost, 0.30, 0.08, 0.01, 0.12 + boost / 2, 0.06 + boost / 2]
    runs = random.choices([0, 1, 2, 3, 4, 6], weights=p)[0]
    return {"runs": {"batter": runs, "extras": 0, "total": runs}}, True


def innings(team, strength, par, target=None):
    overs, runs, wk, legal = [], 0, 0, 0
    cur = []
    ov = 0
    while legal < 120 and wk < 10:
        d, is_legal = ball(strength, par, 120 - legal)
        cur.append(d)
        runs += d["runs"]["total"]
        wk += len(d.get("wickets", []))
        legal += int(is_legal)
        if is_legal and legal % 6 == 0:
            overs.append({"over": ov, "deliveries": cur}); cur = []; ov += 1
        if target is not None and runs >= target:
            break
    if cur:
        overs.append({"over": ov, "deliveries": cur})
    out = {"team": team, "overs": overs}
    if target is not None:
        out["target"] = {"runs": target, "overs": 20}
    return out, runs


def main(n_per_season=14):
    k = 0
    for season in SEASONS:
        for _ in range(n_per_season):
            k += 1
            a, b = random.sample(list(TEAMS), 2)
            venue, city, par = random.choice(VENUES)
            i1, t1 = innings(a, TEAMS[a], par)
            i2, t2 = innings(b, TEAMS[b], par, target=t1 + 1)
            toss_winner = random.choice([a, b])
            if t2 > t1:
                outcome = {"winner": b, "by": {"wickets": 1}}
            elif t2 < t1:
                outcome = {"winner": a, "by": {"runs": t1 - t2}}
            else:
                outcome = {"result": "tie"}
            info = {"dates": [f"{season}-0{random.randint(2, 3)}-{random.randint(10, 28)}"], "season": season,
                    "venue": venue, "city": city, "teams": [a, b],
                    "toss": {"winner": toss_winner, "decision": random.choice(["field", "bat"])},
                    "outcome": outcome}
            innings_list = [i1, i2]
            if k % 41 == 0:                                   # no-result match
                info["outcome"] = {"result": "no result"}
            if k % 53 == 0:                                   # rain-shortened chase
                i2["target"]["overs"] = 15
            (OUT / f"{1000000 + k}.json").write_text(json.dumps({"info": info, "innings": innings_list}))
    print("wrote", k, "matches to", OUT)


if __name__ == "__main__":
    main()
