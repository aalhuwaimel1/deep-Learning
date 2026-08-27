"""اختبارات رُوح — بلا إنترنت: نرفع «شبكة» محلية بلغات مختلفة ونرسله فيها."""

from __future__ import annotations

import http.server
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rooh import lang, senses, sources          # noqa: E402
from rooh.body import Body                       # noqa: E402
from rooh.mind import Mind                       # noqa: E402
from rooh.net import Fetcher                     # noqa: E402
from rooh.personality import Personality         # noqa: E402
from rooh.wanderer import Wanderer               # noqa: E402

# ── نصوص بلغات حقيقية ────────────────────────────────────────────────────
PAGES = {
    "zh": ("量子计算", "量子计算是一种利用量子力学现象进行计算的方式。量子计算机使用量子比特作为"
                  "信息的基本单位。与经典比特不同，量子比特可以处于叠加态。量子纠缠是量子计算"
                  "的另一个核心资源。目前量子计算仍处于早期阶段，纠错是主要挑战之一。"
                  "许多研究机构正在开发更稳定的量子比特实现方案。"),
    "ja": ("量子計算", "量子計算は量子力学の原理を利用した計算方式である。量子ビットは重ね合わせの"
                  "状態を取ることができる。量子もつれは計算資源として利用される。誤り訂正は"
                  "実用化における最大の課題とされている。多くの研究機関が超伝導量子ビットの"
                  "開発を進めている。"),
    "ru": ("Квантовые вычисления", "Квантовые вычисления используют явления квантовой механики. "
           "Кубит является основной единицей квантовой информации. В отличие от классического бита, "
           "кубит может находиться в суперпозиции. Квантовая запутанность служит важным ресурсом. "
           "Коррекция ошибок остаётся главной проблемой практической реализации."),
    "ar": ("الحوسبة الكمية", "الحوسبة الكمية طريقة حساب تعتمد على ظواهر ميكانيكا الكم. الكيوبت هو "
           "الوحدة الأساسية للمعلومة الكمية. خلافاً للبت التقليدي يمكن للكيوبت أن يكون في حالة تراكب. "
           "التشابك الكمي مورد أساسي في الحوسبة الكمية. تصحيح الأخطاء هو التحدي الأكبر أمام التطبيق العملي."),
}


HITS: dict[str, int] = {}


class _Site(http.server.BaseHTTPRequestHandler):
    """شبكة مصغّرة: خلاصات RSS بلغات مختلفة، وصفحات HTML وراءها."""

    def do_GET(self) -> None:                      # noqa: N802
        path = self.path
        HITS[path] = HITS.get(path, 0) + 1
        if path.startswith("/feed/"):
            lg = path.split("/")[-1].replace(".xml", "")
            if lg not in PAGES:
                return self._send(404, "text/plain", "no")
            title, _ = PAGES[lg]
            host = f"http://{self.headers.get('Host')}"
            xml = (
                '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
                f"<title>{lg}</title>"
                + "".join(
                    f"<item><title>{title} {i}</title>"
                    f"<link>{host}/page/{lg}/{i}</link></item>"
                    for i in range(1, 6)
                )
                + "</channel></rss>"
            )
            return self._send(200, "application/rss+xml", xml)

        if path.startswith("/page/"):
            _, _, lg, idx = path.split("/")
            title, text = PAGES[lg]
            html = (
                f'<!DOCTYPE html><html lang="{lg}"><head><title>{title} {idx}</title>'
                "<style>.x{color:red}</style><script>var a=1;</script></head><body>"
                "<nav>قائمة روابط لا تهمّ</nav>"
                f"<article><h1>{title}</h1><p>{text}</p><p>{text}</p></article>"
                '<a href="/page/' + lg + '/9">أكثر</a></body></html>'
            )
            return self._send(200, "text/html; charset=utf-8", html)

        if path == "/thin":
            return self._send(200, "text/html", "<html><body><p>قصير</p></body></html>")
        return self._send(404, "text/plain", "no")

    def _send(self, code: int, ctype: str, body: str) -> None:
        raw = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a: object) -> None:     # صمت أثناء الاختبار
        pass


class LocalNet:
    def __enter__(self) -> str:
        self.srv = socketserver.TCPServer(("127.0.0.1", 0), _Site)
        self.port = self.srv.server_address[1]
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start()
        return f"http://127.0.0.1:{self.port}"

    def __exit__(self, *exc: object) -> None:
        self.srv.shutdown()
        self.srv.server_close()


