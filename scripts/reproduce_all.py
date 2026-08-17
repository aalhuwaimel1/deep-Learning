"""Reproduce every headline result and figure in one command.

Runs the rigorous experiment suite (multi-seed metrics, ROC/PR, ablation,
energy, latency budget) and prints a compact summary. All figures and a
machine-readable ``experiments.json`` land in the artifacts directory.

Usage:
    python -m scripts.reproduce_all                      # full (5 seeds)
    python -m scripts.reproduce_all --seeds 3 --quick    # fast CI run
    python -m scripts.reproduce_all --epochs 5000
"""
from __future__ import annotations

import argparse

from sade_iov import config
from sade_iov.experiments import run_all


def main() -> None:
    p = argparse.ArgumentParser(description="Reproduce SADE-IoV experiments.")
    p.add_argument("--epochs", type=int, default=config.N_EPOCHS)
    p.add_argument("--seeds", type=int, default=5, help="number of random seeds")
    p.add_argument("--quick", action="store_true", help="use fewer seeds (CI)")
    args = p.parse_args()

    all_seeds = [42, 7, 13, 99, 123, 256, 512, 1000]
    seeds = all_seeds[: max(1, args.seeds)]

    print(f"Running experiments · epochs={args.epochs} · seeds={seeds}")
    r = run_all(n_epochs=args.epochs, seeds=seeds, quick=args.quick)

    ms = r["multi_seed_risk_engine"]["metrics"]
    print("\n=== Risk engine (mean ± std over seeds) ===")
    for k in ["accuracy", "attack_detection_recall", "f1_macro", "false_negative_rate"]:
        print(f"  {k:24s} {ms[k]['mean']:.3f} ± {ms[k]['std']:.3f}")
    print(f"  ROC-AUC = {r['roc_pr_auc']['roc_auc']:.3f} · PR-AP = {r['roc_pr_auc']['pr_ap']:.3f}")

    print("\n=== Ablation — cost vs protection ===")
    for name, m in r["ablation"]["policies"].items():
        print(f"  {name:28s} latency={m['mean_latency_ms']:.4f} ms · "
              f"response@attack={m['attack_response_recall']*100:5.1f}% · "
              f"heavy={m['heavy_share']*100:4.1f}%")

    en = r["energy"]
    print("\n=== Energy (same messages) ===")
    print(f"  static max : {en['static_max_uj']/1000:.2f} mJ")
    print(f"  SADE-IoV   : {en['adaptive_uj']/1000:.2f} mJ  "
          f"({en['energy_saving_vs_max_pct']:.1f}% less)")

    lb = r["latency_budget"]
    print(f"\n=== Latency budget (deadline {lb['deadline_ms']} ms) ===")
    print(f"  overall compliance: {lb['overall_compliance_pct']:.1f}%")

    print(f"\nFigures + experiments.json written to {config.ARTIFACT_DIR}/")


if __name__ == "__main__":
    main()
