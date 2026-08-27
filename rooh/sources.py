"""المصادر — إلى أين تذهب الروح، وبأي لسان تسأل هناك.

العمود الفقري هو واجهة ويكيبيديا/ويكي‌الأخبار، لأنها تعمل بنفس الشكل في
كل اللغات (zh, ja, ru, ar, ko, fa, ...) ولا تتعطّل. وفوقها خلاصات RSS
وطنية يستطيع صاحب الجهاز أن يضيف ويحذف منها كما يشاء.

المسألة الدقيقة هنا: اهتماماتك مكتوبة بالعربية. البحث عن «الذكاء
الاصطناعي» في ويكيبيديا الصينية يعود بلا شيء. لذلك تتعلّم الروح كيف
يُقال المصطلح بلسان أهله (عبر روابط اللغات)، وتحفظ ما تعلّمته في الجسد
حتى لا تتعلّمه مرّتين.
"""

from __future__ import annotations

import json
import random
import re
import sqlite3
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

from .net import FetchError, Fetcher

# ── سجلّ المصادر الافتراضي ────────────────────────────────────────────────
# «الجنسيات» التي تعرف الروح كيف تمشي فيها. عدّلها في ~/.rooh/sources.json
DEFAULT_SOURCES: dict = {
    "wiki_langs": ["ar", "en", "zh", "ja", "ru", "ko", "fr", "de", "es", "fa", "tr",
                   "hi", "pt", "it", "pl", "uk", "he", "id", "vi", "th"],
    "wikinews_langs": ["ar", "en", "zh", "ja", "ru", "fr", "de", "es", "pt", "pl",
                       "it", "ko", "cs", "uk", "sr", "ta", "tr"],
    # خلاصات RSS وطنية. الروابط تتغيّر مع الزمن — تحقّق منها بـ: rooh sources --check
    "feeds": {
        "zh": [
            {"name": "中国新闻网", "url": "https://www.chinanews.com.cn/rss/scroll-news.xml"},
            {"name": "cnBeta 科技", "url": "https://rss.cnbeta.com.tw/rss"},
        ],
        "ja": [
            {"name": "NHK 主要ニュース", "url": "https://www.nhk.or.jp/rss/news/cat0.xml"},
            {"name": "ITmedia NEWS", "url": "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml"},
        ],
        "ru": [
            {"name": "Лента.ру", "url": "https://lenta.ru/rss/news"},
            {"name": "Хабр", "url": "https://habr.com/ru/rss/articles/"},
        ],
        "ar": [
            {"name": "الجزيرة", "url": "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4bd4-9d80-a84db769f779/73d0e1b4-532f-45ef-b135-bfdff8b8cab9"},
            {"name": "BBC عربي", "url": "https://feeds.bbci.co.uk/arabic/rss.xml"},
        ],
        "en": [
            {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
            {"name": "Hacker News", "url": "https://hnrss.org/frontpage"},
            {"name": "arXiv cs.AI", "url": "https://rss.arxiv.org/rss/cs.AI"},
        ],
        "ko": [{"name": "한겨레", "url": "https://www.hani.co.kr/rss/"}],
        "de": [{"name": "Tagesschau", "url": "https://www.tagesschau.de/xml/rss2/"}],
        "fr": [{"name": "France Info", "url": "https://www.francetvinfo.fr/titres.rss"}],
        "es": [{"name": "El País", "url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada"}],
        "fa": [{"name": "BBC فارسی", "url": "https://feeds.bbci.co.uk/persian/rss.xml"}],
        "tr": [{"name": "BBC Türkçe", "url": "https://feeds.bbci.co.uk/turkce/rss.xml"}],
    },
}


@dataclass
class Destination:
    """محطّة واحدة تنوي الروح زيارتها."""
    url: str
    lang: str
    source: str
    title: str = ""
    kind: str = "page"       # page | wiki | rss_item | paper
    # محتوى جاهز جاء مع نتيجة البحث، فلا نطلب الصفحة مرّة ثانية
    payload: Optional[dict] = None


def load_sources(path) -> dict:
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return json.loads(json.dumps(DEFAULT_SOURCES))
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return json.loads(json.dumps(DEFAULT_SOURCES))
    merged = json.loads(json.dumps(DEFAULT_SOURCES))
    merged.update(data)
    return merged


def save_sources(path, data: dict) -> None:
    from pathlib import Path

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── ويكيبيديا: نفس الواجهة بكل لسان ──────────────────────────────────────
def _api(lang: str, site: str = "wikipedia") -> str:
    return f"https://{lang}.{site}.org/w/api.php"


def wiki_search(f: Fetcher, lang: str, query: str, limit: int = 5,
                site: str = "wikipedia") -> list[str]:
    """يبحث في ويكي تلك اللغة ويعيد عناوين المقالات."""
    params = urllib.parse.urlencode({
        "action": "query", "list": "search", "srsearch": query,
        "srlimit": limit, "format": "json", "formatversion": "2",
    })
    try:
        data = f.get_json(f"{_api(lang, site)}?{params}")
    except (FetchError, json.JSONDecodeError):
        return []
    return [i["title"] for i in ((data.get("query") or {}).get("search") or [])]


def wiki_random(f: Fetcher, lang: str, count: int = 3,
                site: str = "wikipedia") -> list[str]:
    """مقالات عشوائية — هذا ما يجعل التجوّل تجوّلاً لا بحثاً."""
    params = urllib.parse.urlencode({
        "action": "query", "list": "random", "rnnamespace": 0,
        "rnlimit": count, "format": "json", "formatversion": "2",
    })
    try:
        data = f.get_json(f"{_api(lang, site)}?{params}")
    except (FetchError, json.JSONDecodeError):
        return []
    return [i["title"] for i in ((data.get("query") or {}).get("random") or [])]


def wiki_extract(f: Fetcher, lang: str, title: str,
                 site: str = "wikipedia") -> Optional[dict]:
    """نصّ المقال كاملاً بلا HTML، بلغته الأصلية."""
    params = urllib.parse.urlencode({
        "action": "query", "prop": "extracts", "titles": title,
        "explaintext": "1", "exsectionformat": "plain",
        "format": "json", "formatversion": "2",
    })
    try:
        data = f.get_json(f"{_api(lang, site)}?{params}")
    except (FetchError, json.JSONDecodeError):
        return None
    pages = (data.get("query") or {}).get("pages") or []
    if not pages or pages[0].get("missing"):
        return None
    page = pages[0]
    return {
        "title": page.get("title", title),
        "text": page.get("extract", "") or "",
        "url": wiki_url(lang, page.get("title", title), site),
        "lang": lang,
    }


def wiki_url(lang: str, title: str, site: str = "wikipedia") -> str:
    return f"https://{lang}.{site}.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"


# ── المعجم: كيف يُقال اهتمامي بلسانهم ────────────────────────────────────
_LEXICON_SCHEMA = """
CREATE TABLE IF NOT EXISTS lexicon (
    term     TEXT NOT NULL,
    src_lang TEXT NOT NULL,
    dst_lang TEXT NOT NULL,
    dst_term TEXT,
    learned_at REAL NOT NULL,
    PRIMARY KEY (term, src_lang, dst_lang)
);
"""


def ensure_lexicon(conn: sqlite3.Connection) -> None:
    conn.executescript(_LEXICON_SCHEMA)
    conn.commit()


def translate_term(f: Fetcher, conn: sqlite3.Connection, term: str,
                   src_lang: str, dst_lang: str) -> Optional[str]:
    """يترجم مصطلحاً عبر روابط اللغات في ويكيبيديا، ويحفظ الترجمة في الجسد.

    ليست ترجمة آلية: هي المقابل الذي اتّفق عليه محرّرو ويكيبيديا في
    اللغتين. لذلك هي دقيقة للمصطلحات وأسماء الأعلام تحديداً.
    None محفوظة أيضاً — «لا يوجد مقابل» معرفة تستحق الحفظ.
    """
    if src_lang == dst_lang:
        return term
    ensure_lexicon(conn)
    row = conn.execute(
        "SELECT dst_term FROM lexicon WHERE term=? AND src_lang=? AND dst_lang=?",
        (term, src_lang, dst_lang),
    ).fetchone()
    if row is not None:
        return row[0]

    result: Optional[str] = None
    titles = wiki_search(f, src_lang, term, limit=1)
    if titles:
        params = urllib.parse.urlencode({
            "action": "query", "titles": titles[0], "prop": "langlinks",
            "lllang": dst_lang, "format": "json", "formatversion": "2",
        })
        try:
            data = f.get_json(f"{_api(src_lang)}?{params}")
            pages = (data.get("query") or {}).get("pages") or []
            if pages and pages[0].get("langlinks"):
                result = pages[0]["langlinks"][0].get("title")
        except (FetchError, json.JSONDecodeError, KeyError, IndexError):
            result = None

    conn.execute(
        """INSERT OR REPLACE INTO lexicon(term, src_lang, dst_lang, dst_term, learned_at)
           VALUES(?,?,?,?,?)""",
        (term, src_lang, dst_lang, result, time.time()),
    )
    conn.commit()
    return result


# ── RSS / Atom ───────────────────────────────────────────────────────────
def parse_feed(xml_text: str, limit: int = 10) -> list[dict]:
    """يقرأ RSS 2.0 و Atom بنفس الدالة."""
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_text.strip())
    except ET.ParseError:
        return items

    for item in root.iter():
        tag = item.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        title, link = "", ""
        for child in item:
            ctag = child.tag.split("}")[-1]
            if ctag == "title" and child.text:
                title = child.text.strip()
            elif ctag == "link":
                link = (child.get("href") or child.text or "").strip()
        if link:
            items.append({"title": title, "url": link})
        if len(items) >= limit:
            break
    return items


def feed_destinations(f: Fetcher, sources: dict, lang: str,
                      rng: Optional[random.Random] = None,
                      limit: int = 5) -> list[Destination]:
    """يفتح خلاصة وطنية بتلك اللغة ويعيد ما فيها من مقالات."""
    r = rng or random
    feeds = sources.get("feeds", {}).get(lang, [])
    if not feeds:
        return []
    feed = r.choice(feeds)
    try:
        resp = f.get(feed["url"], accept="application/rss+xml,application/xml,text/xml,*/*")
    except FetchError:
        return []
    return [
        Destination(url=it["url"], lang=lang, source=feed.get("name", feed["url"]),
                    title=it["title"], kind="rss_item")
        for it in parse_feed(resp.text(), limit=limit)
    ]
