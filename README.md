# SADE-IoV — Situation-Aware Dynamic Encryption for the Internet of Vehicles

A Python prototype of the **SADE-IoV** adaptive-security framework described in
the graduation-project design report (GP1). Instead of applying the same heavy
cryptography to every V2X message, SADE-IoV treats vehicular security as an
*elastic, context-dependent spectrum*: it measures the situation, scores the
risk with machine learning, and scales protection up or down accordingly — while
always failing **secure**.

This repository implements the simulation prototype specified in Chapter 5 of
the report and the evaluation methodology of Chapter 6.

## The three-layer architecture

| Layer | Module | Responsibility |
|-------|--------|----------------|
| **L1 — Contextual Data Ingestion** | `sade_iov/data_generator.py` | Produces the real-time context vector `F_t = {R_RSSI, V_var, alpha_freq, D_class}` (here from a synthetic IoV telemetry stream). |
| **L2 — Multi-Factor AI Decision Core** | `sade_iov/risk_engine.py`, `sade_iov/decision_logic.py` | XGBoost risk engine outputs `S_risk ∈ [0,100]`; a deterministic, fail-secure fusion function `Ω = f(S_risk, D_class, U_policy)` chooses the state. |
| **L3 — Adaptive Security Execution** | `sade_iov/crypto_exec.py` | Applies the cipher / key-rotation / PUF / ledger configuration for the chosen state, using real PyCryptodome AES and measuring execution time. |

### The four adaptive security states

| State | Trigger | Cryptographic configuration |
|-------|---------|-----------------------------|
| **0 — Low** | Safe context, low sensitivity | AES-128 (minimum latency) |
| **1 — Medium** | Mild congestion / moderate sensitivity | AES-256 + dynamic key rotation |
| **2 — High** | Anomaly detected, or `D_class = 2` | AES-256 + PUF challenge + async ledger log |
| **3 — Critical** | Verified active attack | Channel isolation + ECU containment + driver alarm |

### Fail-secure decision logic (Section 5.6)

The orchestrator evaluates the most severe condition first, so the Critical
state is always reachable and protection can only be **raised**, never lowered:

```python
def execute_security_orchestration(S_risk, D_class, U_policy):
    if S_risk >= 95:                                   # verified active attack
        return STATE_3_CRITICAL
    if S_risk >= 85 or (D_class == 2 and S_risk > 50): # high risk OR safety floor
        return STATE_2_HIGH
    if U_policy == 'MAX_PRIVACY' or S_risk >= 40:      # policy may only RAISE
        return STATE_1_MEDIUM
    return STATE_0_LOW                                 # low-risk optimisation
```

A safety-control payload (`D_class = 2`) imposes a hard security floor that a
benign risk score cannot lower — this is what neutralises **downgrade attacks**.

## Quick start

```bash
pip install -r requirements.txt

# 1. Run the full pipeline: generate data -> train -> simulate -> evaluate
python -m scripts.run_simulation

# 2. Train and persist just the risk engine
python -m scripts.train

# 3. Launch the interactive dashboard
streamlit run dashboard/app.py

# 4. Run the unit tests (fail-secure invariants)
python -m pytest tests/ -q
```

Generated models, figures and the JSON report are written to `artifacts/`.

## What the simulation does (Section 5.8)

1. Generate a 10,000-epoch synthetic telemetry stream interleaving normal
   cruising with RF jamming, packet-injection/Sybil flooding and ECU spoofing —
   with deliberate **boundary noise** so the classification task is non-trivial.
2. Train and persist the edge-constrained XGBoost risk engine (max depth 5,
   ~100 estimators, standardised features, stratified 80:20 split).
3. Stream held-out epochs through the ingestion layer to obtain context vectors.
4. Score each vector, apply the fail-secure fusion, and obtain the state command.
5. Execute the corresponding cryptographic primitives and record timing + state.
6. Aggregate metrics and compare against a static maximum-security baseline.

## Evaluation (Chapter 6)

`scripts/run_simulation.py` reports:

* **Risk-engine metrics** — accuracy, precision, recall (priority) and F1, plus a
  confusion matrix, with emphasis on minimising **false negatives** (an active
  attack misclassified as safe).
* **Per-state latency** — on-path processing cost for each security state; State 0
  stays well within the V2X safety window.
* **Comparative latency** — average and cumulative latency of the adaptive scheme
  versus a static max-security baseline (DrivMan-like flat-rate execution),
  reporting the relative reduction during low-risk driving.

### Representative run (seed 42, 10,000 epochs)

| Metric | Result | Report target (Table 8) |
|--------|--------|--------------------------|
| Attack-detection recall | ~0.96 | ≥ 0.98 (priority) |
| Accuracy | ~0.975 | non-trivial (overlap injected) |
| State-0 latency | ~0.11 ms | < 5 ms |
| Avg. latency vs. static | **~39% lower** | lower than static |
| All four states reachable | yes | yes |

> These are simulation results from a software prototype; absolute timings
> differ from certified On-Board Units, but relative comparisons between states
> and against the static baseline remain informative (Section 6.6).

## Project layout

```
sade_iov/
  config.py           # states, thresholds, feature & profile definitions
  data_generator.py   # L1: synthetic IoV telemetry + boundary noise
  risk_engine.py      # L2: XGBoost risk classifier + S_risk regressor
  decision_logic.py   # L2: fail-secure policy-fusion orchestration
  crypto_exec.py      # L3: AES, hash-ratchet key rotation, mock PUF, async ledger
  simulation.py       # end-to-end workflow + static baseline
  evaluation.py       # Chapter 6 metrics + figures
scripts/
  train.py            # train & persist the risk engine
  run_simulation.py   # full pipeline + report
dashboard/
  app.py              # Streamlit live-orchestration demo
tests/
  test_decision_logic.py
```

## Notes on fidelity to the design

* **Real ciphers, real timings** — AES-128/256-GCM via PyCryptodome.
* **Dynamic key rotation** is a genuine one-way hash ratchet
  (`K_k = KDF(K_{k-1}, salt_k)`) giving forward/backward secrecy; the rotation
  interval shortens as risk rises.
* **Asynchronous blockchain logging** uses a background worker that chains record
  hashes off the critical path, so ledger commits never gate safety messages.
* **PUF** is mocked with a keyed-hash challenge-response plus a small settling
  delay to keep on-path cost realistic.

The framework deliberately reuses well-known primitives (AES, PUF, consortium
ledger); the contribution is the *orchestration logic* that decides which
protections to invoke, in which context, and how often to refresh keys.