# ── اللغة ────────────────────────────────────────────────────────────────
class TestLang(unittest.TestCase):
    def test_cjk_is_not_one_giant_word(self) -> None:
        toks = lang.tokenize(PAGES["zh"][1], "zh")
        self.assertGreater(len(toks), 20)
        self.assertTrue(all(len(t) == 2 for t in toks))

    def test_keywords_per_script(self) -> None:
        self.assertIn("量子", lang.keywords(PAGES["zh"][1], "zh", 8))
        self.assertIn("量子", lang.keywords(PAGES["ja"][1], "ja", 8))
        self.assertIn("кубит", lang.keywords(PAGES["ru"][1], "ru", 8))
        self.assertIn("الكمية", lang.keywords(PAGES["ar"][1], "ar", 8))

    def test_japanese_drops_grammar_bigrams(self) -> None:
        kws = lang.keywords(PAGES["ja"][1], "ja", 10)
        self.assertFalse(any("は" in k or "であ" == k for k in kws), kws)

    def test_script_detection(self) -> None:
        self.assertEqual(lang.script_of(PAGES["zh"][1]), "cjk")
        self.assertEqual(lang.script_of(PAGES["ru"][1]), "cyrillic")
        self.assertEqual(lang.script_of(PAGES["ar"][1]), "arabic")

    def test_cjk_sentences_split_without_spaces(self) -> None:
        one = lang.summarize(PAGES["zh"][1], "zh", 1)
        self.assertTrue(one.endswith("。"))
        self.assertLess(len(one), len(PAGES["zh"][1]))

    def test_summary_never_invents(self) -> None:
        src = PAGES["ar"][1]
        out = lang.summarize(src, "ar", 2)
        for sentence in out.split("."):
            if sentence.strip():
                self.assertIn(sentence.strip()[:20], src)

    def test_summary_does_not_repeat_a_sentence(self) -> None:
        """صفحات كثيرة تكرّر مقدّمتها؛ خلاصة تعيد الجملة مرّتين ليست خلاصة."""
        one = "الحوسبة الكمية طريقة حساب تعتمد على ظواهر ميكانيكا الكم."
        two = "الكيوبت هو الوحدة الأساسية للمعلومة الكمية في هذا النظام."
        out = lang.summarize(" ".join([one, two, one, one, two]), "ar", 3)
        self.assertEqual(out.count(one), 1, out)
        self.assertEqual(out.count(two), 1, out)

    def test_summary_dedupes_html_shaped_text(self) -> None:
        """شكل النصّ كما يخرج فعلاً من HTML: سطر عنوان ثم فقرة مكرّرة."""
        para = ("Квантовые вычисления используют явления квантовой механики. "
                "Кубит является основной единицей квантовой информации.")
        extracted = f"Квантовые вычисления\n{para}\n{para}"
        out = lang.summarize(extracted, "ru", 3)
        first = "Квантовые вычисления используют явления квантовой механики."
        self.assertEqual(out.count(first), 1, out)

    def test_empty_text(self) -> None:
        self.assertEqual(lang.summarize("", "ar"), "")
        self.assertEqual(lang.keywords("", "ar"), [])


# ── الحواسّ ──────────────────────────────────────────────────────────────
class TestSenses(unittest.TestCase):
    def test_strips_script_style_nav(self) -> None:
        html = ('<html lang="ja"><head><title>عنوان</title><script>var x=1</script>'
                '<style>a{}</style></head><body><nav>تنقّل</nav>'
                '<p>نصّ حقيقي</p><a href="/b">رابط</a></body></html>')
        got = senses.extract(html, "http://h/a")
        self.assertEqual(got["title"], "عنوان")
        self.assertEqual(got["lang"], "ja")
        self.assertIn("نصّ حقيقي", got["text"])
        for junk in ("var x=1", "تنقّل", "a{}"):
            self.assertNotIn(junk, got["text"])
        self.assertEqual(got["links"], ["http://h/b"])

    def test_broken_html_does_not_raise(self) -> None:
        got = senses.extract("<html><body><p>باقٍ<div><span>", "http://h/")
        self.assertIn("باقٍ", got["text"])

    def test_substantiality_gate(self) -> None:
        self.assertFalse(senses.looks_substantial("قصير"))
        self.assertTrue(senses.looks_substantial("ا" * 500))
        self.assertFalse(senses.looks_substantial(""))

    def test_cjk_article_is_not_dismissed_as_shallow(self) -> None:
        """٢٦٠ حرفاً صينياً مقالٌ كامل، لا «نصّ ضحل».

        الحرف الصيني يعادل كلمة؛ عتبةٌ واحدة بالحروف للكتابتين ترمي
        المحتوى الصيني والياباني كلّه.
        """
        zh = PAGES["zh"][1]
        self.assertLess(len(zh), 400)
        self.assertTrue(senses.looks_substantial(zh))
        # وفي المقابل: نصّ لاتيني بنفس الطول يبقى ضحلاً
        self.assertFalse(senses.looks_substantial("word " * 50))


