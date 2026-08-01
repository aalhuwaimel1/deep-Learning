"""Tests for the dataset layer and the three-solutions comparison."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sade_iov import datasets, experiments
from sade_iov.data_generator import generate_dataset


def test_veremi_like_schema_and_classes():
    df = datasets.synthesize_veremi_like(n_epochs=600, seed=1)
    for col in ["R_RSSI", "V_var", "alpha_freq", "D_class", "label", "is_attack", "risk_true"]:
        assert col in df.columns
    assert set(df["label"].unique()) <= {0, 1}          # binary benchmark
    assert df["is_attack"].mean() > 0.2                  # has attackers
    assert (df["is_attack"] == (df["label"] != 0)).all()


def test_three_solutions_ordering():
    """On a small run, static-strong is safest, static-light is unsafe,
    and SADE-IoV lands in between on cost while staying highly protective."""
    df = generate_dataset(n_epochs=1500, seed=3)
    r = experiments.three_solutions(df, seed=3)
    s = r["solutions"]
    assert r["train_n"] > r["test_n"] > 0                # train/test split present
    strong = s["Static strong (AES-256+PUF)"]
    light = s["Static light (AES-128 only)"]
    sade = s["SADE-IoV (adaptive)"]
    assert strong["attack_response_pct"] == 100.0
    assert light["attack_response_pct"] == 0.0
    assert sade["attack_response_pct"] > 80.0            # highly protective
    assert light["mean_latency_ms"] <= sade["mean_latency_ms"] <= strong["mean_latency_ms"]
