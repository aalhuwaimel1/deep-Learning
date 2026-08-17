"""Compare three security solutions on both an existing and a generated dataset.

Addresses the review points:
  * use an **existing dataset** (VeReMi-style, cited in the report) *and* a
    **generated** (synthetic) dataset;
  * report **how accuracy is identified** — a held-out test split with standard
    metrics on each dataset;
  * show the **train/test split** sizes explicitly;
  * compare **three solutions** (SADE-IoV adaptive vs static-strong vs
    static-light) and report the results side by side.

Writes ``artifacts/three_solutions.png`` and prints the tables.

Usage:
    python -m scripts.compare_solutions [--epochs N] [--seed S]
"""
from __future__ import annotations

import argparse

from sade_iov import config
from sade_iov.experiments import compare_datasets, fig_solutions


def main() -> None:
    p = argparse.ArgumentParser(description="Compare three solutions on two datasets.")
    p.add_argument("--epochs", type=int, default=config.N_EPOCHS)
    p.add_argument("--seed", type=int, default=config.DEFAULT_SEED)
    args = p.parse_args()

    print(f"Comparing three solutions · epochs={args.epochs} · seed={args.seed}\n")
    cmp = compare_datasets(seed=args.seed, n_epochs=args.epochs)

    for dname, d in cmp.items():
        print("=" * 72)
        print(f"DATASET: {dname}")
        print(f"  train/test split : {d['train_n']} train  /  {d['test_n']} test "
              f"(stratified 80:20) · attacks {d['attack_ratio']*100:.1f}%")
        c = d["classifier"]
        print(f"  risk-engine accuracy (held-out test): acc={c['accuracy']:.3f} · "
              f"recall={c['attack_recall']:.3f} · F1={c['f1_macro']:.3f}")
        print(f"  {'solution':<28}{'latency(ms)':>12}{'energy(µJ)':>12}{'attack-safe%':>14}")
        for name, m in d["solutions"].items():
            print(f"  {name:<28}{m['mean_latency_ms']:>12.3f}{m['mean_energy_uj']:>12.2f}"
                  f"{m['attack_response_pct']:>13.1f}%")
        print()

    fig = fig_solutions(cmp, f"{config.ARTIFACT_DIR}/three_solutions.png")
    print(f"Figure written to {fig}")


if __name__ == "__main__":
    main()
