"""Download / locate the public benchmark datasets used by SADE-IoV.

The full archives are large and some hosts require a manual/agreed download,
so this script documents the official sources and verifies whatever is already
present under ``data/``. Run it on a machine with open network access.

Layout expected by the loaders:
    data/veremi/      <- extracted VeReMi JSON logs (recursively discovered)
    data/ciciov2024/  <- CICIoV2024 CSV files

Usage:
    python -m scripts.fetch_datasets            # show status + instructions
    python -m scripts.fetch_datasets --try-download veremi
"""
from __future__ import annotations

import argparse
import os
import sys

SOURCES = {
    "veremi": {
        "year": "2018 / extension 2020",
        "what": "V2X position-falsification misbehaviour (VEINS/SUMO)",
        "url": "https://github.com/josephkamel/VeReMi-Dataset",
        "dir": "data/veremi",
        "loader": "sade_iov.datasets.load_veremi('data/veremi')",
    },
    "ciciov2024": {
        "year": "2024",
        "what": "In-vehicle CAN-bus attacks (spoofing / DoS)",
        "url": "https://www.unb.ca/cic/datasets/iov-dataset-2024.html",
        "dir": "data/ciciov2024",
        "loader": "sade_iov.datasets.load_ciciov2024('data/ciciov2024')",
    },
}


def status() -> None:
    print("SADE-IoV benchmark datasets\n" + "=" * 60)
    for key, s in SOURCES.items():
        present = os.path.isdir(s["dir"]) and any(os.scandir(s["dir"]))
        mark = "FOUND" if present else "missing"
        print(f"\n[{mark}] {key}  ({s['year']})")
        print(f"   {s['what']}")
        print(f"   source : {s['url']}")
        print(f"   place under : {s['dir']}/")
        print(f"   load with   : {s['loader']}")
    print("\n" + "=" * 60)
    print("After placing the files, run:  python -m scripts.compare_models --dataset all")


def try_download(name: str) -> None:
    import urllib.request

    if name not in SOURCES:
        print(f"Unknown dataset {name!r}. Choose from: {list(SOURCES)}")
        return
    s = SOURCES[name]
    os.makedirs(s["dir"], exist_ok=True)
    print(f"Attempting to reach {s['url']} ...")
    try:
        req = urllib.request.Request(s["url"], headers={"User-Agent": "sade-iov"})
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"  reachable (HTTP {r.status}). Follow the page to download the "
                  f"archive, then extract it into {s['dir']}/.")
    except Exception as e:  # noqa: BLE001
        print(f"  could not fetch automatically ({e}).")
        print(f"  Download manually from {s['url']} and extract into {s['dir']}/.")


def main() -> None:
    p = argparse.ArgumentParser(description="Fetch/locate SADE-IoV datasets.")
    p.add_argument("--try-download", choices=list(SOURCES), default=None)
    args = p.parse_args()
    if args.try_download:
        try_download(args.try_download)
    status()


if __name__ == "__main__":
    sys.exit(main())
