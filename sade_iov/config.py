"""Central configuration for the SADE-IoV prototype.

All thresholds, feature definitions, security-state definitions and
per-profile telemetry distributions are collected here so that the rest of the
code (data generator, risk engine, decision logic, crypto execution and the
dashboard) shares a single source of truth.

The values mirror the design report (Chapter 4 - System Design, Chapter 5 -
Implementation Plan, Chapter 6 - Evaluation): the four adaptive security states
(Table 5), the ingestion features (Table 4) and the training configuration
(Table 7).
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Security states (Table 5: the four adaptive security states)
# ---------------------------------------------------------------------------
STATE_0_LOW = 0       # AES-128, minimum latency
STATE_1_MEDIUM = 1    # AES-256 + dynamic key rotation
STATE_2_HIGH = 2      # AES-256 + PUF challenge + async ledger log
STATE_3_CRITICAL = 3  # Channel isolation + ECU containment + driver alarm

STATE_NAMES = {
    STATE_0_LOW: "STATE_0_LOW",
    STATE_1_MEDIUM: "STATE_1_MEDIUM",
    STATE_2_HIGH: "STATE_2_HIGH",
    STATE_3_CRITICAL: "STATE_3_CRITICAL",
}

STATE_LABELS = {
    STATE_0_LOW: "0 - Low (AES-128)",
    STATE_1_MEDIUM: "1 - Medium (AES-256 + key rotation)",
    STATE_2_HIGH: "2 - High (AES-256 + PUF + async ledger)",
    STATE_3_CRITICAL: "3 - Critical (channel isolation + alarm)",
}

# ---------------------------------------------------------------------------
# Data payload sensitivity classes (Table 4: D_class)
#   0 = infotainment, 1 = localisation, 2 = safety-control
# ---------------------------------------------------------------------------
DCLASS_INFOTAINMENT = 0
DCLASS_LOCALISATION = 1
DCLASS_SAFETY = 2

# ---------------------------------------------------------------------------
# Decision-logic thresholds (Section 5.6: execute_security_orchestration)
# ---------------------------------------------------------------------------
RISK_CRITICAL = 95   # >= 95  -> STATE_3_CRITICAL (verified active attack)
RISK_HIGH = 85       # >= 85  -> STATE_2_HIGH
SAFETY_FLOOR_RISK = 50  # D_class == 2 and S_risk > 50 -> at least HIGH
RISK_MEDIUM = 40     # >= 40  -> STATE_1_MEDIUM

# User-policy levels (policy may only RAISE, never lower, the final state)
POLICY_STANDARD = "STANDARD"
POLICY_MAX_PRIVACY = "MAX_PRIVACY"

# ---------------------------------------------------------------------------
# Telemetry feature names (Table 4: ingestion-layer contextual features)
#   R_RSSI : received signal strength (dBm) - jamming/spoofing indicator
#   V_var  : velocity variance (CAN-bus)    - ECU-compromise indicator
#   alpha_freq : packet arrival-rate anomaly - flooding/injection indicator
# ---------------------------------------------------------------------------
FEATURES = ["R_RSSI", "V_var", "alpha_freq"]

# ---------------------------------------------------------------------------
# Threat profiles for synthetic generation (Section 5.4)
#   Each profile defines (mean, std) for the three telemetry features.
#   Distributions deliberately overlap so the classification task is realistic
#   (boundary noise is added on top by the generator).
# ---------------------------------------------------------------------------
PROFILE_NORMAL = "normal"
PROFILE_JAMMING = "jamming"          # RF jamming -> RSSI collapses
PROFILE_INJECTION = "injection"      # packet-injection / Sybil flooding -> alpha_freq spikes
PROFILE_SPOOFING = "spoofing"        # telemetry / ECU spoofing -> velocity variance erratic

PROFILES = [PROFILE_NORMAL, PROFILE_JAMMING, PROFILE_INJECTION, PROFILE_SPOOFING]

# Sampling weights (normal driving dominates a real cycle).
PROFILE_WEIGHTS = {
    PROFILE_NORMAL: 0.55,
    PROFILE_JAMMING: 0.15,
    PROFILE_INJECTION: 0.15,
    PROFILE_SPOOFING: 0.15,
}

# (mean, std) per feature, per profile. RSSI in dBm (more negative = weaker).
PROFILE_DISTRIBUTIONS = {
    PROFILE_NORMAL:    {"R_RSSI": (-60.0, 4.0), "V_var": (0.5, 0.3),  "alpha_freq": (10.0, 1.5)},
    PROFILE_JAMMING:   {"R_RSSI": (-90.0, 6.0), "V_var": (0.8, 0.5),  "alpha_freq": (9.0, 3.0)},
    PROFILE_INJECTION: {"R_RSSI": (-62.0, 5.0), "V_var": (0.7, 0.4),  "alpha_freq": (40.0, 8.0)},
    PROFILE_SPOOFING:  {"R_RSSI": (-61.0, 5.0), "V_var": (6.0, 2.0),  "alpha_freq": (12.0, 3.0)},
}

# Numeric attack label per profile (0 = genuine, used for detection metrics).
PROFILE_TO_LABEL = {
    PROFILE_NORMAL: 0,
    PROFILE_JAMMING: 1,
    PROFILE_INJECTION: 2,
    PROFILE_SPOOFING: 3,
}
LABEL_TO_PROFILE = {v: k for k, v in PROFILE_TO_LABEL.items()}

# Reproducibility
DEFAULT_SEED = 42
N_EPOCHS = 10_000           # Section 5.4: synthetic dataset of 10,000 epochs
TEST_SIZE = 0.20            # Table 7: stratified 80:20 split

# XGBoost training configuration (Table 7, edge-constrained).
XGB_PARAMS = {
    "max_depth": 5,             # edge-constrained
    "n_estimators": 100,        # ~100 estimators
    "learning_rate": 0.1,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "objective": "multi:softprob",
    "n_jobs": 0,
}

# Artifact locations
ARTIFACT_DIR = "artifacts"
MODEL_PATH = f"{ARTIFACT_DIR}/risk_engine.json"
SCALER_PATH = f"{ARTIFACT_DIR}/scaler.joblib"
REGRESSOR_PATH = f"{ARTIFACT_DIR}/risk_regressor.json"
