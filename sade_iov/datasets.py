"""Unified dataset layer for the SADE-IoV risk engine.

The design report grounds the evaluation on two public benchmarks plus a
noise-aware synthetic generator:

  * VeReMi (2018) and its extension (2020) - V2X position-falsification
    misbehaviour, generated with the VEINS/SUMO stack.
      source: https://github.com/josephkamel/VeReMi-Dataset
  * CICIoV2024 - in-vehicle CAN-bus attack traffic (spoofing / DoS) from the
    Canadian Institute for Cybersecurity, University of New Brunswick.
      source: https://www.unb.ca/cic/datasets/iov-dataset-2024.html
  * Synthetic generator (this project) - channel-level jamming/injection
    scenarios the public sets do not cover.

Every loader returns a DataFrame in one **unified schema** so the risk engine
and the multi-model comparison can consume any source interchangeably:

    R_RSSI, V_var, alpha_freq, D_class, label, is_attack, source

Because the full public archives are large (VeReMi is tens of GB), the loaders
consume files already present on disk; ``fetch_datasets.py`` documents how to
download them. Point the loaders at the extracted dataset directory.
"""
from __future__ import annotations

import glob
import json
import os

import numpy as np
import pandas as pd

from . import config

UNIFIED_COLS = ["R_RSSI", "V_var", "alpha_freq", "D_class", "label", "is_attack", "source"]


# ---------------------------------------------------------------------------
# Synthetic (always available)
# ---------------------------------------------------------------------------
def load_synthetic(n_epochs: int = config.N_EPOCHS, seed: int = config.DEFAULT_SEED) -> pd.DataFrame:
    """Return the synthetic dataset in the unified schema."""
    from .data_generator import generate_dataset

    df = generate_dataset(n_epochs=n_epochs, seed=seed)
    df = df.rename(columns={})
    df["source"] = "synthetic"
    return df[["R_RSSI", "V_var", "alpha_freq", "D_class", "label", "is_attack", "source"]]


# ---------------------------------------------------------------------------
# VeReMi (2018) / VeReMi-extension (2020)
# ---------------------------------------------------------------------------
# VeReMi ground-truth attacker types -> our coarse label.
_VEREMI_ATTACK_TYPES = {
    0: 0,   # genuine
    1: 3,   # constant position       -> spoofing family
    2: 3,   # constant offset
    4: 3,   # random position
    8: 3,   # random offset
    16: 3,  # eventual stop
}


def load_veremi(root: str, max_files: int | None = None, window: int = 10) -> pd.DataFrame:
    """Parse VeReMi JSON logs from ``root`` into the unified schema.

    Each VeReMi receiver log is a JSON-lines file of received BSMs. We derive:
      * R_RSSI    from the message 'RSSI' field (dBm),
      * V_var     rolling variance of reported speed magnitude,
      * alpha_freq rolling message-arrival count (a flooding/injection proxy),
    and take the label from the attacker type recorded in the ground-truth /
    per-message 'attackerType' field.
    """
    files = sorted(glob.glob(os.path.join(root, "**", "*.json"), recursive=True))
    files = [f for f in files if "GroundTruth" not in os.path.basename(f)]
    if max_files:
        files = files[:max_files]
    if not files:
        raise FileNotFoundError(
            f"No VeReMi log files found under {root!r}. "
            "Download & extract the dataset first (see scripts/fetch_datasets.py)."
        )

    rows = []
    for fp in files:
        recs = []
        with open(fp) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    m = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if m.get("type") != 3:          # type 3 = received BSM in VeReMi
                    continue
                spd = m.get("spd") or m.get("speed") or [0, 0, 0]
                spd_mag = float(np.linalg.norm(spd[:2])) if isinstance(spd, (list, tuple)) else float(spd)
                rssi = m.get("RSSI")
                atk = int(m.get("attackerType", 0))
                recs.append((rssi, spd_mag, atk, m.get("rcvTime", m.get("sendTime", 0))))
        for i, (rssi, spd_mag, atk, _t) in enumerate(recs):
            lo = max(0, i - window)
            win_spd = [r[1] for r in recs[lo:i + 1]]
            v_var = float(np.var(win_spd)) if len(win_spd) > 1 else 0.0
            alpha = float(len(win_spd))       # arrival count in the window
            # RSSI in VeReMi is a linear power; convert to dBm if not already.
            if rssi is None:
                r_dbm = -60.0
            elif rssi > 0:
                r_dbm = 10.0 * np.log10(rssi + 1e-12)
            else:
                r_dbm = float(rssi)
            label = _VEREMI_ATTACK_TYPES.get(atk, 3 if atk else 0)
            rows.append({
                "R_RSSI": r_dbm, "V_var": v_var, "alpha_freq": alpha,
                "D_class": 1,                    # V2X BSMs are localisation-class
                "label": label, "is_attack": int(label != 0), "source": "veremi",
            })
    df = pd.DataFrame(rows, columns=UNIFIED_COLS)
    return df


