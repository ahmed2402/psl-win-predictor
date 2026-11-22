# PSL Live Win-Probability Predictor

CT-378 Machine Learning project. Predicts the probability that the chasing team wins,
from the match state at any ball of a PSL second innings. Served by a FastAPI backend with an HTML front end.

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

Training takes a few minutes on a laptop.

Dry run: `python tools/make_fake_data.py` writes SYNTHETIC matches into
data/raw/psl_json (`weather.py` still needs internet). Delete that folder before real work and never report numbers from it.

## Data sources

| Source | What | Licence | Collected | Method |
|---|---|---|---|---|
| Cricsheet (`psl_male_json.zip`) | PSL ball-by-ball, 357 matches, seasons 2015/16 to 2026 | Open Data Commons Attribution, https://cricsheet.org/licensing/ | 2026-11-22 | HTTP download, `src/download_data.py` |
| Open-Meteo Historical Weather API | Evening (16:00 to 22:00 local) mean temperature, humidity and dew point per match city and date | CC BY 4.0, https://open-meteo.com/en/licence | 2026-11-22 | Public API, `src/weather.py` |

Result: 339 usable matches, 38,790 second-innings ball states, 25 model features.
Player names are present in the raw Cricsheet files but never enter the dataset.

Inspiration only, no code copied: arka562/ipl_analysis on GitHub.

## Layout
    src/        download, weather, dataset build, features, pipeline, training, evaluation
    notebooks/  01_eda.ipynb (EDA and feature decisions)
    app/        FastAPI backend and HTML front end
    models/   saved pipeline (joblib) and meta.json
    reports/  figures and metric tables
