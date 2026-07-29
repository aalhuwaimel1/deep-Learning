"""Rigorous evaluation experiments for SADE-IoV (professional results).

Bundles the scientifically important analyses a design-phase report should
carry, all reproducible from a fixed set of seeds:

  * multi_seed_risk_engine  — accuracy / recall / F1 / FNR as mean ± std over
    several random seeds (not a single optimistic point estimate).
  * roc_pr_curves           — ROC and Precision-Recall curves for attack
    detection, with AUC.
  * ablation                — SADE-IoV (adaptive) vs a static-maximum policy
    vs a no-risk (sensitivity-only) policy, comparing both processing latency
    and the protection actually applied during attacks.
  * energy_comparison       — per-message energy of the adaptive scheme vs the
    static baselines (see :mod:`sade_iov.energy`).
  * latency_budget          — per-state latency against the V2X safety window.

Every function returns plain dicts/arrays; :func:`run_all` also writes figures
and a machine-readable ``experiments.json`` under the artifacts directory.
"""
from __future__ import annotations

import json
import os

import numpy as np

from . import config, energy
from .data_generator import generate_dataset
from .decision_logic import execute_security_orchestration
from .evaluation import evaluate_risk_engine
from .risk_engine import train_risk_engine
from .simulation import run_simulation

SAFETY_WINDOW_MS = 5.0  # State-0 target latency budget (report Table 8)


# ---------------------------------------------------------------------------
# 1. Multi-seed statistical evaluation
# ---------------------------------------------------------------------------
def multi_seed_risk_engine(seeds: list[int], n_epochs: int = config.N_EPOCHS) -> dict:
    """Train the XGBoost risk engine over several seeds; return mean ± std."""
    keys = ["accuracy", "attack_detection_recall", "attack_detection_precision",
            "f1_macro", "false_negative_rate"]
    rows = {k: [] for k in keys}
    for s in seeds:
        df = generate_dataset(n_epochs=n_epochs, seed=s)
        engine, parts = train_risk_engine(df, seed=s)
        m = evaluate_risk_engine(engine, parts)
        for k in keys:
            rows[k].append(m[k])
    return {
        "seeds": seeds,
        "n_epochs": n_epochs,
        "metrics": {k: {"mean": float(np.mean(v)), "std": float(np.std(v)),
                        "values": [float(x) for x in v]} for k, v in rows.items()},
    }


# ---------------------------------------------------------------------------
# 2. ROC / PR curves for attack detection
# ---------------------------------------------------------------------------
def roc_pr_curves(seed: int = config.DEFAULT_SEED, n_epochs: int = config.N_EPOCHS) -> dict:
    from sklearn.metrics import auc, precision_recall_curve, roc_curve

    df = generate_dataset(n_epochs=n_epochs, seed=seed)
    engine, parts = train_risk_engine(df, seed=seed)
    proba = engine.predict_proba(parts["X_test"])  # columns = profile classes
    normal = config.PROFILE_TO_LABEL[config.PROFILE_NORMAL]
    attack_score = 1.0 - proba[:, normal]           # P(any attack)
    y_true = (parts["y_cls_test"] != normal).astype(int)

    fpr, tpr, _ = roc_curve(y_true, attack_score)
    prec, rec, _ = precision_recall_curve(y_true, attack_score)
    return {
        "roc": {"fpr": fpr.tolist(), "tpr": tpr.tolist(), "auc": float(auc(fpr, tpr))},
        "pr": {"precision": prec.tolist(), "recall": rec.tolist(),
               "ap": float(auc(rec, prec))},
    }


