"""Plots and tables from the saved test-set predictions (no tuning happens here)."""
import json
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import ConfusionMatrixDisplay, RocCurveDisplay, roc_auc_score

FIG = pathlib.Path("reports/figures")
FIG.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False})

t = pd.read_csv("reports/test_predictions.csv")
name = json.loads(pathlib.Path("models/meta.json").read_text())["model"]

# 1. Confusion matrix at threshold 0.5
fig, ax = plt.subplots(figsize=(4, 4))
ConfusionMatrixDisplay.from_predictions(t["y"], t["p_final"] >= 0.5, ax=ax, cmap="Greys", colorbar=False)
ax.set_title(f"Confusion matrix ({name})")
fig.savefig(FIG / "eval_confusion.png", bbox_inches="tight")

# 2. ROC curves: model vs baseline
fig, ax = plt.subplots(figsize=(4.5, 4))
RocCurveDisplay.from_predictions(t["y"], t["p_final"], ax=ax, name=name)
RocCurveDisplay.from_predictions(t["y"], t["p_baseline"], ax=ax, name="baseline (RRR)")
ax.plot([0, 1], [0, 1], "k:", lw=0.8)
fig.savefig(FIG / "eval_roc.png", bbox_inches="tight")

# 3. Calibration curve
fig, ax = plt.subplots(figsize=(4.5, 4))
for col, lab in [("p_final", name), ("p_baseline", "baseline (RRR)")]:
    frac, mean = calibration_curve(t["y"], t[col], n_bins=10, strategy="quantile")
    ax.plot(mean, frac, marker="o", label=lab)
ax.plot([0, 1], [0, 1], "k:", lw=0.8)
ax.set(xlabel="Predicted probability", ylabel="Observed win rate", title="Calibration")
ax.legend()
fig.savefig(FIG / "eval_calibration.png", bbox_inches="tight")

# 4. Accuracy and AUC by over
by = []
for o, g in t.groupby("over"):
    auc = roc_auc_score(g["y"], g["p_final"]) if g["y"].nunique() == 2 else np.nan
    by.append({"over": o, "accuracy": ((g["p_final"] >= 0.5) == g["y"]).mean(), "auc": auc, "rows": len(g)})
by = pd.DataFrame(by)
by.to_csv("reports/metrics_by_over.csv", index=False)
fig, ax = plt.subplots(figsize=(6, 3.5))
ax.plot(by["over"], by["accuracy"], marker="o", label="accuracy")
ax.plot(by["over"], by["auc"], marker="s", label="ROC-AUC")
ax.set(xlabel="Over of the chase", ylabel="Score", title="Prediction quality by over")
ax.legend()
fig.savefig(FIG / "eval_by_over.png", bbox_inches="tight")

# 5. Largest errors, for the discussion section
t["abs_err"] = (t["y"] - t["p_final"]).abs()
cols = [c for c in ["match_id", "batting_team", "venue", "over", "runs", "wickets", "target", "y", "p_final"] if c in t]
t.sort_values("abs_err", ascending=False).head(15)[cols].to_csv("reports/worst_errors.csv", index=False)
print(by.round(3).to_string(index=False))
print("saved figures to", FIG)
