"""scripts/acquire_v3_data.py
Acquires authorized external research datasets for ClauseGuard V3:
1. Yada / EC-DarkPattern (Apache 2.0)
2. University of Edinburgh Cookie Dialogs - Manually Verified Subsets (CC-BY 4.0)
3. Princeton Dark Patterns at Scale (Mathur et al.)

Saves raw archives/files to data/raw/ and records a cryptographic manifest.
"""
import os
import sys
import json
import hashlib
import pathlib
import urllib.request
import zipfile

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
RAW_DIR = ROOT_DIR / "data" / "raw"

SOURCES = {
    "ec_darkpattern": {
        "url": "https://raw.githubusercontent.com/yamanalab/ec-darkpattern/master/dataset/dataset.tsv",
        "target_file": "ec_darkpattern.tsv",
        "license": "Apache-2.0",
        "citation": "Yuki Yada et al., 2022. Dark patterns in e-commerce: a dataset and its baseline evaluations (arXiv:2211.06543)"
    },
    "princeton_darkpatterns": {
        "url": "https://raw.githubusercontent.com/aruneshmathur/dark-patterns/master/data/final-dark-patterns/dark-patterns.csv",
        "target_file": "princeton_dark_patterns.csv",
        "license": "Research Open Access (Attribution Required)",
        "citation": "Arunesh Mathur et al., 2019. Dark Patterns at Scale: Findings from a Crawl of 11K Shopping Websites (CSCW 2019)"
    },
    "edinburgh_random_500": {
        "url": "https://datashare.ed.ac.uk/bitstreams/aa218749-9e23-465d-aac5-18529a29cd75/download",
        "target_file": "tranco_random_500.zip",
        "license": "CC-BY-4.0",
        "citation": "Daniel Kirkman & Kami Vaniea, 2022. Collected cookie dialogs and dark patterns (doi:10.7488/ds/3475)",
        "extract_to": "edinburgh_random_500"
    },
    "edinburgh_top_500": {
        "url": "https://datashare.ed.ac.uk/bitstreams/dccf42b6-8769-4ea8-8d41-30aaef945bf5/download",
        "target_file": "tranco_top_500.zip",
        "license": "CC-BY-4.0",
        "citation": "Daniel Kirkman & Kami Vaniea, 2022. Collected cookie dialogs and dark patterns (doi:10.7488/ds/3475)",
        "extract_to": "edinburgh_top_500"
    }
}

def sha256_file(filepath: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def download_file(url: str, dest: pathlib.Path):
    print(f"[ACQUIRE] Downloading {url} -> {dest.name}...")
    req = urllib.request.Request(url, headers={"User-Agent": "ClauseGuard-Dataset-Acquisition/3.0 (Research)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        with open(dest, "wb") as f:
            while chunk := resp.read(65536):
                f.write(chunk)
    print(f"          Saved {dest.stat().st_size:,} bytes.")

def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {}

    for name, src in SOURCES.items():
        dest = RAW_DIR / src["target_file"]
        if not dest.exists():
            try:
                download_file(src["url"], dest)
            except Exception as e:
                print(f"[ERROR] Failed to download {name}: {e}")
                continue
        else:
            print(f"[CACHE] {src['target_file']} already present ({dest.stat().st_size:,} bytes).")

        h = sha256_file(dest)
        manifest[name] = {
            "file": src["target_file"],
            "sha256": h,
            "bytes": dest.stat().st_size,
            "license": src["license"],
            "citation": src["citation"]
        }

        if "extract_to" in src:
            extract_dir = RAW_DIR / src["extract_to"]
            if not extract_dir.exists():
                print(f"[EXTRACT] Unzipping {src['target_file']} to {src['extract_to']}...")
                extract_dir.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(dest, "r") as z:
                    z.extractall(extract_dir)
                print(f"          Extracted successfully.")

    manifest_path = RAW_DIR / "raw_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"[DONE] Raw acquisition manifest saved to {manifest_path}")

if __name__ == "__main__":
    main()