# ---------------------------------------------------------------------------
# 3. Ablation: adaptive vs static-max vs no-risk
# ---------------------------------------------------------------------------
def ablation(seed: int = config.DEFAULT_SEED, n_epochs: int = config.N_EPOCHS) -> dict:
    """Compare protection vs cost for three orchestration policies.

    Uses the real per-state latencies measured by the simulation, then applies
    each policy to the same held-out messages.
    """
    res = run_simulation(n_epochs=n_epochs, seed=seed)
    pe = res.per_epoch

    # Real measured mean latency (ms) per state from the adaptive run.
    lat_state = {}
    for s in sorted(config.STATE_NAMES):
        sub = pe[pe.state == s]
        if len(sub):
            lat_state[s] = float((sub["t_total_adaptive"] * 1e3).mean())
    # Fill any unseen state from the nearest heavier one.
    for s in [0, 1, 2, 3]:
        lat_state.setdefault(s, lat_state.get(2, 0.3))

    risk = pe["S_risk"].to_numpy()
    dcl = pe["D_class"].to_numpy()
    atk = pe["is_attack"].to_numpy().astype(bool)

    def sade_state(i):
        return int(execute_security_orchestration(float(risk[i]), int(dcl[i])))

    def norisk_state(i):  # sensitivity-only, ignores the ML risk score
        d = int(dcl[i])
        return config.STATE_2_HIGH if d == 2 else (config.STATE_1_MEDIUM if d == 1 else config.STATE_0_LOW)

    n = len(pe)
    policies = {
        "SADE-IoV (adaptive)": [sade_state(i) for i in range(n)],
        "Static maximum": [config.STATE_2_HIGH] * n,
        "No-risk (sensitivity only)": [norisk_state(i) for i in range(n)],
    }
    out = {}
    for name, states in policies.items():
        states = np.array(states)
        mean_lat = float(np.mean([lat_state[s] for s in states]))
        # attack response = fraction of ATTACK messages met with ELEVATED crypto
        # (state >= MEDIUM, i.e. AES-256+), the security-relevant recall.
        prot = float(np.mean(states[atk] >= config.STATE_1_MEDIUM)) if atk.any() else 0.0
        out[name] = {
            "mean_latency_ms": mean_lat,
            "attack_response_recall": prot,
            "heavy_share": float(np.mean(states >= config.STATE_2_HIGH)),
        }
    return {"seed": seed, "n_epochs": n_epochs, "lat_state_ms": lat_state, "policies": out}


# ---------------------------------------------------------------------------
# 4. Energy comparison + 5. Latency budget
# ---------------------------------------------------------------------------
def energy_comparison(seed: int = config.DEFAULT_SEED, n_epochs: int = config.N_EPOCHS) -> dict:
    res = run_simulation(n_epochs=n_epochs, seed=seed)
    counts = res.per_epoch["state"].value_counts().to_dict()
    counts = {int(k): int(v) for k, v in counts.items()}
    rotations = int(res.per_epoch["rotated"].sum()) if "rotated" in res.per_epoch else 0
    return energy.summarize_energy(counts, rotations=rotations)


def latency_budget(seed: int = config.DEFAULT_SEED, n_epochs: int = config.N_EPOCHS,
                   deadline_ms: float = SAFETY_WINDOW_MS) -> dict:
    res = run_simulation(n_epochs=n_epochs, seed=seed)
    pe = res.per_epoch
    ms = pe["t_total_adaptive"] * 1e3
    per_state = {}
    for s in sorted(config.STATE_NAMES):
        sub = ms[pe.state == s]
        if len(sub):
            per_state[int(s)] = {
                "mean_ms": float(sub.mean()),
                "p95_ms": float(np.percentile(sub, 95)),
                "p99_ms": float(np.percentile(sub, 99)),
            }
    return {
        "deadline_ms": deadline_ms,
        "overall_compliance_pct": float((ms <= deadline_ms).mean() * 100.0),
        "per_state": per_state,
    }


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def fig_roc_pr(curves: dict, path: str) -> str:
    plt = _plt()
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 4.3))
    a.plot(curves["roc"]["fpr"], curves["roc"]["tpr"], color="#2ca02c",
           label=f"AUC = {curves['roc']['auc']:.3f}")
    a.plot([0, 1], [0, 1], "--", color="#888")
    a.set_xlabel("False positive rate"); a.set_ylabel("True positive rate")
    a.set_title("ROC — attack detection"); a.legend(loc="lower right")
    b.plot(curves["pr"]["recall"], curves["pr"]["precision"], color="#4c72b0",
           label=f"AP = {curves['pr']['ap']:.3f}")
    b.set_xlabel("Recall"); b.set_ylabel("Precision")
    b.set_title("Precision–Recall"); b.legend(loc="lower left")
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)
    return path


def fig_multiseed(ms: dict, path: str) -> str:
    plt = _plt()
    keys = ["accuracy", "attack_detection_recall", "f1_macro", "false_negative_rate"]
    labels = ["accuracy", "recall", "F1", "FNR"]
    means = [ms["metrics"][k]["mean"] for k in keys]
    stds = [ms["metrics"][k]["std"] for k in keys]
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    x = np.arange(len(keys))
    ax.bar(x, means, yerr=stds, capsize=6, color=["#4c72b0", "#2ca02c", "#8172b2", "#c44e52"])
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 1.02)
    ax.set_title(f"Risk engine over {len(ms['seeds'])} seeds (mean ± std)")
    for i, (m, s) in enumerate(zip(means, stds)):
        ax.text(i, m + 0.02, f"{m:.3f}", ha="center", fontsize=9)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)
    return path


