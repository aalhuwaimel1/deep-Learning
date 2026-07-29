# SADE-IoV — Situation-Aware Dynamic Encryption for the Internet of Vehicles

[![CI](https://github.com/aalhuwaimel1/deep-Learning/actions/workflows/ci.yml/badge.svg)](https://github.com/aalhuwaimel1/deep-Learning/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-informational.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Live demo](https://img.shields.io/badge/live-demo-38bdf8.svg)](https://aalhuwaimel1.github.io/deep-Learning/)

A prototype of the **SADE-IoV** adaptive-security framework (graduation project,
GP1). Instead of applying the same heavy cryptography to every V2X message,
SADE-IoV treats vehicular security as an *elastic, context-dependent spectrum*:
it measures the situation, scores the risk with machine learning, and scales
protection up or down per message — while always failing **secure**.

> 🚗 **Interactive demo:** <https://aalhuwaimel1.github.io/deep-Learning/> — drive
> a connected car through Riyadh, inject V2X attacks, and watch the encryption
> adapt in real time, ending with a measured comparison against static schemes.

## The three-layer architecture

| Layer | Module | Responsibility |
|-------|--------|----------------|
| **L1 — Contextual Data Ingestion** | `sade_iov/data_generator.py`, `datasets.py` | Real-time context vector `F_t = {R_RSSI, V_var, alpha_freq, D_class}` |
| **L2 — Multi-Factor AI Decision Core** | `risk_engine.py`, `decision_logic.py` | XGBoost risk score `S_risk ∈ [0,100]` + fail-secure fusion `Ω = f(S_risk, D_class, U_policy)` |
| **L3 — Adaptive Security Execution** | `crypto_exec.py`, `energy.py` | Cipher / key-rotation / PUF / ledger per state, with real AES timings and an energy model |

### The four adaptive security states

| State | Trigger | Cryptographic configuration |
|-------|---------|-----------------------------|
| **0 — Low** | Safe context, low sensitivity | AES-128 (minimum latency) |
| **1 — Medium** | Mild congestion / moderate sensitivity | AES-256 + dynamic key rotation |
| **2 — High** | Anomaly detected, or `D_class = 2` | AES-256 + PUF challenge + async ledger log |
| **3 — Critical** | Verified active attack | Channel isolation + ECU containment + driver alarm |

The fail-secure orchestrator (`decision_logic.py`) checks the most severe rule
first and lets the safety floor / user policy only **raise** the state — which
is what neutralises **downgrade attacks** (see [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md)).

## Results (reproducible)

All numbers below are produced by `python -m scripts.reproduce_all` (synthetic
benchmark, mean ± std over seeds). Regenerate every figure with one command.

**Risk engine — attack detection** (5 seeds):

| Metric | Result |
|--------|--------|
| Accuracy | 0.977 ± 0.004 |
| Attack-detection recall | **0.965 ± 0.001** |
| Macro-F1 | 0.973 ± 0.005 |
| False-negative rate | 0.035 ± 0.001 |
| ROC-AUC / PR-AP | 0.997 / 0.997 |

**Ablation — cost vs protection** (why the ML risk core matters):

| Policy | Mean latency | Attack response (elevated crypto) | Heavy usage |
|--------|-------------|-----------------------------------|-------------|
| **SADE-IoV (adaptive)** | **0.16 ms** | **97%** | 15% |
| Static maximum (encrypt-all) | 0.28 ms | 100% | 100% |
| No-risk (sensitivity only) | 0.17 ms | 58% ⚠ | 21% |

SADE-IoV meets ~97% of attacks with elevated cryptography — near the static
maximum — at **~45% lower latency** and **~60% lower energy**, while the no-risk
baseline is cheap but leaves ~42% of attacks under weak protection.

**Energy & latency budget:** SADE-IoV ≈ 3.3 mJ vs 8.2 mJ for encrypt-all over
the same messages (≈60% less); 100% of messages complete within the 5 ms
State-0 safety window.

**Multiple models** (`scripts/compare_models.py`) — XGBoost is chosen because it
matches the top models on recall/F1 while training fastest and keeping inference
among the cheapest, which suits constrained edge OBUs.

Figures written to `artifacts/`: `roc_pr.png`, `multiseed.png`, `ablation.png`,
`energy.png`, `latency_cdf.png`, `confusion_matrix.png`, `model_comparison.png`.

## Quick start

```bash
pip install -e ".[dev,dashboard]"      # or: pip install -r requirements.txt

python -m scripts.run_simulation       # end-to-end pipeline + report
python -m scripts.reproduce_all        # all rigorous experiments + figures
python -m scripts.compare_models       # compare 6 classifiers
streamlit run dashboard/app.py         # interactive dashboard
pytest -q                              # unit tests (fail-secure invariants + energy)
```

## Datasets

A unified schema (`R_RSSI, V_var, alpha_freq, D_class, label`) lets any source
feed the risk engine (`sade_iov/datasets.py`):

| Source | Year | What it covers |
|--------|------|----------------|
| Synthetic generator | — | 10,000 epochs, channel-level jamming / injection / spoofing with boundary noise |
| **VeReMi** (+ extension) | 2018 / 2020 | V2X position-falsification misbehaviour |
| **CICIoV2024** | 2024 | In-vehicle CAN-bus spoofing / DoS |

The public benchmarks are large, so they are fetched on demand:

```bash
python -m scripts.fetch_datasets                 # sources + where to place files
python -m scripts.compare_models --dataset all   # after placing files under data/
```

## Project layout

```
sade_iov/
  config.py           data_generator.py   datasets.py
  risk_engine.py      decision_logic.py   models.py
  crypto_exec.py      energy.py           simulation.py
  evaluation.py       experiments.py
scripts/
  train.py  run_simulation.py  compare_models.py  fetch_datasets.py  reproduce_all.py
dashboard/app.py      # Streamlit dashboard
index.html            # interactive Riyadh V2X simulator (GitHub Pages)
docs/THREAT_MODEL.md  # adversary model + attack→defence matrix
tests/                # decision-logic invariants + energy model
.github/workflows/ci.yml
```

## Notes on fidelity

- **Real ciphers, real timings** — AES-128/256-GCM (PyCryptodome in Python, Web
  Crypto in the browser demo).
- **Dynamic key rotation** is a genuine one-way hash ratchet
  (`K_k = KDF(K_{k-1}, salt_k)`) giving forward/backward secrecy.
- **Asynchronous ledger** chains record hashes off the critical path.
- **PUF** is mocked with a keyed hash + settle delay.
- Absolute latency/energy are software estimates; the *relative* comparisons are
  the informative results.

## License

MIT — see [LICENSE](LICENSE).
