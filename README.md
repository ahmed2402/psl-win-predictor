# PSL Live Win-Probability Predictor

CT-378 Machine Learning project. Predicts the probability that the chasing team wins,
from the match state at any ball of a PSL second innings. Deployed with Streamlit.

## Setup (Python 3.12 or newer; run every command from the project root folder)

Windows (PowerShell):

    py -3.12 -m venv .venv          # or: python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt

macOS / Linux:

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

## Run order

    python src/download_data.py     # Cricsheet PSL JSON -> data/raw/psl_json
    python src/build_dataset.py     # -> data/processed/ball_states.csv
    python src/weather.py           # optional second source -> data/external/weather.csv
    python src/build_dataset.py     # run again so the weather columns are merged
    python src/eda.py               # 7 figures in reports/figures
    python src/train.py             # tunes models, saves models/win_pipeline.joblib
    python src/evaluate.py          # test-set plots and error tables
    streamlit run app/streamlit_app.py

The app opens at http://localhost:8501. Training takes a few minutes on a laptop.

Dry run without internet: `python tools/make_fake_data.py` writes SYNTHETIC matches into
data/raw/psl_json. Delete that folder before real work and never report numbers from it.

## Data sources (add the download date from data/raw/psl_json/DOWNLOAD_INFO.txt)
- Cricsheet PSL ball-by-ball data, Open Data Commons Attribution licence, https://cricsheet.org/licensing/
- Open-Meteo Historical Weather API, CC BY 4.0, https://open-meteo.com/en/licence
- Inspiration only, no code copied: arka562/ipl_analysis on GitHub

## Layout
    src/      download, dataset build, features, pipeline, training, evaluation, EDA
    app/      Streamlit app
    models/   saved pipeline (joblib) and meta.json
    reports/  figures and metric tables
