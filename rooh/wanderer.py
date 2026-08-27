"""الروح — الخروج والعودة.

دورة واحدة كاملة:
    يستيقظ بمزاج ← يقرّر بأي لسان يبدأ ← يترجم فضوله إلى ذلك اللسان
    ← يمشي في مواقع أهله ← يقرأ ← يهضم ← يعود ← يضع كل شيء في الجسد
    ← يكتب يوميّاته ← ينام.

الروح لا تحتفظ بشيء لنفسها. كل ما تعود به يصير جسداً.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import urlparse

from . import config, senses, sources
from .body import Body
from .lang import script_of
from .mind import Mind
from .net import FetchError, Fetcher
from .personality import Personality
from .sources import Destination


@dataclass
class JourneyReport:
    journey_id: int
    mood: str
    visited: int = 0
    stored: int = 0
    failed: int = 0
    langs: list[str] = field(default_factory=list)
    highlights: list[tuple[str, str]] = field(default_factory=list)
    journal: str = ""
    duration: float = 0.0


class Wanderer:
    def __init__(
        self,
        body: Body,
        personality: Personality,
        mind: Mind,
        fetcher: Optional[Fetcher] = None,
        source_map: Optional[dict] = None,
        rng: Optional[random.Random] = None,
        on_event: Optional[Callable[[str, dict], None]] = None,
    ):
        self.body = body
        self.p = personality
        self.mind = mind
        self.rng = rng or random.Random()
        self.sources = source_map or sources.load_sources(config.sources_path())
        self.f = fetcher or Fetcher(respect_robots=self.p.respect_robots)
        self.on_event = on_event or (lambda kind, data: None)
        # مقالات جلبناها من خلاصة ولم نزرها بعد، مفهرسة باللغة
        self._pending: dict[str, list[Destination]] = {}
        self._refills: dict[str, int] = {}      # كم مرّة ملأنا طابور كل لغة
        self._drained: set[str] = set()         # لغات استنفدنا خلاصاتها

    # ── الرحلة ───────────────────────────────────────────────────────────
    def journey(self, pages: Optional[int] = None,
                only_lang: Optional[str] = None) -> JourneyReport:
        budget = pages or self.p.pages_per_journey
        mood = self.p.pick_mood(self.rng)
        seeds = self._current_seeds()
        started = time.monotonic()

        jid = self.body.start_journey(seeds, mood)
        report = JourneyReport(journey_id=jid, mood=mood)
        self.on_event("wake", {"mood": mood, "seeds": seeds, "budget": budget})

        harvested: list[str] = []
        seen_langs: list[str] = []
        attempts = 0
        # سقف المحاولات: مواقع تُرفض وصفحات فارغة يجب ألا توقف الرحلة
        max_attempts = budget * 4

        while report.stored < budget and attempts < max_attempts:
            attempts += 1
            lg = only_lang or self.p.pick_language(self.rng)
            dest = self._choose_destination(lg, seeds)
            if dest is None:
                continue
            if self.body.has_seen(dest.url):
                continue

            self.on_event("visit", {"url": dest.url, "lang": dest.lang,
                                    "source": dest.source})
            page = self._read(dest)
            report.visited += 1
            if page is None:
                report.failed += 1
                continue

            title, text = page["title"], page["text"]
            host = urlparse(dest.url).netloc
            if self.p.is_blocked(host, title):
                self.on_event("skip", {"url": dest.url, "why": "محجوب بشخصيته"})
                continue
            if not senses.looks_substantial(text):
                self.on_event("skip", {"url": dest.url, "why": "نصّ ضحل"})
                continue

            page_lang = self._settle_lang(dest.lang, page.get("lang", ""), text)
            page_id = self.body.store_page(
                journey_id=jid, url=dest.url, host=host, lang=page_lang,
                source=dest.source, title=title, text=text[: config.MAX_TEXT_CHARS],
            )
            if page_id is None:          # سبقتنا إليها رحلة أخرى
                continue

            digested = self.mind.digest(title, text, page_lang)
            self.body.remember(
                title=title, summary=digested["summary"], body=text[:4000],
                lang=page_lang, kind="web", keywords=digested["keywords"],
                source_url=dest.url, importance=digested["importance"],
                journey_id=jid, page_id=page_id,
            )
            for kw in digested["keywords"][:6]:
                self.body.bump_interest(kw, page_lang, amount=0.12)
            harvested.extend(digested["keywords"][:4])

            report.stored += 1
            report.highlights.append((title, page_lang))
            if page_lang not in seen_langs:
                seen_langs.append(page_lang)
            self.on_event("kept", {"title": title, "lang": page_lang,
                                   "importance": digested["importance"]})

        # ── العودة ───────────────────────────────────────────────────────
        self.body.conn.commit()
        self.body.decay_interests()
        report.langs = seen_langs
        report.duration = time.monotonic() - started
        report.journal = self.mind.reflect(
            mood, report.visited, report.stored, seen_langs, report.highlights
        )
        self.body.write_journal(jid, report.journal)
        self._save_journal_file(jid, report)
        self.body.end_journey(jid, langs=seen_langs, visited=report.visited,
                              stored=report.stored, failed=report.failed)
        self.on_event("home", {"stored": report.stored, "visited": report.visited})
        return report

    # ── اختيار المحطّة ───────────────────────────────────────────────────
    def _choose_destination(self, lg: str, seeds: list[str]) -> Optional[Destination]:
        """ثلاثة أبواب: عشوائي محض، بحث عن فضوله، أو خلاصة أخبار وطنية."""
        roll = self.rng.random()
        curiosity = self.p.curiosity

        if roll < curiosity * 0.5:
            return self._random_wiki(lg)
        if roll < 0.5 + curiosity * 0.2 and seeds:
            return self._search_wiki(lg, self.rng.choice(seeds))
        dest = self._from_feed(lg)
        return dest if dest else self._random_wiki(lg)

    def _from_feed(self, lg: str) -> Optional[Destination]:
        """يأخذ مقالاً من طابور تلك اللغة، ويملأ الطابور إن فرغ.

        جلب الخلاصة يكلّف طلباً كاملاً ويعود بعشرة مقالات؛ أخذ واحد ورمي
        التسعة يعني عشرة أضعاف الطلبات على خوادم الناس، وميزانية رحلة
        تنفد قبل أن تمتلئ.
        """
        if lg in self._drained:
            return None
        queue = self._pending.get(lg)
        if not queue:
            # لا نعيد جلب نفس الخلاصة بلا نهاية: نسمح بمحاولة لكل خلاصة
            # مسجّلة لهذه اللغة، ثم نعدّها مستنفدة لبقيّة الرحلة.
            allowed = max(1, len(self.sources.get("feeds", {}).get(lg, [])))
            if self._refills.get(lg, 0) >= allowed:
                self._drained.add(lg)
                return None
            self._refills[lg] = self._refills.get(lg, 0) + 1
            queue = sources.feed_destinations(self.f, self.sources, lg, self.rng,
                                              limit=10)
            if not queue:
                return None
            self.rng.shuffle(queue)
            self._pending[lg] = queue
        while queue:
            dest = queue.pop()
            if not self.body.has_seen(dest.url):
                return dest
        return None

    def _random_wiki(self, lg: str) -> Optional[Destination]:
        if lg not in self.sources.get("wiki_langs", []):
            return None            # لا ويكيبيديا بهذا اللسان في سجلّه
        site = "wikinews" if (
            self.rng.random() < 0.25 and lg in self.sources.get("wikinews_langs", [])
        ) else "wikipedia"
        titles = sources.wiki_random(self.f, lg, count=1, site=site)
        if not titles:
            return None
        return Destination(url=sources.wiki_url(lg, titles[0], site), lang=lg,
                           source=f"{lg}.{site}", title=titles[0], kind="wiki")

    def _search_wiki(self, lg: str, seed: str) -> Optional[Destination]:
        """يسأل عن فضوله بلسان أهل تلك اللغة، لا بلسانه هو."""
        if lg not in self.sources.get("wiki_langs", []):
            return None
        term = seed
        if lg != "ar":
            translated = sources.translate_term(self.f, self.body.conn, seed, "ar", lg)
            if translated:
                term = translated
                self.on_event("translate", {"from": seed, "to": term, "lang": lg})
        titles = sources.wiki_search(self.f, lg, term, limit=3)
        if not titles:
            return None
        title = self.rng.choice(titles)
        return Destination(url=sources.wiki_url(lg, title), lang=lg,
                           source=f"{lg}.wikipedia (بحث: {term})", title=title,
                           kind="wiki")

    # ── القراءة ──────────────────────────────────────────────────────────
    def _read(self, dest: Destination) -> Optional[dict]:
        try:
            if dest.kind == "wiki":
                site = "wikinews" if "wikinews" in dest.source else "wikipedia"
                got = sources.wiki_extract(self.f, dest.lang, dest.title, site=site)
                if not got or not got["text"].strip():
                    return None
                return {"title": got["title"], "text": got["text"], "lang": dest.lang}
            resp = self.f.get(dest.url)
            ctype = (resp.content_type or "").lower()
            if "html" not in ctype and "xml" not in ctype and ctype:
                return None
            got = senses.extract(resp.text(), base_url=dest.url)
            return {"title": got["title"] or dest.title, "text": got["text"],
                    "lang": got["lang"]}
        except FetchError as e:
            self.on_event("fail", {"url": dest.url, "why": str(e)})
            return None
        except Exception as e:                    # صفحة مشوّهة لا تُسقط الرحلة
            self.on_event("fail", {"url": dest.url, "why": f"{type(e).__name__}"})
            return None

    @staticmethod
    def _settle_lang(planned: str, declared: str, text: str) -> str:
        """اللغة التي نصدّقها: ما أعلنته الصفحة، ما لم تكذّبه كتابة النص."""
        if declared and len(declared) <= 3:
            return declared
        script = script_of(text)
        if script == "cjk" and planned not in ("zh", "ja", "ko"):
            return planned
        return planned

    # ── الفضول القادم ────────────────────────────────────────────────────
    def _current_seeds(self) -> list[str]:
        top = [t for t, _lg, _w in self.body.top_interests(limit=10)]
        base = top or list(self.p.seed_interests)
        harvested = [t for t, _lg, _w in self.body.top_interests(limit=20)][10:]
        return self.mind.drift(base, harvested, keep=8)

    def _save_journal_file(self, jid: int, report: JourneyReport) -> None:
        """نسخة إنسانية من اليوميّات، خارج قاعدة البيانات، تُقرأ بأي محرّر."""
        d = config.journal_dir()
        d.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d_%H%M%S", time.localtime())
        path = d / f"{stamp}_رحلة{jid}.md"
        lines = [
            f"# رحلة {jid} — {time.strftime('%Y-%m-%d %H:%M', time.localtime())}",
            f"\nالمزاج: {report.mood}  \n"
            f"زار: {report.visited} • حفظ: {report.stored} • أخفق: {report.failed}  \n"
            f"اللغات: {'، '.join(report.langs) or '—'}\n",
            "## ما كتبه\n", report.journal, "\n## ما رآه\n",
        ]
        lines += [f"- `[{lg}]` {t}" for t, lg in report.highlights]
        path.write_text("\n".join(lines), encoding="utf-8")
