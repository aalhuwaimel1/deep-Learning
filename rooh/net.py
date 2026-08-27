"""الشبكة — كيف تخرج الروح، وكيف تتأدّب وهي خارج البيت.

ثلاث قواعد نلتزم بها لأن الكائن يمشي باسمك:
  1. نعرّف عن أنفسنا بـ User-Agent صادق.
  2. نسأل robots.txt قبل أن ندخل.
  3. لا نطرق باب مضيف واحد أسرع من مرّة كل ثانيتين.
"""

from __future__ import annotations

import gzip
import ssl
import time
import urllib.error
import urllib.request
import urllib.robotparser
import zlib
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from . import config


class FetchError(Exception):
    """فشل جلب صفحة — سبب متوقّع، لا يوقف الرحلة."""


@dataclass
class Response:
    url: str
    status: int
    body: bytes
    content_type: str
    charset: Optional[str]

    def text(self) -> str:
        for enc in (self.charset, "utf-8", "gb18030", "shift_jis", "euc-kr", "cp1251"):
            if not enc:
                continue
            try:
                return self.body.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return self.body.decode("utf-8", errors="replace")


class Fetcher:
    """جالب صفحات مهذّب: يحترم robots، ويباعد بين طلباته."""

    def __init__(
        self,
        *,
        user_agent: str = config.USER_AGENT,
        timeout: int = config.REQUEST_TIMEOUT,
        delay: float = config.DELAY_PER_HOST,
        respect_robots: bool = True,
        max_bytes: int = config.MAX_PAGE_BYTES,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.delay = delay
        self.respect_robots = respect_robots
        self.max_bytes = max_bytes
        self._last_hit: dict[str, float] = {}
        self._robots: dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}
        # يحترم HTTPS_PROXY وشهادات النظام تلقائياً
        self._ssl = ssl.create_default_context()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=self._ssl),
            urllib.request.ProxyHandler(),  # يقرأ متغيّرات البيئة
        )

    # ── تأدّب ────────────────────────────────────────────────────────────
    def _wait_turn(self, host: str) -> None:
        last = self._last_hit.get(host)
        if last is not None:
            gap = time.monotonic() - last
            if gap < self.delay:
                time.sleep(self.delay - gap)
        self._last_hit[host] = time.monotonic()

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parts = urlparse(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            self._robots[origin] = self._load_robots(origin)
        rp = self._robots[origin]
        if rp is None:      # لا robots.txt أو تعذّر قراءته ⇒ نفترض السماح
            return True
        return rp.can_fetch(self.user_agent, url)

    def _load_robots(self, origin: str) -> Optional[urllib.robotparser.RobotFileParser]:
        rp = urllib.robotparser.RobotFileParser()
        try:
            req = urllib.request.Request(
                f"{origin}/robots.txt", headers={"User-Agent": self.user_agent}
            )
            with self._opener.open(req, timeout=min(self.timeout, 10)) as r:
                rp.parse(r.read(200_000).decode("utf-8", errors="replace").splitlines())
            return rp
        except Exception:
            return None

    # ── الجلب ────────────────────────────────────────────────────────────
    def get(self, url: str, *, accept: str = "text/html,application/xhtml+xml,*/*") -> Response:
        parts = urlparse(url)
        if parts.scheme not in ("http", "https"):
            raise FetchError(f"مخطّط غير مدعوم: {parts.scheme}")
        if not self.allowed(url):
            raise FetchError("robots.txt يمنع هذا المسار")

        self._wait_turn(parts.netloc)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": accept,
                "Accept-Encoding": "gzip, deflate",
                # نطلب اللغة الأصلية للموقع، لا ترجمة
                "Accept-Language": "*",
            },
        )
        try:
            with self._opener.open(req, timeout=self.timeout) as r:
                raw = r.read(self.max_bytes)
                encoding = (r.headers.get("Content-Encoding") or "").lower()
                if "gzip" in encoding:
                    raw = gzip.decompress(raw)
                elif "deflate" in encoding:
                    raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                ctype = r.headers.get("Content-Type", "")
                charset = r.headers.get_content_charset()
                return Response(r.geturl(), r.status, raw, ctype, charset)
        except urllib.error.HTTPError as e:
            raise FetchError(f"HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise FetchError(f"تعذّر الوصول: {e.reason}") from e
        except (gzip.BadGzipFile, zlib.error) as e:
            raise FetchError(f"ضغط تالف: {e}") from e
        except Exception as e:                       # مهلة، TLS، إلخ
            raise FetchError(f"{type(e).__name__}: {e}") from e

    def get_json(self, url: str) -> dict:
        import json

        resp = self.get(url, accept="application/json")
        return json.loads(resp.text())
