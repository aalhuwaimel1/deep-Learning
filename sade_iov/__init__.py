"""SADE-IoV: Situation-Aware Dynamic Encryption for the Internet of Vehicles.

A Python prototype of the three-layer adaptive-security framework described in
the GP1 design report:

    Layer 1  Contextual Data Ingestion   -> data_generator (synthetic telemetry)
    Layer 2  Multi-Factor AI Decision Core -> risk_engine + decision_logic
    Layer 3  Adaptive Security Execution  -> crypto_exec

Plus a full simulation workflow (simulation) and evaluation suite (evaluation).
"""
from . import config, crypto_exec, data_generator, datasets, decision_logic
from . import evaluation, models, risk_engine, simulation

__all__ = [
    "config",
    "crypto_exec",
    "data_generator",
    "datasets",
    "decision_logic",
    "evaluation",
    "models",
    "risk_engine",
    "simulation",
]

__version__ = "0.1.0"
