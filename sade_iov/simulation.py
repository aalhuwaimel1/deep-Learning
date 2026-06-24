"""End-to-end SADE-IoV simulation workflow (Section 5.8).

Stages exercised here mirror the report's simulation workflow:

  1. Generate the synthetic telemetry stream (normal + attack epochs).
  2. Train and persist the XGBoost risk engine on the training partition.
  3. Stream held-out epochs through the ingestion layer -> context vectors.
  4. Score each vector, apply the fail-secure fusion -> state command.
  5. Execute the corresponding cryptographic primitives, record timing + state.
  6. Aggregate metrics for the comparative analysis against the static baseline.

A *static maximum-security* baseline (DrivMan-like flat-rate execution) runs the
same payloads at AES-256 + PUF on every message, so the per-cycle latency
reduction of the adaptive scheme can be quantified.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config
from .crypto_exec import AsyncLedger, SecurityExecutor
from .data_generator import generate_dataset
from .decision_logic import execute_security_orchestration
from .risk_engine import RiskEngine, train_risk_engine

PAYLOAD = b"V2X-SAFETY-BEACON:" + b"\x00" * 110  # ~128-byte representative message


@dataclass
class SimulationResult:
    per_epoch: pd.DataFrame
    engine: RiskEngine
    partitions: dict
    summary: dict = field(default_factory=dict)


INFERENCE_WINDOW = 20  # messages share one risk inference (Section 4.5.1)


def _amortised_infer_time(engine: RiskEngine, X) -> tuple[np.ndarray, float]:
    """Batch-score every context vector and return (S_risk[], per-msg infer time).

    The report states inference runs *per context window* rather than per packet
    and is "negligible / bounded" (Tables 8, Section 4.5.1). We therefore time a
    single batched inference and amortise it across an INFERENCE_WINDOW of
    messages so the per-message cost reflects window-level evaluation.
    """
    # Warm up (first call pays XGBoost/JIT setup that would skew the timing).
    engine.predict_risk(X[: min(len(X), 8)])
    t0 = time.perf_counter()
    risks = engine.predict_risk(X)
    batch_time = time.perf_counter() - t0
    per_window_time = batch_time / len(X) * INFERENCE_WINDOW  # cost of one window
    per_msg_infer = per_window_time / INFERENCE_WINDOW        # amortised per message
    return risks, per_msg_infer


def run_simulation(
    n_epochs: int = config.N_EPOCHS,
    seed: int = config.DEFAULT_SEED,
    user_policy: str = config.POLICY_STANDARD,
    df: pd.DataFrame | None = None,
    engine: RiskEngine | None = None,
    partitions: dict | None = None,
    save_model: bool = False,
) -> SimulationResult:
    """Run the full pipeline and return per-epoch records + summary.

    If ``engine``/``partitions`` are supplied they are reused; otherwise a
    fresh dataset is generated and the risk engine is trained.
    """
    if engine is None or partitions is None:
        if df is None:
            df = generate_dataset(n_epochs=n_epochs, seed=seed)
        engine, partitions = train_risk_engine(df, seed=seed)
        if save_model:
            engine.save()

    df = partitions["df"]
    idx_test = partitions["idx_test"]
    test_df = df.iloc[idx_test].reset_index(drop=True)
    X_test = test_df[config.FEATURES].to_numpy(dtype=float)

    ledger = AsyncLedger()
    adaptive = SecurityExecutor(ledger=ledger)
    static = SecurityExecutor(ledger=ledger)  # baseline shares the ledger sink

    risks, t_infer = _amortised_infer_time(engine, X_test)

    records = []
    for i in range(len(test_df)):
        d_class = int(test_df.loc[i, "D_class"])
        s_risk = float(risks[i])

        # --- adaptive path -------------------------------------------------
        state = execute_security_orchestration(s_risk, d_class, user_policy)
        ares = adaptive.execute(state, PAYLOAD, epoch=i)
        adaptive_total = t_infer + ares.t_onpath

        # --- static max-security baseline (always STATE_2_HIGH) ------------
        bres = static.execute(config.STATE_2_HIGH, PAYLOAD, epoch=i)
        static_total = bres.t_onpath  # no risk inference needed for a flat policy

        records.append({
            "epoch": i,
            "R_RSSI": X_test[i, 0],
            "V_var": X_test[i, 1],
            "alpha_freq": X_test[i, 2],
            "D_class": d_class,
            "profile": test_df.loc[i, "profile"],
            "label_true": int(test_df.loc[i, "label"]),
            "is_attack": int(test_df.loc[i, "is_attack"]),
            "risk_true": float(test_df.loc[i, "risk_true"]),
            "S_risk": s_risk,
            "state": state,
            "transmitted": ares.transmitted,
            "t_infer": t_infer,
            "t_crypto": ares.t_crypto,
            "t_aux": ares.t_aux,
            "t_total_adaptive": adaptive_total,
            "t_total_static": static_total,
            "key_bits": ares.key_bits,
            "rotated": ares.rotated,
            "puf_used": ares.puf_used,
        })

    per_epoch = pd.DataFrame(records)
    adaptive.close()
    static.close()
    ledger.flush()
    ledger.stop()

    summary = _summarise(per_epoch)
    summary["ledger_committed"] = ledger.committed_count()
    return SimulationResult(per_epoch=per_epoch, engine=engine,
                            partitions=partitions, summary=summary)


def _summarise(per_epoch: pd.DataFrame) -> dict:
    state_counts = per_epoch["state"].value_counts().sort_index().to_dict()
    mean_adaptive = per_epoch["t_total_adaptive"].mean()
    mean_static = per_epoch["t_total_static"].mean()
    reduction = 100.0 * (1.0 - mean_adaptive / mean_static) if mean_static else 0.0
    return {
        "n_epochs": int(len(per_epoch)),
        "state_distribution": {int(k): int(v) for k, v in state_counts.items()},
        "mean_latency_adaptive_ms": float(mean_adaptive * 1e3),
        "mean_latency_static_ms": float(mean_static * 1e3),
        "latency_reduction_pct": float(reduction),
        "mean_state0_latency_ms": float(
            per_epoch.loc[per_epoch.state == config.STATE_0_LOW, "t_total_adaptive"].mean() * 1e3
        ) if (per_epoch.state == config.STATE_0_LOW).any() else None,
    }


if __name__ == "__main__":  # pragma: no cover - manual run
    res = run_simulation()
    print("Summary:")
    for k, v in res.summary.items():
        print(f"  {k}: {v}")
