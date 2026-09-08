"""التوصيل — كيف يصلك ما عاد به، بلا أن تسأل.

قناتان بترتيب:
  تلغرام : يصلك على جوالك. لا يحتاج خادماً ولا SMTP ولا يقع في «المهملات».
  ملفّ   : دائماً، حتى لو نجح تلغرام. نسخةٌ على قرصك لا تعتمد على أحد.

الملفّ ليس احتياطياً فقط: هو السجلّ. إن غبتَ أسبوعين وعُدت، تجد كل رسالةٍ
أُرسلت — وكل واحدةٍ أخفقت — مكتوبةً عندك.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from . import config

TELEGRAM_API = "https://api.telegram.org"
#: تلغرام يرفض ما زاد على ٤٠٩٦ محرفاً، فنقسّم عند حدود الأسطر.
CHUNK = 3800


def outbox() -> Path:
    return config.home() / "outbox"


def _credentials() -> tuple[Optional[str], Optional[str]]:
    import os

    return (os.environ.get("ROOH_TELEGRAM_TOKEN", "").strip() or None,
            os.environ.get("ROOH_TELEGRAM_CHAT", "").strip() or None)


def configured() -> bool:
    token, chat = _credentials()
    return bool(token and chat)


def _split(text: str) -> list[str]:
    """يقسّم عند الأسطر لا عند المحارف، حتى لا تُبتر جملةٌ في المنتصف."""
    if len(text) <= CHUNK:
        return [text]
    parts, current = [], ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > CHUNK and current:
            parts.append(current)
            current = ""
        # سطرٌ وحده أطول من الحدّ: نقطعه اضطراراً
        while len(line) > CHUNK:
            parts.append(line[:CHUNK])
            line = line[CHUNK:]
        current += line
    if current:
        parts.append(current)
    return parts


def _telegram(text: str, timeout: int = 20) -> tuple[bool, str]:
    token, chat = _credentials()
    if not (token and chat):
        return False, "تلغرام غير مُهيّأ"
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    for i, part in enumerate(_split(text)):
        data = urllib.parse.urlencode({
            "chat_id": chat, "text": part, "disable_web_page_preview": "true",
        }).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = json.loads(r.read().decode("utf-8"))
                if not body.get("ok"):
                    return False, f"تلغرام رفض: {body.get('description','?')}"
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read().decode()).get("description", "")
            except Exception:
                pass
            return False, f"HTTP {e.code} {detail}".strip()
        except Exception as e:                 # شبكةٌ مقطوعة أو مهلة
            return False, f"{type(e).__name__}: {e}"
        if i:
            time.sleep(0.4)                    # تأدّبٌ مع حدود المعدّل
    return True, "أُرسلت"


def send(text: str, subject: str = "") -> dict:
    """يوصّل الرسالة. يكتب نسخةً على القرص دائماً، ثم يحاول تلغرام.

    لا يرفع استثناءً أبداً: هذا يُستدعى من حلقةٍ تعمل بلا مراقبة، وسقوطها
    لأجل إشعارٍ فاشل خسارةٌ لا معنى لها.
    """
    stamp = time.strftime("%Y-%m-%d_%H%M%S", time.localtime())
    result = {"at": time.time(), "file": None, "telegram": None, "error": None}
    body = (f"{subject}\n\n{text}" if subject else text)

    try:
        d = outbox()
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{stamp}.txt"
        path.write_text(body, encoding="utf-8")
        result["file"] = str(path)
    except Exception as e:
        result["error"] = f"تعذّرت الكتابة: {e}"

    if configured():
        ok, why = _telegram(body)
        result["telegram"] = "أُرسلت" if ok else f"أخفقت — {why}"
        if not ok and not result["error"]:
            result["error"] = why
    else:
        result["telegram"] = "غير مُهيّأ"
    return result


SETUP = """لتصلك رسائله على تلغرام:

  ١. افتح تلغرام وكلّم @BotFather، أرسل /newbot واتبع الخطوات.
     ستحصل على رمزٍ مثل: 123456789:AAH...

  ٢. كلّم بوتك الجديد برسالةٍ أي شيء (لن يردّ عليك، هذا طبيعي).

  ٣. افتح هذا في المتصفّح، واستبدل الرمز:
     https://api.telegram.org/bot<الرمز>/getUpdates
     ابحث عن "chat":{"id":123456789 — ذلك رقم محادثتك.

  ٤. ضعهما في بيئتك (وفي crontab إن جدولته):

     export ROOH_TELEGRAM_TOKEN='123456789:AAH...'
     export ROOH_TELEGRAM_CHAT='123456789'

  ٥. تحقّق:  rooh notify --test

وإن لم تفعل شيئاً من هذا فلا بأس: كل رسالةٍ تُكتب في ~/.rooh/outbox/
سواء أُرسلت أو لا."""
