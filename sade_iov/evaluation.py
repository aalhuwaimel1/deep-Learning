"""Evaluation methodology (Chapter 6).

Implements the three evaluation strands of the report:

  * Risk-engine evaluation (6.2): accuracy, precision, recall (priority), F1 and
    a confusion matrix, with emphasis on minimising false negatives (an active
    attack misclassified as safe).
  * Communication-latency evaluation (6.3): per-state on-path processing cost.
  * Comparative evaluation (6.4): cumulative/average latency of the adaptive
    scheme versus a static maximum-security baseline over a driving cycle.

Figures are written to the artifacts directory.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from . import config
from .risk_engine import RiskEngine


def evaluate_risk_engine(engine: RiskEngine, partitions: dict, seeds_note: str = "") -> dict:
    """Classification metrics on the held-out partition (attack vs genuine)."""
    from sklearn.metrics import (
        accuracy_score,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
    )

    X_te = partitions["X_test"]
    y_true = partitions["y_cls_test"]
    y_pred = engine.predict_class(X_te)

    # Binary attack-detection view (genuine=0 vs any attack) for recall focus.
    bin_true = (y_true != config.PROFILE_TO_LABEL[config.PROFILE_NORMAL]).astype(int)
    bin_pred = (y_pred != config.PROFILE_TO_LABEL[config.PROFILE_NORMAL]).astype(int)

    tn = int(((bin_true == 0) & (bin_pred == 0)).sum())
    fp = int(((bin_true == 0) & (bin_pred == 1)).sum())
    fn = int(((bin_true == 1) & (bin_pred == 0)).sum())
    tp = int(((bin_true == 1) & (bin_pred == 1)).sum())
    fnr = fn / (fn + tp) if (fn + tp) else 0.0

    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_macro": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "attack_detection_recall": float(recall_score(bin_true, bin_pred, zero_division=0)),
        "attack_detection_precision": float(precision_score(bin_true, bin_pred, zero_division=0)),
        "false_negative_rate": float(fnr),
        "confusion_binary": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        "confusion_multiclass": confusion_matrix(y_true, y_pred).tolist(),
        "labels": [config.LABEL_TO_PROFILE[i] for i in range(len(config.PROFILES))],
    }


def latency_by_state(per_epoch: pd.DataFrame) -> pd.DataFrame:
    """Mean / p95 on-path latency (ms) per security state."""
    rows = []
    for state in sorted(config.STATE_NAMES):
        sub = per_epoch[per_epoch.state == state]
        if len(sub) == 0:
            continue
        onpath_ms = (sub["t_crypto"] + sub["t_aux"]) * 1e3
        total_ms = sub["t_total_adaptive"] * 1e3
        rows.append({
            "state": state,
            "label": config.STATE_LABELS[state],
            "count": int(len(sub)),
            "mean_crypto_ms": float((sub["t_crypto"] * 1e3).mean()),
            "mean_onpath_ms": float(onpath_ms.mean()),
            "mean_total_ms": float(total_ms.mean()),
            "p95_total_ms": float(np.percentile(total_ms, 95)),
        })
    return pd.DataFrame(rows)


def comparative_latency(per_epoch: pd.DataFrame) -> dict:
    """Adaptive vs static-max cumulative latency over the driving cycle."""
    cum_adaptive_ms = float(per_epoch["t_total_adaptive"].sum() * 1e3)
    cum_static_ms = float(per_epoch["t_total_static"].sum() * 1e3)
    mean_adaptive_ms = float(per_epoch["t_total_adaptive"].mean() * 1e3)
    mean_static_ms = float(per_epoch["t_total_static"].mean() * 1e3)
    reduction = 100.0 * (1 - mean_adaptive_ms / mean_static_ms) if mean_static_ms else 0.0
    return {
        "cumulative_adaptive_ms": cum_adaptive_ms,
        "cumulative_static_ms": cum_static_ms,
        "mean_adaptive_ms": mean_adaptive_ms,
        "mean_static_ms": mean_static_ms,
        "avg_latency_reduction_pct": float(reduction),
    }


# ---------------------------------------------------------------------------
# Plotting helpers (optional - require matplotlib)
# ---------------------------------------------------------------------------
def save_confusion_matrix(metrics: dict, path: str | None = None) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cm = np.array(metrics["confusion_multiclass"])
    labels = metrics["labels"]
    os.makedirs(config.ARTIFACT_DIR, exist_ok=True)
    path = path or f"{config.ARTIFACT_DIR}/confusion_matrix.png"

    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
    ax.set_yticks(range(len(labels)), labels)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title("Risk-engine confusion matrix")
    thresh = cm.max() / 2.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, int(cm[i, j]), ha="center", va="center",
                    color="white" if cm[i, j] > thresh else "black")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def save_latency_comparison(per_epoch: pd.DataFrame, path: str | None = None) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    os.makedirs(config.ARTIFACT_DIR, exist_ok=True)
    path = path or f"{config.ARTIFACT_DIR}/latency_comparison.png"
    lat = latency_by_state(per_epoch)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    ax1.bar([str(s) for s in lat["state"]], lat["mean_total_ms"], color="#4c72b0")
    ax1.set_xlabel("Security state")
    ax1.set_ylabel("Mean on-path latency (ms)")
    ax1.set_title("Per-state processing latency (adaptive)")

    cum_a = (per_epoch["t_total_adaptive"].cumsum() * 1e3)
    cum_s = (per_epoch["t_total_static"].cumsum() * 1e3)
    ax2.plot(cum_a.values, label="SADE-IoV (adaptive)", color="#2ca02c")
    ax2.plot(cum_s.values, label="Static max-security", color="#d62728", linestyle="--")
    ax2.set_xlabel("Message (epoch)")
    ax2.set_ylabel("Cumulative latency (ms)")
    ax2.set_title("Cumulative latency over driving cycle")
    ax2.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def full_report(engine: RiskEngine, partitions: dict, per_epoch: pd.DataFrame) -> dict:
    """Bundle every evaluation strand into one dict and write the figures."""
    risk = evaluate_risk_engine(engine, partitions)
    lat = latency_by_state(per_epoch)
    comp = comparative_latency(per_epoch)
    cm_path = save_confusion_matrix(risk)
    lat_path = save_latency_comparison(per_epoch)
    return {
        "risk_engine": risk,
        "latency_by_state": lat.to_dict(orient="records"),
        "comparative": comp,
        "figures": {"confusion_matrix": cm_path, "latency_comparison": lat_path},
    }
