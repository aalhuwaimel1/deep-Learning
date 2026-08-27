"""الأبحاث — حيث يقرأ ما يكتبه الباحثون، بلغاتهم هم.

أربعة مصادر مفتوحة، بلا مفاتيح ولا اشتراكات:

  OpenAlex   ٢٥٠+ مليون بحث من كل التخصّصات، ويرشّح **بلغة البحث** مباشرة
             (filter=language:ja) — وهذا بالضبط ما يجعل «أبحاث مختلفة
             اللغة» ممكنة بدل أن تكون أمنية.
  Crossref   ١٥٠+ مليون DOI مسجّل، مرجع الناشرين.
  arXiv      المسوّدات قبل النشر: فيزياء، رياضيات، حاسوب.
  DOAJ       دليل المجلات مفتوحة الوصول — أغنى المصادر بالإسبانية
             والبرتغالية والإندونيسية والفارسية، لغاتٌ يهملها غيره.

الاثنان الأولان يطلبان بريداً للتعريف مقابل خدمة أسرع وأثبت («الطابور
المهذّب»). نرسله إن وضعته في ROOH_CONTACT، ولا نخترع بريداً إن لم تضعه.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

from .net import FetchError, Fetcher

OPENALEX = "https://api.openalex.org/works"
CROSSREF = "https://api.crossref.org/works"
ARXIV = "http://export.arxiv.org/api/query"
DOAJ = "https://doaj.org/api/search/articles"

PROVIDERS = ("openalex", "crossref", "arxiv", "doaj")


@dataclass
class Paper:
    title: str
    abstract: str = ""
    lang: str = ""
    year: Optional[int] = None
    authors: list[str] = field(default_factory=list)
    doi: str = ""
    url: str = ""
    venue: str = ""
    provider: str = ""
    cited_by: int = 0

    def scholarly_text(self) -> str:
        """العنوان والملخّص وحدهما — ما يُستخلص منه المعنى.

        نفصله عن as_text عمداً: تلك تضيف تسميات عربية («الباحثون:»،
        «المنشور في:») للعرض، ولو هضمناها لتسلّلت هذه التسميات إلى
        خريطة فضوله فصار «المنشور» و«السنة» من أكثر ما يشغله.
        """
        return f"{self.title}\n\n{self.abstract}".strip()

    def as_text(self) -> str:
        """نصّ البحث كما يُخزَّن في الجسد — بالبيانات الوصفية للعرض."""
        head = [self.title]
        if self.authors:
            head.append("الباحثون: " + "، ".join(self.authors[:6]))
        if self.venue:
            head.append(f"المنشور في: {self.venue}")
        if self.year:
            head.append(f"السنة: {self.year}")
        if self.doi:
            head.append(f"DOI: {self.doi}")
        return "\n".join(head) + "\n\n" + self.abstract


def contact() -> str:
    """بريد التعريف للطابور المهذّب. فارغ إن لم يضعه صاحب الجهاز."""
    return os.environ.get("ROOH_CONTACT", "").strip()


# ── OpenAlex ─────────────────────────────────────────────────────────────
def _deinvert(index: Optional[dict]) -> str:
    """OpenAlex يخزّن الملخّص مقلوباً: {كلمة: [مواضعها]}. نعيد بناء النص.

    السبب أن الناشرين يمنعون إعادة نشر الملخّص كنصّ متّصل، لا يمنعون
    الفهرس. إعادة الترتيب عمل حسابي بحت: نضع كل كلمة في موضعها.
    """
    if not index:
        return ""
    slots: list[tuple[int, str]] = []
    for word, positions in index.items():
        for pos in positions:
            slots.append((pos, word))
    slots.sort()
    return " ".join(w for _, w in slots)


def openalex_search(f: Fetcher, query: str, lang: str = "",
                    limit: int = 5) -> list[Paper]:
    params: dict[str, str] = {"search": query, "per-page": str(min(limit, 50))}
    if lang:
        params["filter"] = f"language:{lang}"
    if contact():
        params["mailto"] = contact()
    try:
        data = f.get_json(f"{OPENALEX}?{urllib.parse.urlencode(params)}")
    except (FetchError, json.JSONDecodeError):
        return []

    out: list[Paper] = []
    for w in (data.get("results") or [])[:limit]:
        loc = w.get("primary_location") or {}
        src = loc.get("source") or {}
        oa = w.get("open_access") or {}
        url = oa.get("oa_url") or loc.get("landing_page_url") or w.get("id", "")
        out.append(Paper(
            title=w.get("display_name") or w.get("title") or "",
            abstract=_deinvert(w.get("abstract_inverted_index")),
            lang=w.get("language") or lang,
            year=w.get("publication_year"),
            authors=[a.get("author", {}).get("display_name", "")
                     for a in (w.get("authorships") or [])[:8]],
            doi=(w.get("doi") or "").replace("https://doi.org/", ""),
            url=url, venue=src.get("display_name", "") or "",
            provider="openalex", cited_by=w.get("cited_by_count") or 0,
        ))
    return [p for p in out if p.title]


# ── Crossref ─────────────────────────────────────────────────────────────
_JATS = re.compile(r"<[^>]+>")


def crossref_search(f: Fetcher, query: str, lang: str = "",
                    limit: int = 5) -> list[Paper]:
    params = {"query": query, "rows": str(min(limit, 20))}
    if contact():
        params["mailto"] = contact()
    try:
        data = f.get_json(f"{CROSSREF}?{urllib.parse.urlencode(params)}")
    except (FetchError, json.JSONDecodeError):
        return []

    out: list[Paper] = []
    for it in ((data.get("message") or {}).get("items") or [])[:limit]:
        titles = it.get("title") or []
        if not titles or not titles[0]:
            continue
        year = None
        parts = (it.get("issued") or {}).get("date-parts") or [[]]
        if parts and parts[0]:
            year = parts[0][0]
        # الملخّص يأتي أحياناً بوسوم JATS — ننزعها
        abstract = _JATS.sub(" ", it.get("abstract") or "").strip()
        out.append(Paper(
            title=titles[0], abstract=re.sub(r"\s+", " ", abstract),
            lang=it.get("language") or lang, year=year,
            authors=[f"{a.get('given','')} {a.get('family','')}".strip()
                     for a in (it.get("author") or [])[:8]],
            doi=it.get("DOI", ""), url=it.get("URL", ""),
            venue=(it.get("container-title") or [""])[0],
            provider="crossref", cited_by=it.get("is-referenced-by-count") or 0,
        ))
    return out


# ── arXiv ────────────────────────────────────────────────────────────────
def arxiv_search(f: Fetcher, query: str, lang: str = "",
                 limit: int = 5) -> list[Paper]:
    params = {"search_query": f"all:{query}", "max_results": str(min(limit, 20)),
              "sortBy": "submittedDate", "sortOrder": "descending"}
    try:
        resp = f.get(f"{ARXIV}?{urllib.parse.urlencode(params)}",
                     accept="application/atom+xml,application/xml,*/*")
        root = ET.fromstring(resp.text().strip())
    except (FetchError, ET.ParseError):
        return []

    ns = "{http://www.w3.org/2005/Atom}"
    out: list[Paper] = []
    for entry in root.findall(f"{ns}entry")[:limit]:
        title = (entry.findtext(f"{ns}title") or "").strip()
        if not title:
            continue
        published = (entry.findtext(f"{ns}published") or "")[:4]
        out.append(Paper(
            title=re.sub(r"\s+", " ", title),
            abstract=re.sub(r"\s+", " ", (entry.findtext(f"{ns}summary") or "").strip()),
            lang="en", year=int(published) if published.isdigit() else None,
            authors=[(a.findtext(f"{ns}name") or "").strip()
                     for a in entry.findall(f"{ns}author")[:8]],
            url=(entry.findtext(f"{ns}id") or ""), venue="arXiv",
            provider="arxiv",
        ))
    return out


# ── DOAJ ─────────────────────────────────────────────────────────────────
def doaj_search(f: Fetcher, query: str, lang: str = "",
                limit: int = 5) -> list[Paper]:
    q = urllib.parse.quote(query, safe="")
    url = f"{DOAJ}/{q}?pageSize={min(limit, 20)}"
    try:
        data = f.get_json(url)
    except (FetchError, json.JSONDecodeError):
        return []

    out: list[Paper] = []
    for it in (data.get("results") or [])[:limit]:
        bj = it.get("bibjson") or {}
        title = bj.get("title") or ""
        if not title:
            continue
        links = [l.get("url", "") for l in (bj.get("link") or []) if l.get("url")]
        ident = {i.get("type"): i.get("id") for i in (bj.get("identifier") or [])}
        out.append(Paper(
            title=re.sub(r"\s+", " ", title),
            abstract=re.sub(r"\s+", " ", bj.get("abstract") or ""),
            lang=(bj.get("journal") or {}).get("language", [lang])[0] if
                 (bj.get("journal") or {}).get("language") else lang,
            year=int(bj["year"]) if str(bj.get("year", "")).isdigit() else None,
            authors=[a.get("name", "") for a in (bj.get("author") or [])[:8]],
            doi=ident.get("doi", ""), url=links[0] if links else "",
            venue=(bj.get("journal") or {}).get("title", ""),
            provider="doaj",
        ))
    return out


_SEARCHERS = {
    "openalex": openalex_search,
    "crossref": crossref_search,
    "arxiv": arxiv_search,
    "doaj": doaj_search,
}


def search_papers(f: Fetcher, query: str, lang: str = "", limit: int = 5,
                  providers: tuple[str, ...] = PROVIDERS) -> list[Paper]:
    """يسأل المصادر بالترتيب حتى يجد. يتخطّى المصدر الميّت ولا يتوقّف عنده.

    الترتيب مقصود: OpenAlex أولاً لأنه وحده يرشّح بلغة البحث؛ إن لم يجد
    بتلك اللغة ننزل إلى البقيّة بلا ترشيح لغوي.
    """
    seen_titles: set[str] = set()
    found: list[Paper] = []
    for name in providers:
        fn = _SEARCHERS.get(name)
        if not fn:
            continue
        for paper in fn(f, query, lang, limit):
            key = paper.title.lower()[:80]
            if key in seen_titles:
                continue
            seen_titles.add(key)
            found.append(paper)
        if len(found) >= limit:
            break
    return found[:limit]
