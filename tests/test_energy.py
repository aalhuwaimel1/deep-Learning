"""Tests for the energy model and its use in the ablation/experiments."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sade_iov import config, energy


def test_energy_monotonic_in_state():
    """Heavier states never cost less energy than lighter ones (State 3 aside)."""
    e0 = energy.energy_for_state(config.STATE_0_LOW).total_uj
    e1 = energy.energy_for_state(config.STATE_1_MEDIUM, rotated=True).total_uj
    e2 = energy.energy_for_state(config.STATE_2_HIGH, rotated=True).total_uj
    assert e0 < e1 < e2


def test_critical_state_transmits_nothing():
    assert energy.energy_for_state(config.STATE_3_CRITICAL).total_uj == 0.0


def test_static_max_is_costliest_per_message():
    assert energy.energy_static_max_uj() > energy.energy_static_aes256_uj()
    assert energy.energy_static_aes256_uj() > energy.energy_static_aes128_uj()


def test_adaptive_saves_energy_vs_static_max():
    # A realistic mix dominated by low-risk messages should cost less than
    # encrypting everything at maximum.
    counts = {config.STATE_0_LOW: 700, config.STATE_1_MEDIUM: 200,
              config.STATE_2_HIGH: 90, config.STATE_3_CRITICAL: 10}
    s = energy.summarize_energy(counts, rotations=50)
    assert s["adaptive_uj"] < s["static_max_uj"]
    assert 0 < s["energy_saving_vs_max_pct"] < 100
