"""Run the full SADE-IoV simulation + evaluation and print a report.

Usage:
    python -m scripts.run_simulation [--epochs N] [--seed S] [--policy STANDARD|MAX_PRIVACY]
"""
from __future__ import annotations

import argparse
import json

from sade_iov import config
from sade_iov.evaluation import full_report
from sade_iov.simulation import run_simulation


def main() -> None:
    p = argparse.ArgumentParser(description="Run the SADE-IoV simulation.")
    p.add_argument("--epochs", type=int, default=config.N_EPOCHS)
    p.add_argument("--seed", type=int, default=config.DEFAULT_SEED)
    p.add_argument("--policy", choices=[config.POLICY_STANDARD, config.POLICY_MAX_PRIVACY],
                   default=config.POLICY_STANDARD)
    p.add_argument("--save-model", action="store_true")
    args = p.parse_args()

    print(f"Generating {args.epochs} epochs, training risk engine (seed={args.seed})...")
    res = run_simulation(
        n_epochs=args.epochs, seed=args.seed,
        user_policy=args.policy, save_model=args.save_model,
    )

    report = full_report(res.engine, res.partitions, res.per_epoch)

    print("\n=== Risk-engine evaluation (Chapter 6.2) ===")
    r = report["risk_engine"]
    print(f"  accuracy ............... {r['accuracy']:.3f}")
    print(f"  attack-detection recall  {r['attack_detection_recall']:.3f}  (target >= 0.98)")
    print(f"  false-negative rate .... {r['false_negative_rate']:.4f}  (minimise)")
    print(f"  macro F1 ............... {r['f1_macro']:.3f}")
    cb = r["confusion_binary"]
    print(f"  binary confusion: TP={cb['tp']} FP={cb['fp']} FN={cb['fn']} TN={cb['tn']}")

    print("\n=== Per-state latency (Chapter 6.3) ===")
    for row in report["latency_by_state"]:
        print(f"  state {row['state']} ({row['count']:>5} msgs): "
              f"mean {row['mean_total_ms']:.4f} ms | p95 {row['p95_total_ms']:.4f} ms")

    print("\n=== Comparative latency vs static baseline (Chapter 6.4) ===")
    c = report["comparative"]
    print(f"  mean adaptive .......... {c['mean_adaptive_ms']:.4f} ms")
    print(f"  mean static (max-sec) .. {c['mean_static_ms']:.4f} ms")
    print(f"  avg latency reduction .. {c['avg_latency_reduction_pct']:.1f}%")

    print("\n=== State distribution ===")
    print(f"  {res.summary['state_distribution']}")
    print(f"  ledger records committed (async): {res.summary['ledger_committed']}")
    print(f"\nFigures written to: {report['figures']}")

    with open(f"{config.ARTIFACT_DIR}/report.json", "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"Full report: {config.ARTIFACT_DIR}/report.json")


if __name__ == "__main__":
    main()
