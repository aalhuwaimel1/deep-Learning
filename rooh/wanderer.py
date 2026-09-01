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

from . import config, insight, research, senses, sources
from .drives import Drives
from .body import Body
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
    urges: list[str] = field(default_factory=list)     # ما أراده في كل خطوة
    asked: list[str] = field(default_factory=list)     # أسئلة فتحها
    answered: list[str] = field(default_factory=list)  # أسئلة أغلقها
    filled: list[tuple[str, str]] = field(default_factory=list)  # فجوات سدّها
    came_home_early: bool = False                      # عاد تعباً لا مكتفياً


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
        self._papers: dict[str, list[Destination]] = {}   # أوراق بحث بانتظار القراءة
        self._no_papers: set[str] = set()       # لغات لم تُجدِ فيها قواعد الأبحاث
        # حالته الداخلية، محفوظة في الجسد بين الرحلات
        self.drives = Drives.loads(self.body.load_drives())
        # فجواتٌ ينوي سدّها في هذه الرحلة: (مفهوم، لغةٌ تصمت عنه)
        self._gaps: list[tuple[str, str]] = []

    # ── الرحلة ───────────────────────────────────────────────────────────
    def journey(self, pages: Optional[int] = None,
                only_lang: Optional[str] = None) -> JourneyReport:
        budget = pages or self.p.pages_per_journey
        seeds = self._current_seeds()
        started = time.monotonic()

        # يستيقظ فيجد نفسه على حالٍ: أسئلةٌ تنتظره، وتعبُ أمسٍ قد زال
        self.drives.rest()
        self.drives.feel_questions(self.body.count_open_questions(),
                                   self.p.persistence)
        mood = self.drives.mood()

        jid = self.body.start_journey(seeds, mood)
        report = JourneyReport(journey_id=jid, mood=mood)
        self.on_event("wake", {"mood": mood, "seeds": seeds, "budget": budget,
                               "urge": self.drives.urge(bool(
                                   self.body.count_open_questions()))})

        known = self.body.known_terms()
        self._gaps = self._find_gaps()
        if self._gaps:
            self.on_event("gaps", {"count": len(self._gaps),
                                   "first": self._gaps[0]})
        harvested: list[str] = []
        seen_langs: list[str] = []
        attempts = 0
        # سقف المحاولات: مواقع تُرفض وصفحات فارغة يجب ألا توقف الرحلة
        max_attempts = budget * 4

        while report.stored < budget and attempts < max_attempts:
            attempts += 1
            has_q = self.body.count_open_questions() > 0
            urge = self.drives.urge(has_q)
            if urge == "عودة":
                # تعِب. لا فائدة من تجوّلٍ بلا انتباه.
                report.came_home_early = True
                self.on_event("tired", {"stored": report.stored, "of": budget})
                break
            # تجواله الحرّ يُسخَّر لسدّ فجواتك. لا يزاحم تعبَه ولا حيرته
            # ولا سؤالاً معلّقاً — تلك حاجاته هو، وهذه خدمته لك.
            if (urge in ("تجوّل", "غريب") and self._gaps and not only_lang
                    and self.rng.random() < self.p.service_bias):
                urge = "فجوة"
            report.urges.append(urge)

            lg = only_lang or self._pick_language_for(urge)
            dest = self._destination_for(urge, lg, seeds)
            if dest is None:
                if urge == "فجوة" and self._gaps:
                    self._gaps.pop(0)     # فجوةٌ تعذّر سدّها لا نعلق عندها
                continue
            if urge == "فجوة":
                lg = dest.lang
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
            # عتبة «الضحالة» للصفحات، لا للأوراق: ملخّص بحث في ٨٠٠ حرف
            # ورقةٌ كاملة، ورفضه لأنه «قصير» يرمي أغنى ما نعود به.
            if dest.kind != "paper" and not senses.looks_substantial(text):
                self.on_event("skip", {"url": dest.url, "why": "نصّ ضحل"})
                continue
            if dest.kind == "paper" and len(text) < 120:
                self.on_event("skip", {"url": dest.url, "why": "ورقة بلا ملخّص"})
                continue

            page_lang = self._settle_lang(dest.lang, page.get("lang", ""), text)
            page_id = self.body.store_page(
                journey_id=jid, url=dest.url, host=host, lang=page_lang,
                source=dest.source, title=title, text=text[: config.MAX_TEXT_CHARS],
            )
            if page_id is None:          # سبقتنا إليها رحلة أخرى
                continue

            # للورقة: نهضم عنوانها وملخّصها، لا بياناتها الوصفية
            to_digest = (dest.payload or {}).get("content") or text
            digested = self.mind.digest(title, to_digest, page_lang)
            mem_id = self.body.remember(
                title=title, summary=digested["summary"], body=text[:4000],
                lang=page_lang, kind=("paper" if dest.kind == "paper" else "web"),
                keywords=digested["keywords"],
                source_url=dest.url, importance=digested["importance"],
                journey_id=jid, page_id=page_id,
            )
            keywords = digested["keywords"]

            # ما مقدار الجديد في هذه الصفحة؟ عليه تدور حالته كلها.
            novelty = Drives.novelty(keywords, known)
            gain = self.drives.observe(novelty, self.p.openness, self.p.depth)

            # أسئلة أغلقتها هذه الصفحة
            closed = self.body.resolve_by_keywords(keywords, page_lang, mem_id)
            for term in closed:
                self.drives.answered()
                report.answered.append(term)
                self.on_event("answered", {"term": term})

            # وأسئلة فتحتها: مصطلحٌ بارز فيها لا يعرفه بعد
            for term in self._new_questions(keywords, known, closed):
                if self.body.ask(term, page_lang, context=title,
                                 from_memory=mem_id):
                    report.asked.append(term)
                    self.on_event("asked", {"term": term, "lang": page_lang})

            # يسجّل كل ما قرأه، لا ما شدّه فقط. التمييز بينهما في الوزن
            # لا في الوجود: الأوائل تجذبه، والبقيّة يعرفها فحسب.
            #
            # حين كان يسجّل الستّة الأولى ويقيس الجِدّة على الاثني عشر،
            # كان النصف الباقي «جديداً» أبداً، فتجمّدت الجِدّة على ٠٫٥
            # ولم يستطع أن يملّ ولا أن يحتار مهما قرأ.
            for rank, kw in enumerate(keywords):
                self.body.bump_interest(kw, page_lang,
                                        amount=0.12 if rank < 6 else 0.06)
                known.add(kw.lower())
            harvested.extend(keywords[:4])

            self.on_event("learned", {"novelty": round(novelty, 2),
                                      "gain": round(gain, 2),
                                      "mood": self.drives.mood()})
            report.stored += 1
            if urge == "فجوة" and self._gaps:
                concept, _lang = self._gaps.pop(0)
                report.filled.append((concept, page_lang))
                self.on_event("filled", {"concept": concept, "lang": page_lang})
            report.highlights.append((title, page_lang))
            if page_lang not in seen_langs:
                seen_langs.append(page_lang)
            self.on_event("kept", {"title": title, "lang": page_lang,
                                   "importance": digested["importance"]})

        # ── العودة ───────────────────────────────────────────────────────
        self.body.conn.commit()
        self.body.abandon_stale_questions(self.p.max_question_attempts)
        self.body.decay_interests()
        self._protect_obsessions()
        self.drives.feel_questions(self.body.count_open_questions(),
                                   self.p.persistence)
        self.body.save_drives(self.drives.dumps())
        report.mood = self.drives.mood()
        report.langs = seen_langs
        report.duration = time.monotonic() - started
        report.journal = self.mind.reflect(
            report.mood, report.visited, report.stored, seen_langs,
            report.highlights,
            state={"urges": list(dict.fromkeys(report.urges)),
                   "asked": report.asked, "answered": report.answered,
                   "filled": [c for c, _lg in report.filled],
                   "aspiration": self.p.aspiration,
                   "came_home_early": report.came_home_early},
        )
        self.body.write_journal(jid, report.journal)
        self._save_journal_file(jid, report)
        self.body.end_journey(jid, langs=seen_langs, visited=report.visited,
                              stored=report.stored, failed=report.failed)
        self.on_event("home", {"stored": report.stored, "visited": report.visited})
        return report

    # ── ترجمة النزوع إلى فعل ─────────────────────────────────────────────
    def _find_gaps(self) -> list[tuple[str, str]]:
        """مواضيع يكتب عنها عالَمٌ لغويٌّ وتصمت عنها لغاتٌ يزورها كثيراً.

        بلا شبكة: يعمل بما في معجمه وما جمعه. أوّل رحلاته لا فجوات فيها
        لأن معجمه فارغ — وهذا صحيح، لا نصطنع له فجوات لا يملك دليلها.
        """
        if self.p.service_bias <= 0:
            return []
        langs = list(self.p.languages)
        out: list[tuple[str, str]] = []
        for gap in insight.gaps(self.body, langs, limit=8):
            for lg in gap.missing:
                out.append((gap.concept, lg))
        self.rng.shuffle(out)
        return out[:12]

    def _gap_destination(self) -> Optional[Destination]:
        """يذهب إلى اللغة الصامتة ليقرأ فيها عن الموضوع — إن كان لها فيه شيء."""
        for concept, lg in list(self._gaps):
            term = self._term_in(lg, concept)
            self.on_event("filling", {"concept": concept, "lang": lg,
                                      "term": term})
            for door in (lambda: self._search_wiki(lg, term),
                         lambda: self._research_paper(lg, term)):
                dest = door()
                if dest is not None:
                    return dest
            self._gaps.remove((concept, lg))
        return None

    def _pick_language_for(self, urge: str) -> str:
        """النزوع يختار اللسان أيضاً، لا الوجهة وحدها."""
        if urge == "مألوف":
            # أرضٌ يعرفها: اللسان الذي له فيه أكثر الذكريات
            rows = self.body.conn.execute(
                """SELECT lang, COUNT(*) c FROM memories
                   GROUP BY lang ORDER BY c DESC LIMIT 3"""
            ).fetchall()
            known_langs = [r["lang"] for r in rows if r["lang"] in self.p.languages]
            if known_langs:
                return self.rng.choice(known_langs)
        elif urge == "غريب":
            # لسانٌ لم يزره قطّ، وإلا فأقلّها زيارةً
            visited = {r["lang"] for r in self.body.conn.execute(
                "SELECT DISTINCT lang FROM memories")}
            unvisited = [c for c in self.p.languages if c not in visited]
            if unvisited:
                return self.rng.choice(unvisited)
        return self.p.pick_language(self.rng)

    def _destination_for(self, urge: str, lg: str,
                         seeds: list[str]) -> Optional[Destination]:
        """كل نزوعٍ وبابه. هذا هو موضع تحوّل الحالة الداخلية إلى سلوك."""
        if urge == "فجوة":
            dest = self._gap_destination()
            if dest is not None:
                return dest
        elif urge == "سؤال":
            dest = self._chase_question(lg)
            if dest is not None:
                return dest
        elif urge == "مألوف":
            # يرجع لأقوى ما في خريطة فضوله ليربط عليه ما جمع
            anchors = [t for t, _lg, _w in self.body.top_interests(limit=5)]
            for anchor in anchors:
                if self.p.repels(anchor):
                    continue
                dest = self._search_wiki(lg, anchor)
                if dest is not None:
                    return dest
        elif urge == "غريب":
            dest = self._random_wiki(lg)
            if dest is not None:
                return dest
        return self._choose_destination(lg, seeds)

    def _chase_question(self, lg: str) -> Optional[Destination]:
        """يلاحق سؤالاً فتحه ولم يغلقه. هذا ما يصل رحلة اليوم برحلة أمس."""
        pending = self.body.open_questions(limit=6)
        self.rng.shuffle(pending)
        for qid, term, q_lang, _attempts in pending:
            if self.p.repels(term):
                continue
            self.body.note_attempt(qid)
            self.on_event("chasing", {"term": term, "lang": lg})
            # يسأل عنه أولاً حيث صادفه، ثم بلسانه هو
            for target in (q_lang if q_lang != "mul" else lg, lg):
                dest = self._search_wiki(target, term)
                if dest is not None:
                    return dest
            dest = self._research_paper(lg, term)
            if dest is not None:
                return dest
        self.body.conn.commit()
        return None

    def _new_questions(self, keywords: list[str], known: set[str],
                       closed: list[str]) -> list[str]:
        """ما الذي مرّ به في هذه الصفحة ولم يعرفه؟

        نأخذ اثنين على الأكثر: من يفتح عشرين سؤالاً في صفحة واحدة لا
        يلاحق شيئاً — يغرق. والسؤال يجب أن يكون مصطلحاً لا شظيّة.
        """
        from .lang import is_continuous, script_of

        just_closed = {c.lower() for c in closed}
        out: list[str] = []
        for term in keywords[:8]:
            low = term.lower()
            if low in known or low in just_closed:
                continue
            # حدّ الطول بحسب الكتابة: «量子» كلمة كاملة، و«ab» شظيّة.
            # حدٌّ واحد بالحروف كان يمنعه من السؤال بالصينية أصلاً.
            floor = 2 if is_continuous(script_of(term)) else 3
            if len(term) < floor or self.p.repels(term):
                continue
            out.append(term)
            if len(out) == 2:
                break
        return out

    def _protect_obsessions(self) -> None:
        """الهاجس لا يُنسى بالخفوت. هذا معنى أن يكون هاجساً."""
        for term in self.p.obsessions:
            self.body.bump_interest(term, "mul", amount=0.35)
        self.body.conn.commit()

    # ── اختيار المحطّة ───────────────────────────────────────────────────
    def _choose_destination(self, lg: str, seeds: list[str]) -> Optional[Destination]:
        """أربعة أبواب: ورقة بحث، عشوائي محض، بحث عن فضوله، أو خبر وطني.

        نرتّب الأبواب بحسب مزاجه ثم **نطرقها بالترتيب حتى يُفتح أحدها**.
        الاكتفاء بباب واحد يعني أن رحلةً كاملة تضيع لو كان ذلك الباب
        مغلقاً — موقعٌ محجوب أو خلاصة ميّتة تُنهي جولته بلا سبب.
        """
        roll = self.rng.random()
        curiosity = self.p.curiosity
        seed = self.rng.choice(seeds) if seeds else None

        doors: list = []
        if seed and self.rng.random() < self.p.research_bias:
            doors.append(lambda: self._research_paper(lg, seed))
        if roll < curiosity * 0.5:
            doors += [lambda: self._random_wiki(lg), lambda: self._from_feed(lg)]
        elif roll < 0.5 + curiosity * 0.2 and seed:
            doors += [lambda: self._search_wiki(lg, seed),
                      lambda: self._from_feed(lg), lambda: self._random_wiki(lg)]
        else:
            doors += [lambda: self._from_feed(lg), lambda: self._random_wiki(lg)]
        if seed:
            doors.append(lambda: self._search_wiki(lg, seed))

        for door in doors:
            dest = door()
            if dest is not None:
                return dest
        return None

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

    def _term_in(self, lg: str, seed: str) -> str:
        """المصطلح كما يُقال بتلك اللغة — أو كما هو إن لم يوجد مقابل."""
        if lg == "ar":
            return seed
        translated = sources.translate_term(self.f, self.body.conn, seed, "ar", lg)
        if translated:
            self.on_event("translate", {"from": seed, "to": translated, "lang": lg})
            return translated
        return seed

    def _research_paper(self, lg: str, seed: str) -> Optional[Destination]:
        """ورقة بحث بلغة أهلها. الملخّص يأتي مع النتيجة فلا نطلب الصفحة."""
        if lg in self._no_papers:
            return None
        queue = self._papers.get(lg)
        if not queue:
            term = self._term_in(lg, seed)
            papers = research.search_papers(self.f, term, lang=lg, limit=8)
            if not papers:
                # قاعدةٌ لم تُجب بهذه اللغة (أو الشبكة مقطوعة): لا نعيد
                # سؤالها في كل محاولة فنُنفق الرحلة كلها في انتظار مهلات.
                self._no_papers.add(lg)
                return None
            queue = [
                Destination(url=pp.url or f"doi:{pp.doi}", lang=pp.lang or lg,
                            source=f"{pp.provider}: {pp.venue or 'بحث'}",
                            title=pp.title, kind="paper",
                            payload={"text": pp.as_text(), "year": pp.year,
                                     "cited_by": pp.cited_by, "doi": pp.doi})
                for pp in papers if pp.url or pp.doi
            ]
            self.rng.shuffle(queue)
            self._papers[lg] = queue
        while queue:
            dest = queue.pop()
            if not self.body.has_seen(dest.url):
                return dest
        return None

    def _search_wiki(self, lg: str, seed: str) -> Optional[Destination]:
        """يسأل عن فضوله بلسان أهل تلك اللغة، لا بلسانه هو."""
        if lg not in self.sources.get("wiki_langs", []):
            return None
        term = self._term_in(lg, seed)
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
            if dest.kind == "paper" and dest.payload:
                return {"title": dest.title, "text": dest.payload["text"],
                        "lang": dest.lang}
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
        return planned

    # ── الفضول القادم ────────────────────────────────────────────────────
    def _current_seeds(self) -> list[str]:
        """ما يخرج باحثاً عنه: رغباته الخاصة أولاً، ثم فضوله المتحرّك.

        الترتيب مقصود — الهواجس والطموح تدخل دائماً، فلا يُغرقها انجرافُ
        الفضول مهما تغيّرت اهتماماته.
        """
        own = self.p.wants(self.rng)
        top = [t for t, _lg, _w in self.body.top_interests(limit=10)]
        base = top or list(self.p.seed_interests)
        harvested = [t for t, _lg, _w in self.body.top_interests(limit=20)][10:]
        drifted = self.mind.drift(base, harvested, keep=8)
        seeds = own + [d for d in drifted if d not in own]
        return [s for s in seeds if not self.p.repels(s)][:10]

    def _save_journal_file(self, jid: int, report: JourneyReport) -> None:
        """نسخة إنسانية من اليوميّات، خارج قاعدة البيانات، تُقرأ بأي محرّر."""
        d = config.journal_dir()
        d.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d_%H%M%S", time.localtime())
        path = d / f"{stamp}_رحلة{jid}.md"
        lines = [
            f"# رحلة {jid} — {time.strftime('%Y-%m-%d %H:%M', time.localtime())}",
            f"\nالمزاج: {report.mood}  \n"
            f"ما أراده: {'، '.join(dict.fromkeys(report.urges)) or '—'}  \n"
            f"زار: {report.visited} • حفظ: {report.stored} • أخفق: {report.failed}"
            + (" • عاد متعباً" if report.came_home_early else "") + "  \n"
            f"اللغات: {'، '.join(report.langs) or '—'}  \n"
            f"سأل: {'، '.join(report.asked) or '—'}  \n"
            f"أجاب: {'، '.join(report.answered) or '—'}\n",
            "## ما كتبه\n", report.journal, "\n## ما رآه\n",
        ]
        lines += [f"- `[{lg}]` {t}" for t, lg in report.highlights]
        path.write_text("\n".join(lines), encoding="utf-8")
