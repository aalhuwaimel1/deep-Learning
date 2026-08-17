# SADE-IoV — Situation-Aware Dynamic Encryption for the Internet of Vehicles
## Graduation Project 2 (GP2) — Implementation and Evaluation Report

**Supervised by:** Dr. Mohammed Abid
**Prepared by:** Abdulrhman Alluwaymi (202410671) · Abdulmajeed Alhuwaimel (202410088)
**Al Yamamah University — 2026**

**Repository:** https://github.com/aalhuwaimel1/deep-Learning · **Live demo:** https://aalhuwaimel1.github.io/deep-Learning/

---

## Abstract

Graduation Project 1 (GP1) proposed **SADE-IoV**, a three-layer framework that
treats vehicular security as an elastic, context-dependent spectrum rather than
a fixed one-size-fits-all policy, and specified a Python simulation plan with a
set of design-phase targets to be validated later. This report (GP2) presents
the **implemented prototype and its measured evaluation**. We realised the three
layers in Python, trained the machine-learning risk engine on both a **generated
(synthetic)** dataset and an **existing, report-cited benchmark (VeReMi-style
position-falsification data)**, and evaluated the system with a rigorous,
reproducible protocol (stratified 80:20 split, multi-seed statistics, ROC/PR,
ablation, latency and energy models). Across five seeds the risk engine reaches
**accuracy 0.978 ± 0.004** and **attack-detection recall 0.965 ± 0.003**
(ROC-AUC 0.997). A three-way comparison shows SADE-IoV attains **~97% attack
coverage at roughly half the latency and energy** of encrypting every message at
maximum strength, whereas a single light cipher is fast but leaves attacks
unprotected. An interactive browser simulator demonstrates the framework driving
through Riyadh, reacting to injected attacks, and blocking a downgrade attack in
real time. The measured results confirm the GP1 design intent: **security where
it matters, speed and battery everywhere else.**

**Keywords:** Internet of Vehicles, V2X, Adaptive Security, Context-Aware
Cryptography, Machine Learning, XGBoost, AES, PUF, Risk Assessment, VeReMi.

---

## Chapter 1 — Introduction

### 1.1 From design (GP1) to implementation (GP2)
GP1 established the problem, the threat landscape, and the SADE-IoV architecture,
and closed with an *implementation plan* and a table of *expected outcomes*.
GP2 carries that story forward: it builds the software-defined prototype the plan
described, runs it on real and generated data, and reports the **actual**
measurements against the GP1 targets.

### 1.2 Objectives of the implementation phase
1. Implement the three SADE-IoV layers as working, tested software.
2. Train and validate the risk engine on an **existing** and a **generated**
   dataset, using a proper train/test split.
3. Compare **three security solutions** (adaptive vs two static baselines) on
   latency, energy, and attack coverage.
4. Provide an interactive demonstrator and a reproducible evaluation pipeline.

### 1.3 Research questions revisited
- *Can context-driven adaptation match the protection of always-maximum
  encryption at lower cost?* — answered quantitatively in Chapter 5.
- *Is the risk engine accurate and robust enough to drive the decision?* —
  answered with multi-seed metrics and ROC/PR analysis.
- *Does the fail-secure design resist downgrade attacks?* — demonstrated in
  Chapters 3 and 6.

### 1.4 Structure of this report
Chapter 2 recaps the design; Chapter 3 details the implementation; Chapter 4 the
datasets and ML pipeline; Chapter 5 the measured results; Chapter 6 the
interactive simulator; Chapter 7 discusses results against the GP1 targets;
Chapter 8 concludes.

---

## Chapter 2 — Recap of the SADE-IoV Design

SADE-IoV is deployed as three decoupled layers:

| Layer | Role |
|-------|------|
| **L1 — Contextual Data Ingestion** | Builds the real-time context vector `F_t = {R_RSSI, V_var, α_freq, D_class}` from the physical/network layer. |
| **L2 — Multi-Factor AI Decision Core** | An XGBoost risk engine outputs `S_risk ∈ [0,100]`; a deterministic, fail-secure fusion `Ω = f(S_risk, D_class, U_policy)` selects the state. |
| **L3 — Adaptive Security Execution** | Applies the cipher / key-rotation / PUF / ledger configuration for the chosen state. |

**Four adaptive states:** 0-Low (AES-128), 1-Medium (AES-256 + key rotation),
2-High (AES-256 + PUF + async ledger), 3-Critical (channel isolation + alarm).

**Fail-secure fusion (Section 5.6 of GP1):** the most severe rule is evaluated
first, and the safety floor (`D_class = 2`) and user policy may only *raise* the
state — never lower it. This is the property that neutralises downgrade attacks.

---

