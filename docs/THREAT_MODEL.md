# SADE-IoV — Threat Model & Defence Coverage

This document states the adversary model for SADE-IoV and maps each modelled
attack to the mechanism that mitigates it. SADE-IoV is an **orchestration layer
above** standardised V2X security (IEEE 1609.2 / ETSI TS 102 940 certificates
and pseudonyms); it assumes those provide baseline message authentication and
privacy, and adds context-driven, adaptive protection on top.

## Adversary model

- **Capabilities.** A radio-range attacker that can eavesdrop, inject, replay,
  jam, and spoof V2X messages, and may attempt to influence the context inputs
  the risk engine observes. May also present cloned/forged node identities.
- **Goals.** Break confidentiality, forge or replay safety messages, deny
  service, or **downgrade** the security level so that safety-critical traffic
  is served with weak protection.
- **Out of scope.** Compromise of the certificate authority, physical
  extraction of the PUF secret, and side-channel attacks on the host CPU.

## Security goals

Confidentiality · Integrity · Authenticity · Availability · Freshness (replay
resistance) · Forward/backward key secrecy · Downgrade resistance · Auditability.

## Attack → defence matrix

| # | Attack (STRIDE) | Effect if unmitigated | SADE-IoV defence | Where in code |
|---|-----------------|-----------------------|------------------|---------------|
| A1 | **Eavesdropping** (Information disclosure) | Telemetry/location leaks | AES-GCM on every payload; AES-256 + short key lifetime for sensitive classes | `crypto_exec.py` |
| A2 | **Message injection / Sybil flooding** (Spoofing/Tampering) | Fake beacons, congestion | Packet-rate feature `α_freq` raises `S_risk` → escalation to High; authenticated encryption rejects forgeries | `data_generator.py`, `decision_logic.py` |
| A3 | **RF jamming** (Denial of service) | Signal loss, missed safety msgs | RSSI feature detects the drop → escalation; verified attack triggers channel isolation (State 3) | `decision_logic.py`, `crypto_exec.py` |
| A4 | **Telemetry / ECU spoofing** (Spoofing) | Falsified position/speed | Velocity-variance feature `V_var` + **PUF challenge** in State 2 confirm physical node authenticity | `crypto_exec.py` (`MockPUF`) |
| A5 | **Replay** (Tampering) | Old messages re-accepted | Per-session **hash-ratchet** key chain + rotation counter bind messages to a key epoch | `crypto_exec.py` (`HashRatchet`) |
| A6 | **Key compromise** | Past/future traffic exposed | One-way KDF chain gives **forward & backward secrecy**; interval shortens under threat | `crypto_exec.py` |
| A7 | **Downgrade attack** (Elevation via context manipulation) | Safety traffic forced into weak cipher | **Fail-secure fusion**: safety floor (`D_class=2`) and user policy can only *raise* the state; most-severe rule checked first | `decision_logic.py` |
| A8 | **Repudiation** | No forensic trail | Asynchronous consortium-ledger writes create an immutable, off-critical-path record of high-risk events | `crypto_exec.py` (`AsyncLedger`) |

## Downgrade resistance (worked example)

An adversary manipulates context toward "benign" to force a low security state
on a braking command (`D_class = 2`). Because `execute_security_orchestration`
evaluates the most-severe rule first and the safety floor holds
(`D_class == 2 and S_risk > 50 → State 2`), the command is still served at
AES-256 + PUF. Manipulating the risk score downward **cannot** defeat the
sensitivity floor. This invariant is pinned by
`tests/test_decision_logic.py::test_safety_floor_overrides_benign_risk` and the
monotonicity test.

## Residual risks / limitations

- The risk engine's quality bounds detection; a crafted **adversarial input**
  could try to bias the score. The fail-secure floors limit the damage
  (safety traffic cannot be downgraded), but adversarial-robustness hardening is
  future work.
- Absolute latency/energy figures are software estimates, not measurements on
  certified OBUs; relative comparisons between states and strategies are the
  informative results.