# ---------------------------------------------------------------------------
# CICIoV2024 (CAN-bus attacks)
# ---------------------------------------------------------------------------
def load_ciciov2024(root: str, window: int = 20) -> pd.DataFrame:
    """Parse CICIoV2024 CSV files from ``root`` into the unified schema.

    CICIoV2024 captures CAN frames labelled benign / DoS / spoofing. These are
    internal-network attacks, so we map:
      * V_var     -> rolling variance of the decoded CAN payload magnitude
                     (erratic ECU values, the spoofing signature),
      * alpha_freq -> rolling frame-arrival count (the DoS/flooding signature),
      * R_RSSI    -> a benign RF constant (no wireless channel on the CAN bus).
    """
    files = sorted(glob.glob(os.path.join(root, "**", "*.csv"), recursive=True))
    if not files:
        raise FileNotFoundError(
            f"No CICIoV2024 CSV files found under {root!r}. "
            "Download the dataset first (see scripts/fetch_datasets.py)."
        )
    frames = []
    for fp in files:
        try:
            frames.append(pd.read_csv(fp))
        except Exception:
            continue
    raw = pd.concat(frames, ignore_index=True)
    raw.columns = [c.strip().lower() for c in raw.columns]

    # Locate the label column and the DATA byte columns robustly.
    label_col = next((c for c in raw.columns if c in ("label", "category", "class", "attack")), None)
    data_cols = [c for c in raw.columns if c.startswith("data") or c.startswith("d")]
    data_cols = [c for c in data_cols if raw[c].dtype != object][:8]

    def to_label(v):
        s = str(v).lower()
        if "benign" in s or s in ("0", "normal"):
            return 0
        if "dos" in s or "flood" in s:
            return 2      # injection/flooding family
        return 3          # spoofing family

    payload = raw[data_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    mag = payload.sum(axis=1).to_numpy(dtype=float)
    labels = raw[label_col].map(to_label).to_numpy() if label_col else np.zeros(len(raw), int)

    rows = []
    for i in range(len(raw)):
        lo = max(0, i - window)
        win = mag[lo:i + 1]
        rows.append({
            "R_RSSI": -60.0,
            "V_var": float(np.var(win)) if len(win) > 1 else 0.0,
            "alpha_freq": float(len(win)),
            "D_class": 2,                        # CAN traffic is safety-control class
            "label": int(labels[i]), "is_attack": int(labels[i] != 0), "source": "ciciov2024",
        })
    return pd.DataFrame(rows, columns=UNIFIED_COLS)


# ---------------------------------------------------------------------------
# Combine + describe
# ---------------------------------------------------------------------------
def combine(*frames: pd.DataFrame) -> pd.DataFrame:
    """Concatenate unified frames from several sources into one dataset."""
    df = pd.concat([f for f in frames if f is not None and len(f)], ignore_index=True)
    return df[UNIFIED_COLS]


def describe(df: pd.DataFrame) -> dict:
    """Return (and pretty-print) the dataset size and class balance."""
    info = {
        "rows": int(len(df)),
        "features": [c for c in ("R_RSSI", "V_var", "alpha_freq", "D_class") if c in df],
        "by_source": df["source"].value_counts().to_dict() if "source" in df else {},
        "by_label": df["label"].value_counts().sort_index().to_dict(),
        "attack_ratio": float(df["is_attack"].mean()) if "is_attack" in df else None,
    }
    print(f"Dataset size : {info['rows']:,} rows x {len(info['features'])} features")
    print(f"By source    : {info['by_source']}")
    print(f"By label     : {info['by_label']}  (0=genuine)")
    if info["attack_ratio"] is not None:
        print(f"Attack ratio : {info['attack_ratio']*100:.1f}%")
    return info