# ── الجسد ────────────────────────────────────────────────────────────────
class TestBody(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.body = Body(Path(self.tmp.name) / "b.db")

    def tearDown(self) -> None:
        self.body.close()
        self.tmp.cleanup()

    def test_remember_and_recall(self) -> None:
        self.body.remember(title="الحوسبة الكمية", summary=PAGES["ar"][1],
                           body=PAGES["ar"][1], lang="ar", keywords=["الكم"])
        found = self.body.recall("الكمية")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].title, "الحوسبة الكمية")

    def test_recall_across_scripts(self) -> None:
        self.body.remember(title="量子计算", summary=PAGES["zh"][1], lang="zh")
        self.assertTrue(self.body.recall("量子计算"))

    def test_recall_partial_cjk_term(self) -> None:
        """انحدار: FTS5 يعدّ مقطع CJK كلّه كلمةً واحدة، فيخفق البحث عن جزء منه."""
        self.body.remember(title="量子計算", summary=PAGES["ja"][1],
                           body=PAGES["ja"][1], lang="ja")
        self.body.remember(title="量子计算", summary=PAGES["zh"][1],
                           body=PAGES["zh"][1], lang="zh")
        for term in ("量子", "計算", "誤り訂正", "纠错"):
            self.assertTrue(self.body.recall(term), f"لم يجد: {term}")

    def test_recall_empty_query(self) -> None:
        self.body.remember(title="ت", summary="نص", lang="ar")
        self.assertEqual(self.body.recall("   "), [])

    def test_recall_strengthens_memory(self) -> None:
        mid = self.body.remember(title="ت", summary="نصّ للتذكّر", lang="ar",
                                 importance=0.5)
        self.body.recall("للتذكّر")
        row = self.body.conn.execute(
            "SELECT recall_count, importance FROM memories WHERE id=?", (mid,)
        ).fetchone()
        self.assertEqual(row["recall_count"], 1)
        self.assertGreater(row["importance"], 0.5)

    def test_fts_special_chars_do_not_crash(self) -> None:
        self.body.remember(title="ت", summary="نصّ", lang="ar")
        for q in ['"', "AND OR", "*", "a NEAR/2 b", "(("]:
            self.body.recall(q)          # لا يرمي استثناء

    def test_page_dedupe(self) -> None:
        first = self.body.store_page(journey_id=None, url="http://h/x", host="h",
                                     lang="ar", source="s", title="t", text="نص")
        again = self.body.store_page(journey_id=None, url="http://h/x", host="h",
                                     lang="ar", source="s", title="t", text="نص")
        self.assertIsNotNone(first)
        self.assertIsNone(again)
        self.assertTrue(self.body.has_seen("http://h/x"))

    def test_interest_decay_removes_the_forgotten(self) -> None:
        self.body.bump_interest("باقٍ", "ar", amount=5.0)
        self.body.bump_interest("زائل", "ar", amount=0.05)
        for _ in range(40):
            self.body.decay_interests(factor=0.9)
        terms = [t for t, _, _ in self.body.top_interests(20)]
        self.assertIn("باقٍ", terms)
        self.assertNotIn("زائل", terms)

    def test_stats(self) -> None:
        self.body.remember(title="t", summary="s", lang="ja")
        st = self.body.stats()
        self.assertEqual(st["memories"], 1)
        self.assertEqual(st["by_lang"]["ja"], 1)


# ── المصادر ──────────────────────────────────────────────────────────────
class TestSources(unittest.TestCase):
    def test_rss_and_atom(self) -> None:
        rss = ('<rss version="2.0"><channel><item><title>ت</title>'
               "<link>http://h/1</link></item></channel></rss>")
        atom = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>ت</title>'
                '<link href="http://h/2"/></entry></feed>')
        self.assertEqual(sources.parse_feed(rss)[0]["url"], "http://h/1")
        self.assertEqual(sources.parse_feed(atom)[0]["url"], "http://h/2")

    def test_malformed_feed_returns_empty(self) -> None:
        self.assertEqual(sources.parse_feed("<not xml"), [])
        self.assertEqual(sources.parse_feed(""), [])


