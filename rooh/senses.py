"""الحواسّ — كيف تقرأ الروح صفحة HTML وتخرج منها بالنص وحده.

نستعمل HTMLParser من المكتبة القياسية حتى لا يعتمد الكائن على أي حزمة
خارجية. إن كانت beautifulsoup4 مثبّتة نستعملها لأنها أدقّ.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urljoin, urlparse

try:                                   # اختياري
    from bs4 import BeautifulSoup      # type: ignore
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False

_SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "nav", "footer",
              "header", "aside", "form", "iframe"}
_BLOCK_TAGS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
               "section", "article", "blockquote", "td"}

#: كم حرفاً صينياً/يابانياً يعادل الحرف اللاتيني في كثافة المعنى (انظر
#: looks_substantial). ليست رقماً اعتباطياً: مشتقّة من متوسّط طول الكلمة.
CJK_DENSITY = 0.28


class _Reader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title: str = ""
        self.lang: str = ""
        self.links: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        d = dict(attrs)
        if tag == "html" and d.get("lang"):
            self.lang = (d["lang"] or "").split("-")[0].lower()
        if tag == "title":
            self._in_title = True
        if tag == "a" and d.get("href"):
            self.links.append(d["href"] or "")
        if tag == "meta":
            # <meta property="og:title"> بديل جيد حين يكون <title> رديئاً
            if d.get("property") in ("og:title",) and d.get("content") and not self.title:
                self.title = d["content"] or ""
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title = (self.title + data).strip()
            return
        if self._skip_depth == 0 and data.strip():
            self.parts.append(data)


def _clean(text: str) -> str:
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    lines = [ln.strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def extract(html: str, base_url: str = "") -> dict:
    """يعيد {title, text, lang, links} من صفحة HTML."""
    if _HAS_BS4:
        return _extract_bs4(html, base_url)
    r = _Reader()
    try:
        r.feed(html)
    except Exception:
        pass                       # HTML مكسور: نأخذ ما جمعناه حتى الآن
    links = _absolutize(r.links, base_url)
    return {"title": r.title.strip(), "text": _clean("".join(r.parts)),
            "lang": r.lang, "links": links}


def _extract_bs4(html: str, base_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(list(_SKIP_TAGS)):
        tag.decompose()
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            title = og["content"].strip()
    html_tag = soup.find("html")
    lang = ""
    if html_tag and html_tag.get("lang"):
        lang = html_tag["lang"].split("-")[0].lower()
    links = _absolutize(
        [a.get("href", "") for a in soup.find_all("a", href=True)], base_url
    )
    return {"title": title, "text": _clean(soup.get_text("\n")), "lang": lang,
            "links": links}


def _absolutize(hrefs: list[str], base_url: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for h in hrefs:
        if not h or h.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        full = urljoin(base_url, h) if base_url else h
        if urlparse(full).scheme not in ("http", "https"):
            continue
        if full not in seen:
            seen.add(full)
            out.append(full)
    return out


def looks_substantial(text: str, min_chars: int = 400) -> bool:
    """هل الصفحة تستحق التذكّر، أم أنها قائمة روابط؟

    العتبة تُقاس بالحروف، والحروف ليست متساوية القيمة. لو طبّقنا نفس الرقم
    على الكتابتين لرمينا كل مقال صيني جادّ بحجّة أنه «قصير».

    حساب النسبة: ٤٠٠ حرف لاتيني ≈ ٧٢ كلمة (بمتوسّط ٥٫٥ حرف للكلمة مع
    الفراغ)، والكلمة الصينية أو اليابانية ≈ ١٫٥ حرف، أي ما يقارب ١١٠
    حرفاً لنفس القدر من المعنى — نسبة ٠٫٢٨.
    """
    from .lang import script_of

    if not text:
        return False
    threshold = min_chars * CJK_DENSITY if script_of(text) == "cjk" else min_chars
    return len(text) >= threshold
