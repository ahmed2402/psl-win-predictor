"""Download the PSL ball-by-ball JSON archive from Cricsheet (ODC-BY licence)."""
import datetime
import io
import pathlib
import zipfile

import requests

URL = "https://cricsheet.org/downloads/psl_male_json.zip"
OUT = pathlib.Path("data/raw/psl_json")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    resp = requests.get(URL, timeout=120)
    resp.raise_for_status()
    zipfile.ZipFile(io.BytesIO(resp.content)).extractall(OUT)
    n = len(list(OUT.glob("*.json")))
    print(f"Extracted {n} match files to {OUT}")
    # Keep a record for the README / report data section
    with open(OUT / "DOWNLOAD_INFO.txt", "w") as f:
        f.write(f"source: {URL}\nlicence: Open Data Commons Attribution (cricsheet.org/licensing)\n")
        f.write(f"downloaded: {datetime.date.today().isoformat()}\nmethod: HTTP GET via requests\n")


if __name__ == "__main__":
    main()
