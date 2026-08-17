"""Energy model for the adaptive security execution layer.

On a constrained On-Board Unit (OBU) the cost of security is not only *latency*
but also *energy*, which matters for battery/thermal budgets. This module gives
a transparent, parameterised estimate of the energy each security state spends
per message, so the adaptive scheme can be compared against static baselines on
energy as well as time.

The constants are design-phase estimates (order-of-magnitude figures reported
for embedded AES-GCM and PUF evaluation in the literature), expressed per
representative 128-byte V2X beacon. They are model parameters, not measured on
certified hardware — absolute values will differ in deployment, but the
*relative* comparison between states and strategies is the informative result.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import config

# --- per-operation energy parameters (micro-joules per 128-byte message) ----
E_AES128_UJ = 1.8    # AES-128-GCM encrypt of a beacon
E_AES256_UJ = 2.5    # AES-256-GCM (larger key schedule / more rounds)
E_PUF_UJ = 4.0       # one PUF challenge-response (hardware identity check)
E_ROTATE_UJ = 0.6    # a hash-ratchet key-derivation step
E_LEDGER_ENQUEUE_UJ = 0.3  # on-path cost to enqueue an async ledger record


@dataclass(frozen=True)
class EnergyBreakdown:
    state: int
    cipher_uj: float
    puf_uj: float
    rotate_uj: float
    ledger_uj: float

    @property
    def total_uj(self) -> float:
        return self.cipher_uj + self.puf_uj + self.rotate_uj + self.ledger_uj


def energy_for_state(state: int, rotated: bool = False) -> EnergyBreakdown:
    """Estimated on-path energy (uJ) for one message handled in ``state``."""
    if state == config.STATE_0_LOW:
        return EnergyBreakdown(state, E_AES128_UJ, 0.0, 0.0, 0.0)
    if state == config.STATE_1_MEDIUM:
        return EnergyBreakdown(state, E_AES256_UJ, 0.0,
                               E_ROTATE_UJ if rotated else 0.0, 0.0)
    if state == config.STATE_2_HIGH:
        return EnergyBreakdown(state, E_AES256_UJ, E_PUF_UJ,
                               E_ROTATE_UJ if rotated else 0.0, E_LEDGER_ENQUEUE_UJ)
    # STATE_3_CRITICAL: channel isolated, no payload transmitted
    return EnergyBreakdown(state, 0.0, 0.0, 0.0, 0.0)


# Static baselines process *every* message at a fixed configuration.
def energy_static_max_uj() -> float:
    """Per-message energy of an always-maximum (AES-256 + PUF) policy."""
    return E_AES256_UJ + E_PUF_UJ + E_LEDGER_ENQUEUE_UJ


def energy_static_aes256_uj() -> float:
    return E_AES256_UJ


def energy_static_aes128_uj() -> float:
    return E_AES128_UJ


def summarize_energy(state_counts: dict[int, int], rotations: int = 0) -> dict:
    """Total energy for a run given per-state message counts.

    Returns the adaptive total and the static baselines for the same messages,
    plus the relative saving of the adaptive scheme versus always-maximum.
    """
    n = sum(state_counts.values())
    # Adaptive: sum each state's per-message energy (rotations amortised).
    adaptive = 0.0
    for state, count in state_counts.items():
        eb = energy_for_state(state, rotated=False)
        adaptive += eb.total_uj * count
    adaptive += E_ROTATE_UJ * rotations

    static_max = energy_static_max_uj() * n
    static_256 = energy_static_aes256_uj() * n
    static_128 = energy_static_aes128_uj() * n
    saving_pct = 100.0 * (1 - adaptive / static_max) if static_max else 0.0
    return {
        "messages": n,
        "adaptive_uj": adaptive,
        "static_max_uj": static_max,
        "static_aes256_uj": static_256,
        "static_aes128_uj": static_128,
        "energy_saving_vs_max_pct": saving_pct,
        "adaptive_uj_per_msg": adaptive / n if n else 0.0,
        "static_max_uj_per_msg": energy_static_max_uj(),
    }
