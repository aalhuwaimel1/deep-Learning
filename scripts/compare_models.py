"""Compare several risk classifiers on the SADE-IoV feature space.

Addresses the reviewer request to "use multiple ways (XGBoost and other way)":
trains XGBoost alongside Random Forest, Extra Trees, Logistic Regression, an
RBF SVM and an MLP on the same partition, then prints a ranked table and saves
a comparison figure.

Usage:
    python -m scripts.compare_models                     # synthetic dataset
    python -m scripts.compare_models --dataset veremi    # if data/veremi present
    python -m scripts.compare_models --dataset all       # synthetic + any real
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
from sklearn.model_selection import train_test_split

from sade_iov import config, datasets
from sade_iov.models import compare_models, save_comparison_figure


def build_dataset(kind: str):
    frames = []
    if kind in ("synthetic", "all"):
        frames.append(datasets.load_synthetic())
    if kind in ("veremi", "all") and os.path.isdir("data/veremi"):
        try:
            frames.append(datasets.load_veremi("data/veremi"))
        except FileNotFoundError as e:
            print(f"[veremi] skipped: {e}")
    if kind in ("ciciov2024", "all") and os.path.isdir("data/ciciov2024"):
        try:
            frames.append(datasets.load_ciciov2024("data/ciciov2024"))
        except FileNotFoundError as e:
            print(f"[ciciov2024] skipped: {e}")
    if kind == "veremi" and not frames:
        raise SystemExit("data/veremi not found - run scripts/fetch_datasets.py first.")
    if not frames:
        frames.append(datasets.load_synthetic())
    return datasets.combine(*frames)


def main() -> None:
    p = argparse.ArgumentParser(description="Compare risk classifiers.")
    p.add_argument("--dataset", default="synthetic",
                   choices=["synthetic", "veremi", "ciciov2024", "all"])
    p.add_argument("--seed", type=int, default=config.DEFAULT_SEED)
    args = p.parse_args()

    print(f"Loading dataset: {args.dataset}")
    df = build_dataset(args.dataset)
    datasets.describe(df)

    X = df[config.FEATURES].to_numpy(dtype=float)
    y = df["label"].to_numpy()
    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=config.TEST_SIZE, random_state=args.seed, stratify=y,
    )

    print("\nTraining & comparing models (this trains 6 classifiers)...\n")
    table = compare_models(Xtr, ytr, Xte, yte, seed=args.seed)

    cols = ["name", "accuracy", "attack_recall", "false_negative_rate",
            "f1_macro", "train_time_s", "infer_ms_per_sample"]
    show = table[cols].copy()
    for c in cols[1:]:
        show[c] = show[c].map(lambda v: f"{v:.4f}")
    print(show.to_string(index=False))

    fig = save_comparison_figure(table)
    os.makedirs(config.ARTIFACT_DIR, exist_ok=True)
    table.to_json(f"{config.ARTIFACT_DIR}/model_comparison.json", orient="records", indent=2)
    best = table.iloc[0]["name"]
    print(f"\nBest by attack-recall then F1: {best}")
    print(f"Figure : {fig}")
    print(f"Table  : {config.ARTIFACT_DIR}/model_comparison.json")


if __name__ == "__main__":
    main()
