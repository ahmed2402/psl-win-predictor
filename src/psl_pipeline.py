"""Pipeline pieces: leak-free venue feature, preprocessing, chronological season split."""
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from features import CATEGORICAL, NUMERIC, WEATHER


class VenueAverage(BaseEstimator, TransformerMixin):
    """Average first-innings total per venue, learned from the training matches only.

    fit() needs 'match_id', 'venue' and 'target' columns (target - 1 = first-innings total).
    transform() only needs 'venue', so the app can call it without match_id.
    """

    def fit(self, X, y=None):
        m = X.drop_duplicates("match_id")
        self.venue_mean_ = (m["target"] - 1).groupby(m["venue"]).mean()
        self.global_mean_ = float((m["target"] - 1).mean())
        return self

    def transform(self, X):
        X = X.copy()
        X["venue_avg_first"] = X["venue"].map(self.venue_mean_).fillna(self.global_mean_)
        return X


def feature_lists(df):
    numeric = NUMERIC + [c for c in WEATHER if c in df.columns]
    return numeric, CATEGORICAL


def make_pipeline(clf, numeric, categorical):
    prep = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), numeric),
        ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")),
                          ("oh", OneHotEncoder(handle_unknown="ignore", sparse_output=False))]), categorical),
    ])
    return Pipeline([("venue", VenueAverage()), ("prep", prep), ("model", clf)])


def make_baseline(clf):
    """Baseline: required run rate alone."""
    return Pipeline([("sel", ColumnTransformer([("rrr", StandardScaler(), ["rrr"])])), ("model", clf)])


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
