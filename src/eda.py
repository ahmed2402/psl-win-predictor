"""EDA plots on the TRAINING seasons only. In a notebook, split at the '# %%' markers into cells."""
# %%
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from features import WEATHER
from psl_pipeline import split_by_season

FIG = pathlib.Path("reports/figures")
FIG.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False})
df = pd.read_csv("data/processed/ball_states.csv", parse_dates=["date"])
df = split_by_season(df)[0]["train"]          # explore training data only
print(df.shape, df["match_id"].nunique(), "matches")
print(df.isna().mean().sort_values(ascending=False).head(10))

# %% 1. Class balance (one row per ball vs one row per match)
fig, ax = plt.subplots(1, 2, figsize=(7, 3))
df["chaser_won"].value_counts().sort_index().plot.bar(ax=ax[0], color="grey", title="Ball states")
df.drop_duplicates("match_id")["chaser_won"].value_counts().sort_index().plot.bar(ax=ax[1], color="grey", title="Matches")
for a in ax:
    a.set_xlabel("chaser won (0/1)")
fig.savefig(FIG / "eda_1_class_balance.png", bbox_inches="tight")

# %% 2. Distribution of required run rate by outcome
fig, ax = plt.subplots(figsize=(5, 3.5))
for k, g in df.groupby("chaser_won"):
    ax.hist(g["rrr"].clip(0, 30), bins=40, alpha=0.5, label=f"won={k}", density=True)
ax.set(xlabel="Required run rate (clipped at 30)", title="RRR by outcome")
ax.legend()
fig.savefig(FIG / "eda_2_rrr_hist.png", bbox_inches="tight")

# %% 3. Win rate by wickets lost
fig, ax = plt.subplots(figsize=(5, 3.5))
df.groupby("wickets")["chaser_won"].mean().plot(marker="o", ax=ax, color="black")
ax.set(ylabel="Chasing-side win rate", title="Win rate by wickets lost")
fig.savefig(FIG / "eda_3_wickets_winrate.png", bbox_inches="tight")

# %% 4. Venue first-innings scores (outliers) per match
m = df.drop_duplicates("match_id")
fig, ax = plt.subplots(figsize=(7, 3.5))
order = m.groupby("venue")["first_innings_total"].median().sort_values().index
ax.boxplot([m.loc[m.venue == v, "first_innings_total"] for v in order], tick_labels=[v[:18] for v in order])
ax.tick_params(axis="x", rotation=60)
ax.set_title("First-innings totals by venue")
fig.savefig(FIG / "eda_4_venue_boxplot.png", bbox_inches="tight")

# %% 5. Correlation heatmap of numeric features
num = ["over", "runs", "wickets", "balls_left", "runs_needed", "target", "crr", "rrr", "rr_gap",
       "runs_last12", "wkts_last12", "toss_winner_is_chaser", "in_pakistan", "chaser_won"]
num += WEATHER
corr = df[num].corr()
fig, ax = plt.subplots(figsize=(7, 6))
im = ax.imshow(corr, cmap="Greys", vmin=-1, vmax=1)
ax.set_xticks(range(len(num)), num, rotation=90)
ax.set_yticks(range(len(num)), num)
fig.colorbar(im, ax=ax, shrink=0.7)
fig.savefig(FIG / "eda_5_correlation.png", bbox_inches="tight")

# %% 6. Missing values per column
miss = df.isna().mean()
fig, ax = plt.subplots(figsize=(6, 3))
if (miss > 0).any():
    miss[miss > 0].sort_values().plot.barh(ax=ax, color="grey", title="Share missing")
else:
    ax.set_title("Share missing")
    ax.text(0.5, 0.5, "No missing values", ha="center", transform=ax.transAxes)
    ax.set_axis_off()
fig.savefig(FIG / "eda_6_missing.png", bbox_inches="tight")

# %% 7. Win rate by over and by toss decision
fig, ax = plt.subplots(1, 2, figsize=(8, 3))
df.groupby("over")["chaser_won"].mean().plot(marker="o", ax=ax[0], color="black", title="Win rate by over")
df.drop_duplicates("match_id").groupby("toss_decision")["chaser_won"].mean().plot.bar(ax=ax[1], color="grey", title="Chaser win rate by toss decision")
fig.savefig(FIG / "eda_7_over_toss.png", bbox_inches="tight")
print("EDA figures saved")
