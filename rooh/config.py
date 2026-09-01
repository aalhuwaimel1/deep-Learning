"""مسارات وإعدادات عامة. كل شيء يعيش داخل «الجسد» على جهازك."""

from __future__ import annotations

import os
from pathlib import Path

#: جذر الجسد. يمكن تغييره عبر متغيّر البيئة ROOH_HOME.
DEFAULT_HOME = Path.home() / ".rooh"


def home() -> Path:
    """المجلد الذي يسكنه هذا الكائن على جهازك."""
    return Path(os.environ.get("ROOH_HOME", DEFAULT_HOME)).expanduser()


def db_path() -> Path:
    return home() / "body.db"


def personality_path() -> Path:
    return home() / "personality.json"


def sources_path() -> Path:
    return home() / "sources.json"


def journal_dir() -> Path:
    return home() / "journal"


def snapshots_path() -> Path:
    """سجلّ القياس: سطر JSON واحد لكل يوم. هذا هو ما يُحلَّل، لا قاعدة البيانات."""
    return home() / "snapshots.jsonl"


def ensure_home() -> Path:
    h = home()
    h.mkdir(parents=True, exist_ok=True)
    journal_dir().mkdir(parents=True, exist_ok=True)
    return h


# ── سلوك التجوّل ──────────────────────────────────────────────────────────
USER_AGENT = (
    "rooh/0.1 (personal knowledge wanderer; +https://github.com/aalhuwaimel1/deep-Learning)"
)
REQUEST_TIMEOUT = 25          # ثانية لكل طلب
DELAY_PER_HOST = 2.0          # أدنى فاصل بين طلبين لنفس المضيف (تأدّب)
MAX_PAGE_BYTES = 2_000_000    # لا نبتلع صفحات ضخمة
MAX_TEXT_CHARS = 40_000       # ما نخزّنه من نص كل صفحة
