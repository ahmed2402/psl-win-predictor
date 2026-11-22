"""Train, tune, select, refit and evaluate. The test set is scored once, at the end."""
import json
import pathlib
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, log_loss, roc_auc_score
from sklearn.model_selection import GridSearchCV, GroupKFold, RandomizedSearchCV
from sklearn.neighbors import KNeighborsClassifier

from features import WEATHER
from psl_pipeline import feature_lists, make_baseline, make_pipeline, split_by_season

DATA = pathlib.Path("data/processed/ball_states.csv")
SEED = 42
QUICK = False   # set True for a fast dry run


def xy(d, cols):
    return d[["match_id"] + cols], d["chaser_won"]


def score(model, X, y):
    p = model.predict_proba(X)[:, 1]
    return {"roc_auc": roc_auc_score(y, p), "f1": f1_score(y, p >= 0.5),
            "log_loss": log_loss(y, p), "accuracy": float(((p >= 0.5) == y).mean())}


def main():
    df = pd.read_csv(DATA, parse_dates=["date"])
    numeric, categorical = feature_lists(df)
    cols = [c for c in numeric + categorical if c != "venue_avg_first"]
    cols += ["target"] if "target" not in cols else []
    parts, groups = split_by_season(df)
    for k, v in parts.items():
        print(f"{k:5s} seasons={groups[k]} matches={v.match_id.nunique()} rows={len(v)}")

    Xtr, ytr = xy(parts["train"], cols)
    Xva, yva = xy(parts["val"], cols)
    Xte, yte = xy(parts["test"], cols)
    cv = GroupKFold(n_splits=5)
    n_iter = 2 if QUICK else 8

    searches = {
        "logreg": GridSearchCV(
            make_pipeline(LogisticRegression(max_iter=2000), numeric, categorical),
            {"model__C": [0.01, 0.1, 1, 10]}, cv=cv, scoring="roc_auc", n_jobs=-1),
        "knn": GridSearchCV(
            make_pipeline(KNeighborsClassifier(), numeric, categorical),
            {"model__n_neighbors": [15, 31, 61], "model__weights": ["uniform", "distance"]},
            cv=cv, scoring="roc_auc", n_jobs=-1),
        "random_forest": RandomizedSearchCV(
            make_pipeline(RandomForestClassifier(random_state=SEED, n_jobs=-1), numeric, categorical),
            {"model__n_estimators": [200, 400], "model__max_depth": [6, 10, 14, None],
             "model__min_samples_leaf": [5, 20, 50]},
            n_iter=n_iter, cv=cv, scoring="roc_auc", random_state=SEED, n_jobs=1),
        "gradient_boosting": RandomizedSearchCV(
            make_pipeline(HistGradientBoostingClassifier(random_state=SEED), numeric, categorical),
            {"model__learning_rate": [0.03, 0.06, 0.1], "model__max_depth": [3, 5, None],
             "model__max_leaf_nodes": [15, 31], "model__min_samples_leaf": [20, 50, 100],
             "model__l2_regularization": [0.0, 1.0]},
            n_iter=n_iter, cv=cv, scoring="roc_auc", random_state=SEED, n_jobs=-1),
    }

    rows, fitted = [], {}
    for name, s in searches.items():
        t = time.time()
        s.fit(Xtr, ytr, groups=Xtr["match_id"])
        m = score(s.best_estimator_, Xva, yva)
        fitted[name] = s
        rows.append({"model": name, "cv_auc": s.best_score_, **{f"val_{k}": v for k, v in m.items()},
                     "fit_seconds": round(time.time() - t, 1), "best_params": s.best_params_})
        print(f"{name:18s} cv_auc={s.best_score_:.3f} val_auc={m['roc_auc']:.3f} ({rows[-1]['fit_seconds']}s)")

    base = make_baseline(LogisticRegression()).fit(Xtr, ytr)
    bm = score(base, Xva, yva)
    rows.insert(0, {"model": "baseline_rrr", "cv_auc": np.nan,
                    **{f"val_{k}": v for k, v in bm.items()}, "fit_seconds": 0, "best_params": {}})
    table = pd.DataFrame(rows)
    pathlib.Path("reports").mkdir(exist_ok=True)
    table.to_csv("reports/model_comparison_validation.csv", index=False)
    print(table.drop(columns="best_params").round(3).to_string(index=False))

    # Select on validation, refit on train+val, then touch the test set once.
    best_name = table[table.model != "baseline_rrr"].sort_values("val_roc_auc").iloc[-1]["model"]
    print("Selected:", best_name)
    Xfull = pd.concat([Xtr, Xva])
    yfull = pd.concat([ytr, yva])
    final = clone(fitted[best_name].best_estimator_).fit(Xfull, yfull)
    base_final = make_baseline(LogisticRegression()).fit(Xfull, yfull)
    test = {"baseline_rrr": score(base_final, Xte, yte), best_name: score(final, Xte, yte)}
    print(json.dumps(test, indent=2))

    pathlib.Path("models").mkdir(exist_ok=True)
    joblib.dump(final, "models/win_pipeline.joblib")
    venue_city = df.drop_duplicates("venue").set_index("venue")["city"].to_dict()
    meta = {
        "model": best_name, "feature_columns": [c for c in cols if c != "match_id"],
        "teams": sorted(df["batting_team"].unique()), "venues": sorted(df["venue"].unique()),
        "venue_city": venue_city, "weather_features": WEATHER,
        "test_metrics": test, "split": {k: v for k, v in groups.items()},
    }
    pathlib.Path("models/meta.json").write_text(json.dumps(meta, indent=2))

    # keep test predictions for evaluate.py (plots only, no further tuning)
    out = Xte.copy()
    out["y"] = yte.values
    out["p_final"] = final.predict_proba(Xte)[:, 1]
    out["p_baseline"] = base_final.predict_proba(Xte)[:, 1]
    out.to_csv("reports/test_predictions.csv", index=False)


if __name__ == "__main__":
    main()
