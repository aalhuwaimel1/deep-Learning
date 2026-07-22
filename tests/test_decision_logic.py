"""Unit tests for the fail-secure decision logic (Section 5.6).

These tests pin the safety-critical invariants of the orchestrator: the
Critical state must be reachable, the safety-control floor must hold, and the
user policy must only ever *raise* the security state.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sade_iov import config
from sade_iov.decision_logic import execute_security_orchestration as orch


def test_critical_state_reachable():
    assert orch(96, 0) == config.STATE_3_CRITICAL
    assert orch(100, 2) == config.STATE_3_CRITICAL


def test_high_risk_maps_to_high_state():
    assert orch(90, 0) == config.STATE_2_HIGH


def test_safety_floor_overrides_benign_risk():
    # Safety-control payload (D_class=2) with moderate risk is forced to HIGH,
    # even though the risk alone would resolve to a lower tier (downgrade-proof).
    assert orch(60, config.DCLASS_SAFETY) == config.STATE_2_HIGH
    # Infotainment at the same risk resolves to MEDIUM, not HIGH.
    assert orch(60, config.DCLASS_INFOTAINMENT) == config.STATE_1_MEDIUM


def test_safety_floor_not_triggered_below_threshold():
    # At/below the safety floor risk (50) the floor does not yet force HIGH.
    assert orch(45, config.DCLASS_SAFETY) == config.STATE_1_MEDIUM


def test_medium_threshold():
    assert orch(40, 0) == config.STATE_1_MEDIUM
    assert orch(39, 0) == config.STATE_0_LOW


def test_low_state_default():
    assert orch(10, config.DCLASS_INFOTAINMENT) == config.STATE_0_LOW


def test_user_policy_only_raises():
    # MAX_PRIVACY raises an otherwise-LOW context to MEDIUM ...
    assert orch(5, config.DCLASS_INFOTAINMENT, config.POLICY_MAX_PRIVACY) == config.STATE_1_MEDIUM
    # ... but never lowers a HIGH/CRITICAL decision.
    assert orch(96, 0, config.POLICY_MAX_PRIVACY) == config.STATE_3_CRITICAL
    assert orch(88, 0, config.POLICY_MAX_PRIVACY) == config.STATE_2_HIGH


def test_monotonic_non_decreasing_in_risk():
    # Higher risk must never yield a weaker state (fail-secure monotonicity).
    for d in (0, 1, 2):
        states = [orch(r, d) for r in range(0, 101)]
        assert all(b >= a for a, b in zip(states, states[1:])), f"non-monotonic for D_class={d}"
