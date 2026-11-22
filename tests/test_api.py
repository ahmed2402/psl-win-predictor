"""API tests. The live weather call is replaced, so the tests run offline."""
import pytest
from fastapi.testclient import TestClient

import app.main as main

client = TestClient(main.app)
VALID = {"batting_team": "Lahore Qalandars", "bowling_team": "Karachi Kings", "city": "Lahore",
         "target": 180, "runs": 90, "wickets": 3, "overs": 10, "balls": 0, "runs_last12": 18, "wkts_last12": 1}


@pytest.fixture(autouse=True)
def offline_dew(monkeypatch):
    monkeypatch.setattr(main, "evening_dew", lambda city: 15.0)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_meta_lists_teams_and_cities():
    m = client.get("/meta").json()
    assert "Lahore Qalandars" in m["teams"] and "Karachi" in m["cities"]


def test_predict_valid():
    r = client.post("/predict", json=VALID)
    assert r.status_code == 200
    body = r.json()
    assert 0 < body["win_probability"] < 1
    assert body["dew_point_c"] == 15.0 and body["dew_source"].startswith("live")
    assert any(p["runs"] == 90 for p in body["what_if"])
    assert len(body["contributions"]) == 8


def test_more_runs_means_higher_probability():
    worse = client.post("/predict", json={**VALID, "runs": 60}).json()["win_probability"]
    better = client.post("/predict", json={**VALID, "runs": 120}).json()["win_probability"]
    assert better > worse


@pytest.mark.parametrize("change", [
    {"runs": 180},                              # chase already won
    {"bowling_team": "Lahore Qalandars"},       # same team twice
    {"runs_last12": 95},                        # last-12 runs above total
    {"wkts_last12": 4},                         # last-12 wickets above wickets lost
    {"city": "London"},
    {"overs": 20},                              # out of range
])
def test_predict_invalid_returns_422(change):
    r = client.post("/predict", json={**VALID, **change})
    assert r.status_code == 422


def test_weather_down_uses_training_median(monkeypatch):
    monkeypatch.setattr(main, "evening_dew", lambda city: None)
    body = client.post("/predict", json=VALID).json()
    assert body["dew_point_c"] == main.DEW_MEDIAN and "median" in body["dew_source"]
