"""Layer 2 - Policy Fusion & deterministic decision logic (Section 4.5.2 / 5.6).

The fused orchestration command ``Omega_t = f(S_risk, D_class, U_policy)`` is
produced by deterministic, *fail-secure* code rather than relying solely on the
ML output. The most severe condition is evaluated first so that the Critical
state is always reachable, and the sensitivity floor / user policy can only
*raise* - never lower - the final state. This neutralises downgrade attacks:
manipulating context toward 'benign' cannot push safety-control traffic into a
weak cipher.

The implementation is the corrected logic from Section 5.6 of the report.
"""
from __future__ import annotations

from . import config


def execute_security_orchestration(
    S_risk: float,
    D_class: int,
    U_policy: str = config.POLICY_STANDARD,
) -> int:
    """Map (risk score, payload class, user policy) to a security state.

    Rules are checked from most to least severe so that escalation always wins
    (fail-secure). Returns one of STATE_0_LOW .. STATE_3_CRITICAL.
    """
    # Rule 1: verified active attack (checked FIRST so it is reachable).
    if S_risk >= config.RISK_CRITICAL:
        return config.STATE_3_CRITICAL          # isolate channel + driver alarm

    # Rule 2: high risk, or any safety-control payload above the floor.
    if S_risk >= config.RISK_HIGH or (
        D_class == config.DCLASS_SAFETY and S_risk > config.SAFETY_FLOOR_RISK
    ):
        return config.STATE_2_HIGH              # AES-256 + PUF + async ledger log

    # Rule 3: user-policy escalation (may only RAISE the level).
    if U_policy == config.POLICY_MAX_PRIVACY or S_risk >= config.RISK_MEDIUM:
        return config.STATE_1_MEDIUM            # AES-256 + dynamic key rotation

    # Rule 4: default low-risk optimisation.
    return config.STATE_0_LOW                   # AES-128, minimum latency


def floor_for_class(D_class: int) -> int:
    """Hard minimum security state imposed by a payload class.

    Safety-control payloads (D_class == 2) cannot be served below STATE_2_HIGH
    once any non-trivial risk is present; this is the fail-secure floor used in
    the security analysis (downgrade resistance).
    """
    if D_class == config.DCLASS_SAFETY:
        return config.STATE_2_HIGH
    return config.STATE_0_LOW


def explain(S_risk: float, D_class: int, U_policy: str = config.POLICY_STANDARD) -> str:
    """Human-readable justification for the chosen state (for the dashboard)."""
    state = execute_security_orchestration(S_risk, D_class, U_policy)
    if state == config.STATE_3_CRITICAL:
        reason = f"S_risk={S_risk:.0f} >= {config.RISK_CRITICAL}: verified active attack."
    elif state == config.STATE_2_HIGH:
        if D_class == config.DCLASS_SAFETY and S_risk > config.SAFETY_FLOOR_RISK:
            reason = (
                f"Safety-control payload (D_class=2) with S_risk={S_risk:.0f} "
                f"> {config.SAFETY_FLOOR_RISK}: sensitivity floor forces HIGH."
            )
        else:
            reason = f"S_risk={S_risk:.0f} >= {config.RISK_HIGH}: high risk."
    elif state == config.STATE_1_MEDIUM:
        if U_policy == config.POLICY_MAX_PRIVACY and S_risk < config.RISK_MEDIUM:
            reason = "User policy MAX_PRIVACY raises baseline to MEDIUM."
        else:
            reason = f"S_risk={S_risk:.0f} >= {config.RISK_MEDIUM}: moderate risk."
    else:
        reason = f"S_risk={S_risk:.0f} < {config.RISK_MEDIUM}: low-risk optimisation."
    return f"{config.STATE_LABELS[state]} | {reason}"