# ── الرحلة كاملة ─────────────────────────────────────────────────────────
class TestJourney(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.body = Body(Path(self.tmp.name) / "b.db")

    def tearDown(self) -> None:
        self.body.close()
        self.tmp.cleanup()

    def _wanderer(self, base: str, **kw) -> Wanderer:
        p = Personality.default()
        p.curiosity = 0.0            # يبقى في شبكتنا المحلية، لا يخرج لويكيبيديا
        p.seed_interests = []
        p.languages = {lg: 1.0 for lg in PAGES}
        p.limits = {**p.limits, **kw}
        src = {"wiki_langs": [], "wikinews_langs": [],
               "feeds": {lg: [{"name": f"موقع {lg}", "url": f"{base}/feed/{lg}.xml"}]
                         for lg in PAGES}}
        return Wanderer(self.body, p, Mind(p, use_llm=False),
                        fetcher=Fetcher(delay=0.0, respect_robots=False),
                        source_map=src)

    def test_full_journey(self) -> None:
        import os

        with LocalNet() as base:
            os.environ.setdefault("ROOH_HOME", self.tmp.name)
            w = self._wanderer(base)
            rep = w.journey(pages=6)

        self.assertEqual(rep.stored, 6)
        self.assertGreaterEqual(rep.visited, 6)
        self.assertTrue(rep.journal)

        # كل ما رآه صار جسداً
        st = self.body.stats()
        self.assertEqual(st["memories"], 6)
        self.assertEqual(st["pages"], 6)
        self.assertEqual(st["journeys"], 1)

        # تجوّل بأكثر من لسان، وحفظ لكل لسان ذاكرته
        self.assertGreater(len(rep.langs), 1)
        for lg in rep.langs:
            self.assertIn(lg, PAGES)

        # الخلاصات ليست فارغة، والمفاتيح استُخلصت بحسب الكتابة
        for m in self.body.recent(10):
            self.assertTrue(m.summary.strip(), f"خلاصة فارغة: {m.title}")
            self.assertTrue(m.keywords, f"بلا مفاتيح: {m.title}")

        # الفضول تحرّك من الصفر
        self.assertTrue(self.body.top_interests(5))

    def test_second_journey_does_not_re_store_same_pages(self) -> None:
        with LocalNet() as base:
            w = self._wanderer(base)
            w.journey(pages=4)
            before = self.body.stats()["pages"]
            w.journey(pages=4)
            after = self.body.stats()["pages"]
        # الشبكة المحلية فيها ٢٠ صفحة فقط؛ المهم ألا تتكرّر أي صفحة
        urls = [r[0] for r in self.body.conn.execute("SELECT url FROM pages")]
        self.assertEqual(len(urls), len(set(urls)))
        self.assertGreater(after, before)

    def test_journey_survives_dead_sources(self) -> None:
        with LocalNet() as base:
            p = Personality.default()
            p.curiosity = 0.0
            p.seed_interests = []
            p.languages = {"zh": 1.0, "xx": 1.0}
            src = {"wiki_langs": [], "wikinews_langs": [], "feeds": {
                "zh": [{"name": "حيّ", "url": f"{base}/feed/zh.xml"}],
                "xx": [{"name": "ميّت", "url": f"{base}/feed/none.xml"}],
            }}
            w = Wanderer(self.body, p, Mind(p, use_llm=False),
                         fetcher=Fetcher(delay=0.0, respect_robots=False),
                         source_map=src)
            rep = w.journey(pages=3)
        self.assertEqual(rep.stored, 3)      # المصدر الميّت لم يوقف الرحلة

    def test_feed_is_fetched_once_not_once_per_page(self) -> None:
        """الخلاصة تعود بعشرة مقالات؛ أخذ واحد ورمي الباقي يُغرق خوادم الناس."""
        HITS.clear()
        with LocalNet() as base:
            w = self._wanderer(base)
            w.journey(pages=8, only_lang="zh")
        feed_hits = HITS.get("/feed/zh.xml", 0)
        page_hits = sum(v for k, v in HITS.items() if k.startswith("/page/"))
        self.assertGreaterEqual(page_hits, 5)
        self.assertLessEqual(feed_hits, 3, f"جُلبت الخلاصة {feed_hits} مرّة")

    def test_cjk_pages_actually_get_stored(self) -> None:
        """انحدار: كانت الصفحات الصينية تُرمى كلها بحجّة أنها قصيرة."""
        with LocalNet() as base:
            w = self._wanderer(base)
            rep = w.journey(pages=3, only_lang="zh")
        self.assertEqual(rep.stored, 3)
        self.assertEqual(self.body.stats()["by_lang"].get("zh"), 3)

    def test_blocked_host_is_respected(self) -> None:
        with LocalNet() as base:
            w = self._wanderer(base, blocked_hosts=["127.0.0.1"])
            rep = w.journey(pages=2)
        self.assertEqual(rep.stored, 0)
        self.assertEqual(self.body.stats()["memories"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