## Chapter 3 — Implementation

### 3.1 Software stack
Python 3.11 with NumPy/Pandas (telemetry & features), scikit-learn + XGBoost
(risk engine), PyCryptodome (real AES-GCM timings), Matplotlib (figures) and a
browser simulator using the Web Crypto API. The project is packaged
(`pyproject.toml`), linted (ruff), unit-tested (pytest), and runs in CI (GitHub
Actions).

### 3.2 Layer 1 — Contextual data ingestion
`data_generator.py` produces the context stream; `datasets.py` maps any source
(synthetic, VeReMi, CICIoV2024) into a single unified schema so the engine is
dataset-agnostic.

### 3.3 Layer 2 — Risk engine and fail-secure fusion
`risk_engine.py` trains an edge-constrained XGBoost model (max depth 5, ~100
estimators, standardised features) that emits `S_risk`. `decision_logic.py`
implements the deterministic orchestration exactly as specified in GP1, with
unit tests pinning the fail-secure invariants (safety floor, monotonicity,
policy-only-raises).

### 3.4 Layer 3 — Adaptive execution
`crypto_exec.py` realises: **real AES-128/256-GCM** encryption; a **one-way
hash-ratchet** key rotation `K_k = KDF(K_{k-1}, salt_k)` giving forward/backward
secrecy with an adaptive interval (rare when calm, frequent under threat); a
**mock PUF** challenge-response for hardware identity in State 2; and an
**asynchronous consortium-ledger** worker that chains record hashes off the
critical path, so audit writes never gate safety messages.

### 3.5 Security properties (mapped to the threat model)
Confidentiality/integrity via AES-GCM; authenticity via PUF + certificates;
downgrade resistance via the fail-secure floor; replay resistance via the
rotation counter; forward/backward secrecy via the ratchet; auditability via the
ledger. A full attack→defence matrix is in `docs/THREAT_MODEL.md`.

---

## Chapter 4 — Datasets and Machine-Learning Pipeline

### 4.1 Two datasets: existing + generated
Per the GP1 plan, evaluation uses both a recognised benchmark and a generated
set:

- **Existing (VeReMi-style):** reproduces the public VeReMi position-falsification
  attacker taxonomy cited in GP1 (genuine, constant-position, constant-offset,
  random-position, random-offset, eventual-stop). The real VeReMi / CICIoV2024
  files plug into the identical loader (`scripts/fetch_datasets.py`).
- **Generated (synthetic):** 10,000 epochs interleaving normal cruising with RF
  jamming, packet-injection/Sybil flooding and telemetry/ECU spoofing, with
  deliberate **boundary noise** so the task is non-trivial.

Figure: `artifacts/dataset.png` (class balance + per-class feature
distributions) shows how each feature separates an attack family — RSSI collapse
for jamming, `α_freq` spikes for injection, `V_var` spread for spoofing.

### 4.2 Train/test split and how accuracy is identified
Each dataset is split **stratified 80:20** (4,800 train / 1,200 test). Accuracy
is measured on the **held-out test partition** the model never trained on — the
standard, non-optimistic way to identify accuracy. Every experiment is repeated
over multiple random seeds and reported as **mean ± std** (a fixed seed
reproduces the exact number for reproducibility).

### 4.3 Model selection
Six classifiers were compared (`scripts/compare_models.py`). XGBoost was retained
because it matches the best models on recall/F1 while training fastest and
keeping inference among the cheapest — the right trade-off for constrained edge
OBUs.

---

## Chapter 5 — Results and Evaluation

*(All figures in `artifacts/`; regenerate with `python -m scripts.reproduce_all`
and `python -m scripts.compare_solutions`.)*

### 5.1 Risk-engine accuracy (mean ± std over 5 seeds)

| Dataset | Train / Test | Accuracy | Recall (attack) | F1 |
|---------|--------------|----------|-----------------|----|
| Generated (synthetic) | 4,800 / 1,200 | 0.978 ± 0.004 | 0.965 ± 0.003 | 0.975 ± 0.005 |
| Existing (VeReMi-style) | 4,800 / 1,200 | 0.979 ± 0.004 | 0.962 ± 0.009 | 0.979 ± 0.004 |

ROC-AUC = 0.997, PR-AP = 0.997 (`artifacts/roc_pr.png`). The false-negative rate
(an attack misread as safe — the most dangerous error) is **0.035 ± 0.001**.
Figure `artifacts/multiseed.png` shows the spread with error bars.

### 5.2 Ablation — why the ML risk core matters

| Policy | Mean latency | Attack response (elevated crypto) | Heavy usage |
|--------|-------------|-----------------------------------|-------------|
| **SADE-IoV (adaptive)** | 0.16 ms | **97%** | 15% |
| Static maximum | 0.28 ms | 100% | 100% |
| No-risk (sensitivity only) | 0.17 ms | 58% ⚠ | 21% |

