"""Synthetic IoV telemetry generator (Section 5.4).

Generates a stream of ``N`` epochs that interleaves normal cruising with three
attack profiles (RF jamming, packet-injection/Sybil flooding, telemetry/ECU
spoofing). Boundary noise is deliberately injected so that classes overlap near
decision boundaries and the classification task is *not* trivially separable -
exactly as required by the design report to avoid inflated accuracy.

For every epoch we emit:
    * the three telemetry features (R_RSSI, V_var, alpha_freq)
    * the payload sensitivity class D_class in {0,1,2}
    * the discrete attack label (0=genuine .. 3=spoofing) for detection metrics
    * a ground-truth situational risk score in [0, 100] used to train the
      risk regressor that feeds the decision logic.

The pseudocode in Section 5.6 of the report is realised here:

    for t in range(10000):
        profile = sample({normal, jamming, injection, spoofing}, weights)
        F_t = draw_features(profile)          # bounded distributions
        F_t = add_boundary_noise(F_t, sigma)  # overlapping/realistic
        label = attack_label(profile)
        dataset.append((F_t, label))
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def _profile_risk(profile: str, intensity: float) -> float:
    """Ground-truth situational risk for a profile at a given intensity.

    Genuine traffic stays low; attacks scale from the 'suspicious' band up to
    the 'verified active attack' band so that every security state is
    reachable across a driving cycle.
    """
    if profile == config.PROFILE_NORMAL:
        return 5.0 + 25.0 * intensity          # ~ [5, 30]
    # Attacks: base 55 rising to ~100 with intensity.
    base = {
        config.PROFILE_JAMMING: 55.0,
        config.PROFILE_INJECTION: 58.0,
        config.PROFILE_SPOOFING: 60.0,
    }[profile]
    return base + 45.0 * intensity             # ~ [55, 105] -> clipped to 100


def generate_dataset(
    n_epochs: int = config.N_EPOCHS,
    seed: int = config.DEFAULT_SEED,
    boundary_sigma: float = 0.25,
) -> pd.DataFrame:
    """Return a DataFrame with the synthetic telemetry stream.

    Parameters
    ----------
    n_epochs:
        Number of epochs to generate (default 10,000).
    seed:
        RNG seed for reproducibility.
    boundary_sigma:
        Fraction of each feature's std added as extra Gaussian "boundary
        noise" to force class overlap. Larger -> harder classification.
    """
    rng = np.random.default_rng(seed)

    profiles = list(config.PROFILE_WEIGHTS.keys())
    weights = np.array([config.PROFILE_WEIGHTS[p] for p in profiles])
    weights = weights / weights.sum()

    chosen = rng.choice(profiles, size=n_epochs, p=weights)
    # Per-epoch attack intensity (how strong the deviation is this epoch).
    intensity = rng.beta(2.0, 2.0, size=n_epochs)

    rows = []
    for profile, inten in zip(chosen, intensity):
        dist = config.PROFILE_DISTRIBUTIONS[profile]
        feat = {}
        for fname in config.FEATURES:
            mean, std = dist[fname]
            # Base draw, scaled toward the mean for low-intensity attacks so
            # that weak attacks sit close to the normal cloud (overlap).
            if profile != config.PROFILE_NORMAL:
                normal_mean = config.PROFILE_DISTRIBUTIONS[config.PROFILE_NORMAL][fname][0]
                eff_mean = normal_mean + (mean - normal_mean) * (0.55 + 0.45 * inten)
            else:
                eff_mean = mean
            value = rng.normal(eff_mean, std)
            # Boundary noise: extra Gaussian proportional to the feature std.
            value += rng.normal(0.0, boundary_sigma * std)
            feat[fname] = value

        # Payload sensitivity class is independent of the attack profile.
        d_class = rng.choice(
            [config.DCLASS_INFOTAINMENT, config.DCLASS_LOCALISATION, config.DCLASS_SAFETY],
            p=[0.45, 0.35, 0.20],
        )

        risk = _profile_risk(profile, inten)
        # Add measurement noise to the ground-truth risk, then clip to [0,100].
        risk = float(np.clip(risk + rng.normal(0.0, 4.0), 0.0, 100.0))

        rows.append(
            {
                "R_RSSI": feat["R_RSSI"],
                "V_var": feat["V_var"],
                "alpha_freq": feat["alpha_freq"],
                "D_class": int(d_class),
                "profile": profile,
                "label": config.PROFILE_TO_LABEL[profile],
                "is_attack": int(profile != config.PROFILE_NORMAL),
                "risk_true": risk,
            }
        )

    return pd.DataFrame(rows)


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    df = generate_dataset()
    print(df.head())
    print("\nClass balance:")
    print(df["profile"].value_counts())
    print(f"\nrisk_true range: [{df.risk_true.min():.1f}, {df.risk_true.max():.1f}]")
