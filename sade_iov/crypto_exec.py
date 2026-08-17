"""Layer 3 - Adaptive Security Execution (Section 4.6 / 5.6).

Given the orchestration command ``Omega_t`` from the decision logic, this layer
reconfigures the active cryptographic primitives across the four states and
measures realistic execution times using real PyCryptodome ciphers:

  * STATE_0_LOW      : AES-128-GCM, minimum latency.
  * STATE_1_MEDIUM   : AES-256-GCM + dynamic key rotation (hash ratchet).
  * STATE_2_HIGH     : AES-256-GCM + PUF challenge + async ledger log.
  * STATE_3_CRITICAL : channel isolation + ECU containment + driver alarm
                       (no payload is transmitted).

The total per-message cost is ``T_total = T_infer + T_crypto + T_aux`` where
``T_aux`` covers the on-path portion of PUF and (asynchronous) logging - the
ledger write is queued to an edge/RSU worker and committed off the critical
path, never gating the safety message (Section 4.6.2).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import queue
import threading
import time
from dataclasses import dataclass

from Crypto.Cipher import AES

from . import config


# ---------------------------------------------------------------------------
# Dynamic key rotation: one-way hash ratchet (Section 4.6.1)
#   K_k = KDF(K_{k-1}, salt_k)   -> forward & backward secrecy.
# ---------------------------------------------------------------------------
class HashRatchet:
    """One-way key-derivation chain seeded from a session secret.

    Each call to :meth:`next_key` advances the ratchet by one step using
    HKDF-Expand-style HMAC-SHA256, so a compromised key reveals neither past
    nor future keys. ``counter`` is the rotation index carried in the header.
    """

    def __init__(self, session_secret: bytes | None = None, key_len: int = 32):
        self._key = session_secret or os.urandom(32)
        self.key_len = key_len
        self.counter = 0

    def next_key(self) -> bytes:
        salt = self.counter.to_bytes(8, "big")
        derived = hmac.new(self._key, salt + b"sade-iov-ratchet", hashlib.sha256).digest()
        # Ratchet the chaining key forward (one-way).
        self._key = hashlib.sha256(self._key + derived).digest()
        self.counter += 1
        return derived[: self.key_len]


# Adaptive rotation interval: longer when calm, shorter when elevated.
ROTATION_INTERVAL = {
    config.STATE_0_LOW: 1_000_000,   # effectively static (rotation disabled)
    config.STATE_1_MEDIUM: 64,       # rotate every 64 messages
    config.STATE_2_HIGH: 8,          # rotate aggressively under threat
    config.STATE_3_CRITICAL: 1,
}


# ---------------------------------------------------------------------------
# Mock Physical Unclonable Function (Section 4.6, State 2)
# ---------------------------------------------------------------------------
class MockPUF:
    """Simulated PUF challenge-response.

    A real PUF derives a response from intrinsic silicon variation; here we
    emulate it with a keyed hash over a device secret plus a tiny, fixed
    settling delay to keep the measured on-path cost realistic.
    """

    _SETTLE_SECONDS = 0.00005  # ~50 microseconds challenge settling time

    def __init__(self, device_secret: bytes | None = None):
        self._secret = device_secret or os.urandom(16)

    def challenge_response(self, challenge: bytes) -> bytes:
        time.sleep(self._SETTLE_SECONDS)
        return hmac.new(self._secret, challenge, hashlib.sha256).digest()


# ---------------------------------------------------------------------------
# Asynchronous consortium-ledger logger (Section 4.6.2)
# ---------------------------------------------------------------------------
class AsyncLedger:
    """Queues immutable provenance records and commits them off the critical path.

    On the safety-message path we only *enqueue* (microsecond cost); a worker
    thread on the edge/RSU layer drains the queue and "commits" each record by
    chaining its hash to the previous one (a minimal append-only ledger).
    """

    def __init__(self):
        self._q: queue.Queue[dict] = queue.Queue()
        self._chain: list[dict] = []
        self._prev_hash = b"\x00" * 32
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def enqueue(self, record: dict) -> None:
        self._q.put(record)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                record = self._q.get(timeout=0.1)
            except queue.Empty:
                continue
            payload = repr(sorted(record.items())).encode()
            block_hash = hashlib.sha256(self._prev_hash + payload).digest()
            with self._lock:
                self._chain.append({"record": record, "hash": block_hash.hex()})
                self._prev_hash = block_hash
            self._q.task_done()

    def committed_count(self) -> int:
        with self._lock:
            return len(self._chain)

    def flush(self, timeout: float = 2.0) -> None:
        self._q.join()

    def stop(self) -> None:
        self._stop.set()
        self._worker.join(timeout=1.0)


# ---------------------------------------------------------------------------
# Execution result
# ---------------------------------------------------------------------------
@dataclass
class ExecutionResult:
    state: int
    transmitted: bool
    t_crypto: float = 0.0      # seconds, on-path cryptographic cost
    t_aux: float = 0.0         # seconds, on-path PUF + enqueue cost
    key_bits: int = 0
    rotated: bool = False
    puf_used: bool = False
    ledger_logged: bool = False
    note: str = ""

    @property
    def t_onpath(self) -> float:
        return self.t_crypto + self.t_aux


# ---------------------------------------------------------------------------
# The adaptive execution engine
# ---------------------------------------------------------------------------
class SecurityExecutor:
    """Applies the cryptographic configuration for a given security state."""

    def __init__(self, ledger: AsyncLedger | None = None):
        self.ratchet256 = HashRatchet(key_len=32)
        self.static_key_128 = os.urandom(16)
        self.static_key_256 = os.urandom(32)
        self.puf = MockPUF()
        self.ledger = ledger if ledger is not None else AsyncLedger()
        self._own_ledger = ledger is None
        self._msg_count = {s: 0 for s in config.STATE_NAMES}

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _aes_gcm_encrypt(key: bytes, plaintext: bytes) -> tuple[bytes, bytes, bytes]:
        cipher = AES.new(key, AES.MODE_GCM)
        ct, tag = cipher.encrypt_and_digest(plaintext)
        return cipher.nonce, ct, tag

    def _maybe_rotate(self, state: int) -> tuple[bytes, bool]:
        """Return the AES-256 key for this message, rotating per interval."""
        self._msg_count[state] += 1
        interval = ROTATION_INTERVAL[state]
        if interval <= 1 or (self._msg_count[state] % interval == 0):
            return self.ratchet256.next_key(), True
        return self.static_key_256, False

    # -- main entry point ----------------------------------------------------
    def execute(self, state: int, payload: bytes, epoch: int = 0) -> ExecutionResult:
        """Encrypt/handle ``payload`` according to ``state`` and time it."""
        if state == config.STATE_3_CRITICAL:
            # No transmission: isolate channel + raise alarm. Still audited.
            self.ledger.enqueue({"epoch": epoch, "event": "CRITICAL_ISOLATION"})
            return ExecutionResult(
                state=state, transmitted=False, ledger_logged=True,
                note="channel isolated, ECU contained, driver alarm raised",
            )

        if state == config.STATE_0_LOW:
            t0 = time.perf_counter()
            self._aes_gcm_encrypt(self.static_key_128, payload)
            t_crypto = time.perf_counter() - t0
            return ExecutionResult(state=state, transmitted=True,
                                   t_crypto=t_crypto, key_bits=128)

        # STATE_1_MEDIUM or STATE_2_HIGH -> AES-256 (+ rotation).
        key, rotated = self._maybe_rotate(state)
        t0 = time.perf_counter()
        self._aes_gcm_encrypt(key, payload)
        t_crypto = time.perf_counter() - t0

        t_aux = 0.0
        puf_used = False
        ledger_logged = False
        if state == config.STATE_2_HIGH:
            a0 = time.perf_counter()
            self.puf.challenge_response(os.urandom(16))     # on-path PUF
            puf_used = True
            self.ledger.enqueue({                            # off-path: enqueue only
                "epoch": epoch, "event": "HIGH_STATE_TX", "rotated": rotated,
            })
            ledger_logged = True
            t_aux = time.perf_counter() - a0

        return ExecutionResult(
            state=state, transmitted=True, t_crypto=t_crypto, t_aux=t_aux,
            key_bits=256, rotated=rotated, puf_used=puf_used,
            ledger_logged=ledger_logged,
        )

    def close(self) -> None:
        if self._own_ledger:
            self.ledger.flush()
            self.ledger.stop()