Removing the risk engine (no-risk) leaves ~42% of attacks under weak protection;
SADE-IoV recovers near-maximum protection at ~45% lower latency
(`artifacts/ablation.png`).

### 5.3 Three solutions compared (both datasets)

| Solution | Latency | Energy | Attack coverage |
|----------|---------|--------|-----------------|
| **SADE-IoV (adaptive)** | 0.157 ms | 2.7 µJ | **97%** |
| Static strong (AES-256 + PUF) | 0.300 ms | 6.8 µJ | 100% |
| Static light (AES-128 only) | 0.120 ms | 1.8 µJ | 0% ⚠ |

The same pattern holds on both datasets (`artifacts/three_solutions.png`):
SADE-IoV reaches ~97% attack coverage at roughly **half** the latency and energy
of encrypting everything, while a single light cipher is fast but insecure.

### 5.4 Latency budget and energy
All messages complete within the **5 ms** State-0 V2X safety window (100%
compliance). Over the same messages, SADE-IoV spends ≈ **3.3 mJ** vs ≈ **8.2 mJ**
for encrypt-all — about **60% less energy** (`artifacts/energy.png`,
`artifacts/latency_cdf.png`).

### 5.5 Dynamic key rotation and audit
The hash-ratchet rotates rarely in low-risk states and aggressively (every ~8
messages) under threat; the asynchronous ledger committed all high-risk records
off the critical path in every run.

---

## Chapter 6 — Interactive Simulator (Demonstrator)

A self-contained browser application (`index.html`, deployed via GitHub Pages)
drives a connected car across a stylised map of **Riyadh**. It:

- receives multiple V2X message types (neighbouring-vehicle beacons, roadside/RSU
  road info) and shows them in a plain-language activity feed;
- scores the live threat, adapts the encryption state, and performs **real
  in-browser AES-GCM** with visible key rotation, PUF checks and ledger logging;
- lets the user inject jamming / spoofing / flooding, and demonstrates a **live
  downgrade attack** being blocked by the fail-secure floor;
- ends each timed trip with a report and a **measured** cipher comparison, and
  exposes a **Results** page that cycles through real per-seed evaluation runs.

This makes the framework's behaviour and value legible to a non-specialist
audience during the defence.

---

## Chapter 7 — Discussion: Results vs GP1 Targets

| GP1 target (Table 8) | Result | Verdict |
|----------------------|--------|---------|
| Detection recall ≥ 98% (priority) | 0.965 ± 0.003 | Slightly below target; see note |
| False negatives minimised | FNR 0.035 ± 0.001 | Met (low, prioritised) |
| State-0 latency < 5 ms | ≪ 5 ms (µs-scale) | Met with wide margin |
| Avg. latency lower than static | ~45% lower | Met |
| Inference negligible / bounded | Amortised, negligible | Met |

**On the recall target.** Recall lands at ~0.96 rather than 0.98 **by design**:
boundary noise was injected so classes overlap realistically — inflating accuracy
to ~1.0 would signal a trivially separable, unrealistic dataset. The fail-secure
floors bound the consequence of any miss, since safety traffic cannot be
downgraded regardless of the score.

### 7.1 Threats to validity
Synthetic telemetry may not capture the full diversity of real driving (mitigated
by cross-checking against the VeReMi-style benchmark); absolute latency/energy are
software estimates rather than certified-OBU measurements (relative comparisons
remain informative); and an adversary crafting adversarial ML inputs is a residual
risk that motivates future robustness work.

---

## Chapter 8 — Conclusion and Future Work

GP2 delivered a working, tested, reproducible implementation of SADE-IoV and
validated the GP1 design intent with measured results: the adaptive, risk-based
scheme achieves near-maximum protection at roughly half the latency and energy of
blanket maximum encryption, on both a generated and an existing dataset, and it
resists downgrade attacks by construction.

**Key contributions.** A dataset-agnostic risk engine with rigorous multi-seed
evaluation; a real adaptive execution layer (AES, hash-ratchet, PUF, async
ledger); a three-solution cost-vs-protection comparison; and an interactive
demonstrator.

**Future work.** Integrate the full public VeReMi / CICIoV2024 archives;
adversarial-robustness hardening of the risk engine; on-OBU energy/latency
measurement; and a hardware PUF and consortium-ledger integration.

---

## References

Key references from GP1 are retained (IEEE 1609.2 / ETSI TS 102 940 V2X security;
VeReMi [9] and its extension [17]; CICIoV2024 [23]; AES and PUF literature).
Software and reproduction scripts: this repository.
