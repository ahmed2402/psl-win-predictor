"""Pipeline pieces: run-rate clipping, preprocessing, chronological season split."""
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from features import NUMERIC, RATE_CAP


def clip_rates(X):
    """Cap run rates at RATE_CAP. Inside the pipeline, so the API gets the same treatment."""
    return X.assign(rrr=X["rrr"].clip(upper=RATE_CAP), crr=X["crr"].clip(upper=RATE_CAP))


def make_pipeline(clf, numeric=NUMERIC, categorical=()):
    """clip -> impute + scale numeric (+ one-hot categorical, used only for EDA comparisons) -> model.
    Every step is fitted on the training data passed to fit(), so nothing leaks from validation/test."""
    steps = [("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), list(numeric))]
    if categorical:
        steps.append(("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")),
                                       ("oh", OneHotEncoder(handle_unknown="ignore", sparse_output=False))]),
                      list(categorical)))
    return Pipeline([("clip", FunctionTransformer(clip_rates)), ("prep", ColumnTransformer(steps)), ("model", clf)])


def make_baseline(clf):
    """Baseline: required run rate alone."""
    return Pipeline([("clip", FunctionTransformer(clip_rates)),
                     ("sel", ColumnTransformer([("rrr", StandardScaler(), ["rrr"])])), ("model", clf)])


def split_by_season(df, cuts=(0.70, 0.85)):
    """Whole seasons go to train / validation / test, oldest first, cut near 70/15/15 of matches."""
    m = df.groupby("match_id").agg(season=("season", "first"), date=("date", "first")).reset_index()
    order = m.groupby("season")["date"].min().sort_values().index.tolist()
    if len(order) < 3:
        raise ValueError("Need at least 3 seasons for a train/validation/test split")
    counts = m.groupby("season").size().reindex(order)
    cum = (counts.cumsum() / counts.sum()).values
    i1 = int(abs(cum - cuts[0]).argmin())
    i1 = min(i1, len(order) - 3)
    i2 = int(abs(cum - cuts[1]).argmin())
    i2 = min(max(i2, i1 + 1), len(order) - 2)
    groups = {"train": order[: i1 + 1], "val": order[i1 + 1: i2 + 1], "test": order[i2 + 1:]}
    return {k: df[df["season"].isin(v)].copy() for k, v in groups.items()}, groups
