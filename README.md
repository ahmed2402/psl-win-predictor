# PSL Live Win-Probability Predictor

CT-378 Machine Learning project. Predicts the probability that the chasing team wins,
from the match state at any ball of a PSL second innings. Served by a FastAPI backend with an HTML front end.

**Live app:** https://psl-chase-predictor.onrender.com (Render, free tier) · **API docs:** https://psl-chase-predictor.onrender.com/docs

## Setup (Python 3.13, see .python-version; run every command from the project root folder)

`requirements.txt` holds the runtime packages only (what the deployed API needs).
`requirements-dev.txt` adds the data pipeline, notebook and test tools.

Windows (PowerShell):

    py -3.13 -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements-dev.txt

macOS / Linux:

    python3.13 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements-dev.txt

## Run order

    python src/download_data.py     # Cricsheet PSL JSON -> data/raw/psl_json
    python src/weather.py           # Open-Meteo weather per match city/date -> data/external/weather.csv
    python src/build_dataset.py     # JSON + weather -> data/processed/ball_states.csv
    jupyter nbconvert --to notebook --execute --inplace notebooks/01_eda.ipynb   # EDA, 7 figures -> reports/figures
    python src/train.py             # tunes models, saves models/win_pipeline.joblib
    python src/evaluate.py          # test-set plots and error tables
    jupyter nbconvert --to notebook --execute --inplace notebooks/02_modelling.ipynb   # results narrative

Training takes a few minutes on a laptop.

## Run the web app locally

    uvicorn app.main:app --reload     # http://localhost:8000  (API docs at /docs)
    pytest                            # API tests (offline)

The page (`app/static/`) is a broadcast-style win-predictor graphic. Enter the match state, or log each delivery with the
ball pad (0 1 2 3 4 6 W Wd, with undo). It shows the probability, a what-if curve and the inputs moving the needle.

Endpoints: `GET /health`, `GET /meta`, `POST /predict`. `/predict` validates the match state. Today's evening
dew point for the chosen city comes live from Open-Meteo (fetched by the browser, then by the server as a
backup, then the training median if the weather service is unreachable).

## Data sources

| Source | What | Licence | Collected | Method |
|---|---|---|---|---|
| Cricsheet (`psl_male_json.zip`) | PSL ball-by-ball, 357 matches, seasons 2015/16 to 2026 | Open Data Commons Attribution, https://cricsheet.org/licensing/ | 2026-11-22 | HTTP download, `src/download_data.py` |
| Open-Meteo Historical Weather API | Evening (16:00 to 22:00 local) mean temperature, humidity and dew point per match city and date | CC BY 4.0, https://open-meteo.com/en/licence | 2026-11-22 | Public API, `src/weather.py` |

Result: 339 usable matches, 38,790 second-innings ball states, 25 candidate features. The model uses the 8
that the data supports (live match state + dew point); the reasoning is in `notebooks/01_eda.ipynb`.
Player names are present in the raw Cricsheet files but never enter the dataset.

Inspiration only, no code copied: arka562/ipl_analysis on GitHub.

## Results

Logistic regression, selected on the validation seasons (2023/24, 2025) from a run-rate baseline, logistic
regression, KNN, random forest and gradient boosting (5-fold GroupKFold tuning). Scored once on the unseen
2026 season: **ROC-AUC 0.918** (baseline 0.892), F1 0.839, accuracy 0.808. Details: `notebooks/02_modelling.ipynb`.

## Layout
    src/        download, weather, dataset build, features, pipeline, training, evaluation
    notebooks/  01_eda.ipynb (EDA and feature decisions), 02_modelling.ipynb (results)
    app/        FastAPI backend (main.py) and HTML front end (static/)
    models/     saved pipeline (joblib) and meta.json
    reports/    figures and metric tables
    tests/      API tests (pytest)
    data/       external/weather.csv; raw/ and processed/ are rebuilt by the scripts
