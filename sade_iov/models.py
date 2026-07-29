"""Multi-model risk-classifier comparison (addresses "use multiple ways").

The design report selects XGBoost for the risk engine because of its fast edge
inference and strong tabular accuracy. To justify that choice empirically -
rather than by assertion - this module trains several classifiers on the same
partition and reports accuracy, precision, recall (the priority metric), F1,
plus training and per-sample inference time.

Models compared:
  * XGBoost                (gradient-boosted trees, the chosen engine)
  * Random Forest          (bagged trees baseline)
  * Extra Trees            (extremely randomised trees)
  * Logistic Regression    (linear baseline)
  * SVM (RBF kernel)       (kernel baseline)
  * MLP                    (small neural network)

All models share the same standardised features and stratified split, so the
comparison is apples-to-apples.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from xgboost import XGBClassifier

from . import config


def _build_models(seed: int, n_classes: int) -> dict:
    """Instantiate the candidate models (edge-constrained where applicable)."""
    return {
        "XGBoost": XGBClassifier(
            max_depth=5, n_estimators=100, learning_rate=0.1,
            subsample=0.9, colsample_bytree=0.9, num_class=n_classes,
            objective="multi:softprob", eval_metric="mlogloss",
            random_state=seed, n_jobs=0,
        ),
        "RandomForest": RandomForestClassifier(
            n_estimators=200, max_depth=12, random_state=seed, n_jobs=-1,
        ),
        "ExtraTrees": ExtraTreesClassifier(
            n_estimators=200, max_depth=14, random_state=seed, n_jobs=-1,
        ),
        "LogisticRegression": LogisticRegression(
            max_iter=1000, random_state=seed,
        ),
        "SVM_RBF": SVC(kernel="rbf", C=2.0, gamma="scale", random_state=seed),
        "MLP": MLPClassifier(
            hidden_layer_sizes=(64, 32), max_iter=300, early_stopping=True,
            random_state=seed,
        ),
    }


@dataclass
class ModelResult:
    name: str
    accuracy: float
    precision_macro: float
    recall_macro: float
    f1_macro: float
    attack_recall: float
    false_negative_rate: float
    train_time_s: float
    infer_ms_per_sample: float


def compare_models(
    X_train, y_train, X_test, y_test,
    seed: int = config.DEFAULT_SEED,
    normal_label: int = 0,
) -> pd.DataFrame:
    """Train every candidate model and return a ranked comparison table.

    Features are standardised on the training split. Ranking is by attack
    recall first (the safety-critical metric), then macro-F1.
    """
    scaler = StandardScaler().fit(X_train)
    Xtr = scaler.transform(X_train)
    Xte = scaler.transform(X_test)
    n_classes = int(np.max(np.concatenate([y_train, y_test]))) + 1

    rows = []
    for name, model in _build_models(seed, n_classes).items():
        t0 = time.perf_counter()
        model.fit(Xtr, y_train)
        train_t = time.perf_counter() - t0

        # Warm up, then time a full-batch inference and amortise per sample.
        model.predict(Xte[: min(16, len(Xte))])
        t1 = time.perf_counter()
        y_pred = model.predict(Xte)
        infer_ms = (time.perf_counter() - t1) / len(Xte) * 1e3

        bin_true = (y_test != normal_label).astype(int)
        bin_pred = (y_pred != normal_label).astype(int)
        tp = int(((bin_true == 1) & (bin_pred == 1)).sum())
        fn = int(((bin_true == 1) & (bin_pred == 0)).sum())
        fnr = fn / (fn + tp) if (fn + tp) else 0.0

        rows.append(ModelResult(
            name=name,
            accuracy=float(accuracy_score(y_test, y_pred)),
            precision_macro=float(precision_score(y_test, y_pred, average="macro", zero_division=0)),
            recall_macro=float(recall_score(y_test, y_pred, average="macro", zero_division=0)),
            f1_macro=float(f1_score(y_test, y_pred, average="macro", zero_division=0)),
            attack_recall=float(recall_score(bin_true, bin_pred, zero_division=0)),
            false_negative_rate=float(fnr),
            train_time_s=float(train_t),
            infer_ms_per_sample=float(infer_ms),
        ).__dict__)

    df = pd.DataFrame(rows)
    df = df.sort_values(["attack_recall", "f1_macro"], ascending=False).reset_index(drop=True)
    return df


def save_comparison_figure(df: pd.DataFrame, path: str | None = None) -> str:
    """Bar chart comparing attack recall and macro-F1 across models."""
    import os

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    os.makedirs(config.ARTIFACT_DIR, exist_ok=True)
    path = path or f"{config.ARTIFACT_DIR}/model_comparison.png"

    order = df.sort_values("attack_recall")
    y = np.arange(len(order))
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    ax.barh(y - 0.2, order["attack_recall"], height=0.38, label="attack recall", color="#2ca02c")
    ax.barh(y + 0.2, order["f1_macro"], height=0.38, label="macro F1", color="#4c72b0")
    ax.set_yticks(y, order["name"])
    ax.set_xlim(0, 1.0)
    ax.set_xlabel("score")
    ax.set_title("Risk-classifier comparison (higher is better)")
    for i, (r, f) in enumerate(zip(order["attack_recall"], order["f1_macro"])):
        ax.text(r + 0.01, i - 0.2, f"{r:.3f}", va="center", fontsize=8)
        ax.text(f + 0.01, i + 0.2, f"{f:.3f}", va="center", fontsize=8)
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path
