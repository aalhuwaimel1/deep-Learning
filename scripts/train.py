"""Train and persist the SADE-IoV risk engine (Section 5.5).

Usage:
    python -m scripts.train [--epochs N] [--seed S]
"""
from __future__ import annotations

import argparse

from sade_iov import config
from sade_iov.data_generator import generate_dataset
from sade_iov.evaluation import evaluate_risk_engine
from sade_iov.risk_engine import train_risk_engine


def main() -> None:
    p = argparse.ArgumentParser(description="Train the SADE-IoV risk engine.")
    p.add_argument("--epochs", type=int, default=config.N_EPOCHS)
    p.add_argument("--seed", type=int, default=config.DEFAULT_SEED)
    args = p.parse_args()

    print(f"Generating {args.epochs} epochs (seed={args.seed})...")
    df = generate_dataset(n_epochs=args.epochs, seed=args.seed)
    print("Training XGBoost risk engine (max_depth=5, ~100 estimators)...")
    engine, parts = train_risk_engine(df, seed=args.seed)
    engine.save()
    print(f"Saved model to {config.MODEL_PATH}")

    metrics = evaluate_risk_engine(engine, parts)
    print(f"accuracy={metrics['accuracy']:.3f}  "
          f"recall(attack)={metrics['attack_detection_recall']:.3f}  "
          f"FNR={metrics['false_negative_rate']:.4f}")


if __name__ == "__main__":
    main()