def fig_ablation(ab: dict, path: str) -> str:
    plt = _plt()
    names = list(ab["policies"].keys())
    lat = [ab["policies"][n]["mean_latency_ms"] for n in names]
    prot = [ab["policies"][n]["attack_response_recall"] * 100 for n in names]
    x = np.arange(len(names))
    fig, ax1 = plt.subplots(figsize=(8, 4.5))
    ax2 = ax1.twinx()
    ax1.bar(x - 0.2, lat, width=0.38, color="#c44e52", label="mean latency (ms)")
    ax2.bar(x + 0.2, prot, width=0.38, color="#2ca02c", label="attack response — elevated crypto (%)")
    ax1.set_xticks(x, [n.replace(" ", "\n") for n in names], fontsize=9)
    ax1.set_ylabel("mean latency (ms)", color="#c44e52")
    ax2.set_ylabel("attack response (%)", color="#2ca02c")
    ax2.set_ylim(0, 105)
    ax1.set_title("Ablation — cost vs protection")
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)
    return path


def fig_energy(en: dict, path: str) -> str:
    plt = _plt()
    labels = ["AES-128\nonly", "AES-256\nonly", "AES-256+PUF\n(static max)", "SADE-IoV\n(adaptive)"]
    vals = [en["static_aes128_uj"], en["static_aes256_uj"], en["static_max_uj"], en["adaptive_uj"]]
    cols = ["#eab308", "#f59e0b", "#c44e52", "#2ca02c"]
    fig, ax = plt.subplots(figsize=(7, 4.3))
    bars = ax.bar(labels, [v / 1000 for v in vals], color=cols)
    ax.set_ylabel("total energy (mJ) over the run")
    ax.set_title(f"Energy — same {en['messages']} messages, per strategy")
    for brec, v in zip(bars, vals):
        ax.text(brec.get_x() + brec.get_width() / 2, v / 1000, f"{v/1000:.2f}",
                ha="center", va="bottom", fontsize=9)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)
    return path


def fig_latency_cdf(seed: int, n_epochs: int, path: str) -> str:
    plt = _plt()
    res = run_simulation(n_epochs=n_epochs, seed=seed)
    a = np.sort(res.per_epoch["t_total_adaptive"].to_numpy() * 1e3)
    s = np.sort(res.per_epoch["t_total_static"].to_numpy() * 1e3)
    ya = np.linspace(0, 1, len(a)); ys = np.linspace(0, 1, len(s))
    fig, ax = plt.subplots(figsize=(6.6, 4.2))
    ax.plot(a, ya, color="#2ca02c", label="SADE-IoV (adaptive)")
    ax.plot(s, ys, color="#c44e52", linestyle="--", label="Static maximum")
    ax.set_xlabel("per-message latency (ms)"); ax.set_ylabel("cumulative fraction")
    ax.set_title("Latency CDF"); ax.legend(loc="lower right")
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def run_all(n_epochs: int = config.N_EPOCHS, seeds: list[int] | None = None,
            quick: bool = False, outdir: str = config.ARTIFACT_DIR) -> dict:
    seeds = seeds or [42, 7, 13, 99, 123]
    if quick:
        seeds = seeds[:3]
    os.makedirs(outdir, exist_ok=True)
    seed0 = seeds[0]

    ms = multi_seed_risk_engine(seeds, n_epochs)
    curves = roc_pr_curves(seed0, n_epochs)
    ab = ablation(seed0, n_epochs)
    en = energy_comparison(seed0, n_epochs)
    lb = latency_budget(seed0, n_epochs)

    figs = {
        "roc_pr": fig_roc_pr(curves, f"{outdir}/roc_pr.png"),
        "multiseed": fig_multiseed(ms, f"{outdir}/multiseed.png"),
        "ablation": fig_ablation(ab, f"{outdir}/ablation.png"),
        "energy": fig_energy(en, f"{outdir}/energy.png"),
        "latency_cdf": fig_latency_cdf(seed0, n_epochs, f"{outdir}/latency_cdf.png"),
    }
    results = {
        "n_epochs": n_epochs, "seeds": seeds,
        "multi_seed_risk_engine": ms,
        "roc_pr_auc": {"roc_auc": curves["roc"]["auc"], "pr_ap": curves["pr"]["ap"]},
        "ablation": ab, "energy": en, "latency_budget": lb, "figures": figs,
    }
    with open(f"{outdir}/experiments.json", "w") as fh:
        json.dump(results, fh, indent=2)
    return results
