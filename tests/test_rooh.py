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

from rooh import insight, lang, languages, research, senses, sources   # noqa: E402
from rooh.drives import Drives                 # noqa: E402
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

    # كتابات العالم كما تصل فعلاً من مواقعها
    WORLD = {
        "hi": "कृत्रिम बुद्धिमत्ता और भारतीय भाषाओं का प्रसंस्करण। इस शोध में "
              "हिंदी भाषा मॉडल प्रस्तुत किया गया है।",
        "ta": "செயற்கை நுண்ணறிவு மற்றும் தமிழ் மொழி ஆய்வு நடைபெற்றது",
        "bn": "কৃত্রিম বুদ্ধিমত্তা এবং বাংলা ভাষা প্রক্রিয়াকরণ গবেষণা",
        "am": "ሰው ሰራሽ አስተውሎት እና የአማርኛ ቋንቋ ጥናት",
        "ka": "ხელოვნური ინტელექტი და ქართული ენა",
        "th": "ปัญญาประดิษฐ์และการเรียนรู้ของเครื่องกำลังพัฒนา",
        "km": "បញ្ញាសិប្បនិម្មិតនិងការរៀនម៉ាស៊ីន",
        "he": "בינה מלאכותית ועיבוד שפה עברית",
        "el": "Τεχνητή νοημοσύνη και επεξεργασία γλώσσας",
    }

    def test_every_script_yields_tokens(self) -> None:
        """انحدار: `\\w` في بايثون لا يعدّ علامات التشكيل حروفاً، فكانت
        التاميلية تُقطّع إلى صفر كلمات، والهندية إلى شظيّة واحدة."""
        for code, text in self.WORLD.items():
            toks = lang.tokenize(text, code)
            self.assertGreaterEqual(len(toks), 3, f"{code}: {toks}")
            self.assertTrue(lang.keywords(text, code, 5), code)

    def test_indic_words_stay_whole(self) -> None:
        toks = lang.tokenize(self.WORLD["hi"], "hi")
        self.assertIn("प्रसंस्करण", toks)     # لا «करण»
        self.assertIn("कृत्रिम", toks)
        self.assertIn("தமிழ்", lang.tokenize(self.WORLD["ta"], "ta"))

    def test_continuous_scripts_are_ngrammed(self) -> None:
        """التايلندية والخميرية بلا فراغات ككتابات الشرق الأقصى."""
        for code in ("th", "km"):
            script = lang.script_of(self.WORLD[code])
            self.assertTrue(lang.is_continuous(script), f"{code}={script}")
            self.assertGreater(len(lang.tokenize(self.WORLD[code], code)), 10)
        # بينما الهندية والتاميلية تفصل بفراغ، فلا تُعامَل معاملتها
        for code in ("hi", "ta", "am", "ka"):
            self.assertFalse(lang.is_continuous(lang.script_of(self.WORLD[code])), code)

    def test_danda_ends_a_hindi_sentence(self) -> None:
        one = lang.summarize(self.WORLD["hi"], "hi", 1)
        self.assertTrue(one.endswith("।"), one)
        self.assertLess(len(one), len(self.WORLD["hi"]))

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


# ── لغات العالم ──────────────────────────────────────────────────────────
class TestLanguages(unittest.TestCase):
    def test_registry_is_wide_and_well_formed(self) -> None:
        self.assertGreater(len(languages.LANGUAGES), 60)
        for code, info in languages.LANGUAGES.items():
            self.assertRegex(code, r"^[a-z]{2,3}$")
            self.assertEqual(len(info), 5)
            ar, native, script, region, weight = info
            self.assertTrue(ar and native and script and region)
            self.assertGreater(weight, 0)

    def test_profiles_are_normalized(self) -> None:
        for name in ("متوازن", "العالم", *languages.REGIONS):
            w = languages.profile(name)
            self.assertTrue(w, name)
            self.assertAlmostEqual(sum(w.values()), 1.0, places=3, msg=name)

    def test_world_profile_covers_every_language(self) -> None:
        self.assertEqual(set(languages.profile("العالم")), set(languages.LANGUAGES))

    def test_region_profile_stays_in_region(self) -> None:
        for code in languages.profile("أفريقيا"):
            self.assertEqual(languages.region_of(code), "أفريقيا")

    def test_unknown_profile_falls_back(self) -> None:
        self.assertEqual(languages.profile("لا-يوجد"), languages.profile("متوازن"))


# ── الأبحاث ──────────────────────────────────────────────────────────────
class _FakeFetcher:
    """يردّ بما نمليه عليه، فنختبر التفكيك لا الشبكة."""

    def __init__(self, payload: object, raises: bool = False):
        self.payload = payload
        self.raises = raises
        self.urls: list[str] = []

    def get_json(self, url: str) -> object:
        self.urls.append(url)
        if self.raises:
            from rooh.net import FetchError

            raise FetchError("مقطوع")
        return self.payload

    def get(self, url: str, accept: str = "") -> object:
        self.urls.append(url)
        if self.raises:
            from rooh.net import FetchError

            raise FetchError("مقطوع")

        class R:
            def text(_self) -> str:
                return self.payload  # type: ignore[return-value]

        return R()


class TestResearch(unittest.TestCase):
    def test_openalex_rebuilds_inverted_abstract(self) -> None:
        """OpenAlex يعطي الملخّص مقلوباً {كلمة: مواضعها}؛ نعيد ترتيبه."""
        payload = {"results": [{
            "id": "https://openalex.org/W1", "doi": "https://doi.org/10.1/x",
            "display_name": "量子計算の誤り訂正", "language": "ja",
            "publication_year": 2024, "cited_by_count": 7,
            "abstract_inverted_index": {"本": [0], "研究": [1], "では": [2],
                                        "量子": [3], "誤り訂正": [4]},
            "authorships": [{"author": {"display_name": "田中 太郎"}}],
            "primary_location": {"landing_page_url": "https://j.example/1",
                                 "source": {"display_name": "日本物理学会"}},
            "open_access": {"oa_url": "https://j.example/1.pdf"},
        }]}
        f = _FakeFetcher(payload)
        papers = research.openalex_search(f, "量子", lang="ja")
        self.assertEqual(len(papers), 1)
        pp = papers[0]
        self.assertEqual(pp.abstract, "本 研究 では 量子 誤り訂正")
        self.assertEqual(pp.lang, "ja")
        self.assertEqual(pp.doi, "10.1/x")            # بلا بادئة doi.org
        self.assertEqual(pp.url, "https://j.example/1.pdf")   # يفضّل المفتوح
        self.assertEqual(pp.authors, ["田中 太郎"])
        self.assertEqual(pp.cited_by, 7)

    def test_openalex_sends_language_filter(self) -> None:
        """الترشيح باللغة هو ما يجعل «أبحاث مختلفة اللغة» ممكناً أصلاً."""
        f = _FakeFetcher({"results": []})
        research.openalex_search(f, "ذكاء", lang="ru")
        self.assertIn("language%3Aru", f.urls[0])

    def test_crossref_strips_jats_markup(self) -> None:
        payload = {"message": {"items": [{
            "title": ["Квантовые вычисления"],
            "abstract": "<jats:p>Аннотация  текста</jats:p>",
            "DOI": "10.5/y", "URL": "https://doi.org/10.5/y",
            "issued": {"date-parts": [[2023, 4]]},
            "author": [{"given": "Иван", "family": "Петров"}],
            "container-title": ["Журнал"], "is-referenced-by-count": 3,
        }]}}
        pp = research.crossref_search(_FakeFetcher(payload), "квант")[0]
        self.assertEqual(pp.abstract, "Аннотация текста")
        self.assertNotIn("<", pp.abstract)
        self.assertEqual(pp.year, 2023)
        self.assertEqual(pp.authors, ["Иван Петров"])

    def test_arxiv_parses_atom(self) -> None:
        xml = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom"><entry>
          <id>http://arxiv.org/abs/2401.001</id>
          <title>Quantum\n  error correction</title>
          <summary>We  study\n  codes.</summary>
          <published>2024-01-02T00:00:00Z</published>
          <author><name>A. Author</name></author>
        </entry></feed>"""
        pp = research.arxiv_search(_FakeFetcher(xml), "quantum")[0]
        self.assertEqual(pp.title, "Quantum error correction")
        self.assertEqual(pp.abstract, "We study codes.")
        self.assertEqual(pp.year, 2024)
        self.assertEqual(pp.venue, "arXiv")

    def test_doaj_parses_bibjson(self) -> None:
        payload = {"results": [{"bibjson": {
            "title": "Computación cuántica", "abstract": "Resumen del artículo",
            "year": "2022", "author": [{"name": "María López"}],
            "journal": {"title": "Revista", "language": ["es"]},
            "link": [{"url": "https://revista.example/1"}],
            "identifier": [{"type": "doi", "id": "10.9/z"}],
        }}]}
        pp = research.doaj_search(_FakeFetcher(payload), "cuántica")[0]
        self.assertEqual(pp.lang, "es")
        self.assertEqual(pp.year, 2022)
        self.assertEqual(pp.doi, "10.9/z")

    def test_dead_provider_returns_empty_not_crash(self) -> None:
        dead = _FakeFetcher(None, raises=True)
        for fn in (research.openalex_search, research.crossref_search,
                   research.arxiv_search, research.doaj_search):
            self.assertEqual(fn(dead, "س"), [], fn.__name__)

    def test_malformed_payloads_do_not_crash(self) -> None:
        # واجهات حقيقية ترجع المفتاح بقيمة null، و dict.get(k, []) لا تحميك
        # من ذلك — ترجع None لا [].
        for payload in ({}, {"results": [{}]}, {"message": {}}, {"results": None},
                        {"message": None}, {"message": {"items": None}},
                        {"results": [{"bibjson": None}]}):
            try:
                research.openalex_search(_FakeFetcher(payload), "س")
                research.crossref_search(_FakeFetcher(payload), "س")
                research.doaj_search(_FakeFetcher(payload), "س")
            except Exception as e:                     # noqa: BLE001
                self.fail(f"انهار على {payload}: {type(e).__name__}: {e}")

    def test_scholarly_text_excludes_display_labels(self) -> None:
        """انحدار: هضم البيانات الوصفية جعل «الباحثون» و«السنة» من أكثر ما يشغله."""
        pp = research.Paper(title="عنوان البحث", abstract="ملخّص البحث",
                            authors=["أحمد"], venue="مجلة", year=2021, doi="10.1/a")
        scholarly = pp.scholarly_text()
        for label in ("الباحثون", "المنشور في", "السنة", "DOI"):
            self.assertNotIn(label, scholarly)
        self.assertIn("عنوان البحث", scholarly)
        self.assertIn("ملخّص البحث", scholarly)

    def test_paper_as_text_carries_metadata(self) -> None:
        pp = research.Paper(title="ع", abstract="ملخّص", authors=["أ", "ب"],
                            venue="مجلة", year=2021, doi="10.1/a")
        text = pp.as_text()
        for piece in ("ع", "ملخّص", "أ، ب", "مجلة", "2021", "10.1/a"):
            self.assertIn(piece, text)

    def test_wiki_api_null_fields_do_not_crash(self) -> None:
        for payload in ({}, {"query": None}, {"query": {"search": None}},
                        {"query": {"pages": None}}):
            self.assertEqual(sources.wiki_search(_FakeFetcher(payload), "ja", "س"), [])
            self.assertEqual(sources.wiki_random(_FakeFetcher(payload), "ja"), [])
            self.assertIsNone(sources.wiki_extract(_FakeFetcher(payload), "ja", "ع"))

    def test_search_dedupes_across_providers(self) -> None:
        same = {"results": [{"display_name": "نفس العنوان",
                             "abstract_inverted_index": {"ن": [0]},
                             "primary_location": {"landing_page_url": "u"}}]}
        found = research.search_papers(_FakeFetcher(same), "س", limit=5,
                                       providers=("openalex", "openalex"))
        self.assertEqual(len(found), 1)


# ── الدوافع ──────────────────────────────────────────────────────────────
class TestDrives(unittest.TestCase):
    def test_learning_peaks_between_the_familiar_and_the_strange(self) -> None:
        """لا المألوف ولا الغريب يعلّمان؛ ما بينهما يعلّم."""
        self.assertAlmostEqual(Drives.learning(0.0, 0.5), 0.0, places=2)
        self.assertAlmostEqual(Drives.learning(1.0, 0.5), 0.0, places=2)
        self.assertGreater(Drives.learning(0.45, 0.5), 0.8)

    def test_openness_shifts_where_he_learns(self) -> None:
        strange = 0.8
        self.assertGreater(Drives.learning(strange, openness=0.9),
                           Drives.learning(strange, openness=0.1))
        familiar = 0.2
        self.assertGreater(Drives.learning(familiar, openness=0.1),
                           Drives.learning(familiar, openness=0.9))

    def test_pure_noise_never_rewards_however_open(self) -> None:
        """«التلفاز المشوّش»: صفحةٌ لا يتّصل منها شيءٌ بما يعرف لا تُعلّمه شيئاً.

        انحدار: قاعدة المنحنى كانت تتجاوز الجِدّة ١٫٠ عند الانفتاح العالي،
        فكان المنفتح (٠٫٩) يأخذ ٠٫٢٠ من كل صفحة ضوضاء محضة — أي إن أهمّ ما
        يميّز معدّل التعلّم عن الجِدّة الصرفة كان ينهار عند أكثر الشخصيات
        فضولاً، وهي أحوجها إلى تلك الحماية.
        """
        for op in (0.0, 0.1, 0.5, 0.6, 0.9, 1.0):
            self.assertEqual(Drives.learning(1.0, op), 0.0, f"انفتاح {op}")
            self.assertEqual(Drives.learning(0.0, op), 0.0, f"انفتاح {op}")

    def test_openness_still_moves_the_peak_after_the_fix(self) -> None:
        """القيد يحرس الطرف ولا يلغي أثر الانفتاح."""
        peaks = []
        for op in (0.1, 0.5, 0.9):
            best = max(range(101), key=lambda i: Drives.learning(i / 100, op)) / 100
            peaks.append(best)
        self.assertEqual(peaks, sorted(peaks))
        self.assertLess(peaks[0], peaks[-1])

    def test_novelty_measure(self) -> None:
        known = {"a", "b"}
        self.assertEqual(Drives.novelty(["a", "b"], known), 0.0)
        self.assertEqual(Drives.novelty(["x", "y"], known), 1.0)
        self.assertEqual(Drives.novelty(["a", "x"], known), 0.5)
        self.assertEqual(Drives.novelty([], known), 0.0)

    def test_familiar_pages_breed_boredom(self) -> None:
        d = Drives()
        for _ in range(6):
            d.observe(novelty=0.02)
        self.assertGreater(d.boredom, 0.6)
        self.assertEqual(d.urge(), "غريب")
        self.assertEqual(d.mood(), "ضجِر")

    def test_strange_pages_breed_confusion_and_send_him_home(self) -> None:
        d = Drives()
        for _ in range(8):
            d.observe(novelty=0.98, openness=0.2)
        self.assertGreater(d.confusion, 0.6)
        self.assertEqual(d.urge(), "مألوف")

    def test_the_open_stay_calm_where_the_guarded_get_lost(self) -> None:
        """الانفتاح ليس رقماً معروضاً: يغيّر ما يحدث له أمام الغريب."""
        guarded, open_ = Drives(), Drives()
        for _ in range(8):
            guarded.observe(novelty=0.95, openness=0.1)
            open_.observe(novelty=0.95, openness=0.9)
        self.assertGreater(guarded.confusion, open_.confusion)

    def test_fatigue_accumulates_then_clears_with_rest(self) -> None:
        d = Drives()
        for _ in range(20):
            d.observe(novelty=0.5)
        self.assertEqual(d.urge(), "عودة")
        d.rest()
        self.assertEqual(d.fatigue, 0.0)
        self.assertNotEqual(d.urge(), "عودة")

    def test_rest_dims_but_does_not_erase(self) -> None:
        d = Drives(boredom=0.9, confusion=0.8)
        d.rest()
        self.assertLess(d.boredom, 0.9)
        self.assertGreater(d.boredom, 0.0)

    def test_questions_create_longing_and_answers_relieve_it(self) -> None:
        d = Drives()
        d.feel_questions(10, persistence=0.9)
        self.assertGreater(d.longing, 0.5)
        self.assertEqual(d.urge(has_questions=True), "سؤال")
        before = d.longing
        d.answered()
        self.assertLess(d.longing, before)

    def test_persistence_changes_how_soon_he_longs(self) -> None:
        patient, restless = Drives(), Drives()
        patient.feel_questions(5, persistence=0.9)
        restless.feel_questions(5, persistence=0.1)
        self.assertGreater(patient.longing, restless.longing)

    def test_urge_priority_tiredness_first(self) -> None:
        """من أنهكه الطريق لا ينفعه سؤالٌ ولا غريب."""
        d = Drives(fatigue=0.95, boredom=1.0, confusion=1.0, longing=1.0)
        self.assertEqual(d.urge(has_questions=True), "عودة")

    def test_state_survives_between_journeys(self) -> None:
        d = Drives(boredom=0.71, confusion=0.33)
        back = Drives.loads(d.dumps())
        self.assertAlmostEqual(back.boredom, 0.71)
        self.assertAlmostEqual(back.confusion, 0.33)

    def test_corrupt_state_falls_back_to_fresh(self) -> None:
        for raw in (None, "", "{", '{"boredom": "كثير"}', "[]"):
            d = Drives.loads(raw)
            self.assertTrue(0.0 <= d.boredom <= 1.0)

    def test_values_never_leave_their_range(self) -> None:
        d = Drives()
        for _ in range(200):
            d.observe(novelty=0.0)
            d.observe(novelty=1.0)
            d.answered()
        for name, value in vars(d).items():
            self.assertTrue(0.0 <= value <= 1.0, f"{name}={value}")


# ── الرغبات ──────────────────────────────────────────────────────────────
class TestDesires(unittest.TestCase):
    def test_obsessions_are_always_wanted(self) -> None:
        p = Personality.default()
        p.obsessions = ["الوعي", "الزمن"]
        p.aspiration = ""
        self.assertEqual(sorted(p.wants()), ["الزمن", "الوعي"])

    def test_aversion_blocks_a_topic_everywhere(self) -> None:
        p = Personality.default()
        p.aversions = ["السياسة"]
        p.obsessions = ["السياسة الدولية", "الفلك"]
        p.aspiration = "تاريخ السياسة"       # الطموح رغبة، فينطبق عليه النفور
        self.assertTrue(p.repels("أخبار السياسة"))
        self.assertEqual(p.wants(), ["الفلك"])
        self.assertTrue(p.is_blocked("x.com", "تحليل السياسة اليوم"))

    def test_persistence_sets_how_long_he_chases(self) -> None:
        p = Personality.default()
        p.persistence = 1.0
        stubborn = p.max_question_attempts
        p.persistence = 0.0
        self.assertGreater(stubborn, p.max_question_attempts)


# ── الاستبصار عبر اللغات ─────────────────────────────────────────────────
class TestInsight(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.body = Body(Path(self.tmp.name) / "b.db")
        sources.ensure_lexicon(self.body.conn)

    def tearDown(self) -> None:
        self.body.close()
        self.tmp.cleanup()

    def _learn(self, concept: str, pairs: dict) -> None:
        for lg, dst in pairs.items():
            self.body.conn.execute(
                """INSERT OR REPLACE INTO lexicon
                   (term, src_lang, dst_lang, dst_term, learned_at)
                   VALUES(?,?,?,?,0)""", (concept, "ar", lg, dst))
        self.body.conn.commit()

    def _fill(self, lang_: str, n: int, title: str = "عام") -> None:
        for i in range(n):
            self.body.remember(title=f"{title} {lang_}{i}", summary="نص",
                               lang=lang_, keywords=["عام"])

    def test_coverage_matches_each_world_by_its_own_word(self) -> None:
        self._learn("شيخوخة السكان",
                    {"ja": "人口高齢化", "zh": "人口老龄化", "ar": "شيخوخة السكان"})
        self.body.remember(title="人口高齢化と地方経済", summary="分析",
                           lang="ja", keywords=["人口高齢化"])
        self.body.remember(title="人口老龄化与养老金", summary="研究",
                           lang="zh", keywords=["人口老龄化"])
        cov = insight.coverage(self.body, "شيخوخة السكان", ["ja", "zh", "ar"])
        self.assertEqual(cov.views["ja"].count, 1)
        self.assertEqual(cov.views["zh"].count, 1)
        self.assertEqual(cov.views["ar"].count, 0)
        self.assertEqual(sorted(cov.covering), ["ja", "zh"])

    def test_a_language_he_barely_visited_is_not_a_finding(self) -> None:
        """«لا تغطية بالكورية» خبرٌ عن العالم فقط إن كان زار الكورية.
        وإلا فهو خبرٌ عن كسله هو، ولا يجوز عرضه كفجوة."""
        self._learn("موضوع", {"ja": "話題", "ko": "주제", "ar": "موضوع"})
        self.body.remember(title="話題の記事", summary="s", lang="ja",
                           keywords=["話題"])
        self._fill("ja", insight.MIN_PRESENCE)
        self._fill("ar", insight.MIN_PRESENCE)      # زار العربية كثيراً
        self.body.remember(title="واحدة", summary="s", lang="ko")  # والكورية مرّة

        cov = insight.coverage(self.body, "موضوع", ["ja", "ko", "ar"])
        self.assertIn("ar", cov.real_gaps)          # زارها ولم يجد ⇒ فجوة
        self.assertNotIn("ko", cov.real_gaps)       # لم يزرها ⇒ ليست فجوة
        self.assertIn("ko", cov.unexplored)

    def test_a_concept_with_no_equivalent_is_its_own_news(self) -> None:
        self._learn("مفهوم", {"ja": "概念", "ru": None, "ar": "مفهوم"})
        cov = insight.coverage(self.body, "مفهوم", ["ja", "ru", "ar"])
        self.assertIn("ru", cov.untranslatable)
        self.assertNotIn("ru", cov.real_gaps)       # لا يُحسب فجوةً تغطية

    def test_gaps_rank_the_widest_first(self) -> None:
        for lg in ("ja", "zh", "ko", "de", "ar", "en"):
            self._fill(lg, insight.MIN_PRESENCE)
        self._learn("واسع", {lg: f"w-{lg}" for lg in
                             ("ja", "zh", "ko", "de", "ar", "en")})
        self._learn("ضيّق", {lg: f"n-{lg}" for lg in ("ja", "ar", "en")})
        for lg in ("ja", "zh", "ko", "de"):
            self.body.remember(title=f"w-{lg} مقال", summary="s", lang=lg,
                               keywords=[f"w-{lg}"])
        self.body.remember(title="n-ja مقال", summary="s", lang="ja",
                           keywords=["n-ja"])

        found = insight.gaps(self.body, ["ja", "zh", "ko", "de", "ar", "en"])
        self.assertTrue(found)
        self.assertEqual(found[0].concept, "واسع")
        self.assertEqual(sorted(found[0].missing), ["ar", "en"])

    def test_no_lexicon_means_no_invented_gaps(self) -> None:
        """أوّل رحلاته: معجمه فارغ. لا نصطنع فجوات لا دليل عليها."""
        self._fill("ja", 20)
        self._fill("ar", 20)
        self.assertEqual(insight.concepts_of(self.body), [])
        self.assertEqual(insight.gaps(self.body, ["ja", "ar"]), [])

    def test_render_separates_what_he_knows_from_what_he_missed(self) -> None:
        self._learn("موضوع", {"ja": "話題", "ar": "موضوع", "ko": "주제"})
        self.body.remember(title="話題", summary="s", lang="ja", keywords=["話題"])
        self._fill("ar", insight.MIN_PRESENCE)
        text = insight.render_coverage(
            insight.coverage(self.body, "موضوع", ["ja", "ar", "ko"]))
        self.assertIn("●", text)
        self.assertIn("لم يزرهم بما يكفي", text)

    def test_no_model_means_no_invented_comparison(self) -> None:
        """بلا نموذج لغوي نعرض الجداول ولا نؤلّف مقارنةً لا نملك أدلّتها."""
        from rooh.mind import Mind

        self._learn("موضوع", {"ja": "話題", "zh": "话题"})
        cov = insight.coverage(self.body, "موضوع", ["ja", "zh"])
        self.assertIsNone(insight.synthesize(Mind(Personality.default(),
                                                  use_llm=False), cov))


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
        p.research_bias = 0.0        # الأبحاث لها اختبارها الخاص
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
            p.research_bias = 0.0
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

    def test_papers_enter_the_body_as_papers(self) -> None:
        """الورقة تُحفظ نوعاً مستقلاً، ومحتواها يأتي مع نتيجة البحث بلا جلب."""
        from unittest.mock import patch

        made = [
            research.Paper(
                title=f"量子誤り訂正の研究 {i}", lang="ja", year=2024,
                abstract="本研究では量子誤り訂正符号の新しい構成法を提案する。"
                         "従来手法と比較して誤り率が大幅に低減されることを示す。"
                         "数値実験により提案手法の有効性を確認した。",
                authors=["田中 太郎"], venue="日本物理学会", doi=f"10.1/{i}",
                url=f"https://j.example/{i}", provider="openalex", cited_by=i)
            for i in range(1, 6)
        ]
        with LocalNet() as base:
            w = self._wanderer(base)
            w.p.research_bias = 1.0            # أوراق فقط
            w.p.seed_interests = ["الحوسبة الكمية"]
            with patch.object(research, "search_papers", return_value=made):
                rep = w.journey(pages=3, only_lang="ja")

        self.assertEqual(rep.stored, 3)
        rows = self.body.conn.execute(
            "SELECT title, kind, lang, source_url, body FROM memories").fetchall()
        self.assertEqual(len(rows), 3)
        for r in rows:
            self.assertEqual(r["kind"], "paper")
            self.assertEqual(r["lang"], "ja")
            self.assertTrue(r["source_url"].startswith("https://j.example/"))
            self.assertIn("日本物理学会", r["body"])     # البيانات الوصفية محفوظة
            self.assertIn("DOI:", r["body"])
        self.assertEqual(self.body.stats()["papers"], 3)

    def test_paper_keywords_are_topics_not_labels(self) -> None:
        """ما يدخل خريطة فضوله من الورقة موضوعُها، لا تسمياتي الوصفية."""
        from unittest.mock import patch

        made = [research.Paper(
            title="Aprendizaje profundo en agricultura andina", lang="es",
            abstract="Este artículo presenta un modelo de visión por computadora "
                     "para detectar plagas en cultivos de papa en los Andes. "
                     "El modelo alcanza una precisión del noventa por ciento.",
            authors=["María López"], venue="Revista", year=2023, doi="10.9/z",
            url="https://es.example/1", provider="doaj")]
        with LocalNet() as base:
            w = self._wanderer(base)
            w.p.research_bias = 1.0
            w.p.seed_interests = ["الذكاء الاصطناعي"]
            with patch.object(research, "search_papers", return_value=made):
                w.journey(pages=1, only_lang="es")

        terms = [t for t, _lg, _w in self.body.top_interests(20)]
        for label in ("الباحثون", "المنشور", "السنة", "doi"):
            self.assertNotIn(label, terms, f"تسرّبت «{label}» إلى فضوله: {terms}")
        self.assertTrue(any(t in ("aprendizaje", "agricultura", "modelo", "andes",
                                  "profundo", "artículo", "computadora", "cultivos",
                                  "precisión", "plagas", "visión", "presenta")
                            for t in terms), terms)
        # والبيانات الوصفية باقية في الجسد للعرض
        row = self.body.conn.execute("SELECT body FROM memories").fetchone()
        self.assertIn("María López", row["body"])
        self.assertIn("DOI:", row["body"])

    def test_paper_without_abstract_is_skipped(self) -> None:
        """ورقة بعنوان بلا ملخّص ليست معرفة — لا تدخل الجسد."""
        from unittest.mock import patch

        empty = [research.Paper(title="عنوان بلا ملخّص", abstract="", lang="ja",
                                url="https://j.example/x", provider="openalex")]
        with LocalNet() as base:
            w = self._wanderer(base)
            w.p.research_bias = 1.0
            w.p.seed_interests = ["س"]
            with patch.object(research, "search_papers", return_value=empty):
                rep = w.journey(pages=2, only_lang="ja")
        self.assertEqual(self.body.stats()["papers"], 0)
        self.assertGreaterEqual(rep.visited, 1)

    def test_unreachable_research_is_asked_once_per_language(self) -> None:
        """قاعدة لا تجيب: نسألها مرّة، لا في كل محاولة، وإلا نفدت الرحلة انتظاراً."""
        from unittest.mock import patch

        with LocalNet() as base:
            w = self._wanderer(base)
            w.p.research_bias = 1.0
            w.p.seed_interests = ["س"]
            with patch.object(research, "search_papers", return_value=[]) as stub:
                w.journey(pages=3, only_lang="ru")
            self.assertEqual(stub.call_count, 1, "سُئلت القاعدة أكثر من مرّة")

    def test_repetition_actually_bores_him(self) -> None:
        """انحدار: كان يسجّل ٦ مفاتيح ويقيس الجِدّة على ١٢، فتجمّدت على
        ٠٫٥ إلى الأبد وصار الملل مستحيلاً بنيوياً."""
        with LocalNet() as base:
            first = self._wanderer(base)
            first.journey(pages=4)
            self.assertLess(first.drives.boredom, 0.75)
            for _ in range(3):
                w = self._wanderer(base)
                w.journey(pages=4)
        self.assertGreater(w.drives.boredom, 0.75, "قرأ نفسه مراراً ولم يملّ")
        self.assertEqual(w.drives.mood(), "ضجِر")

    def test_boredom_changes_where_he_goes(self) -> None:
        """المزاج ليس زينة: الضجر يبدّل الوجهة فعلاً."""
        with LocalNet() as base:
            for _ in range(4):
                w = self._wanderer(base)
                rep = w.journey(pages=4)
        self.assertIn("غريب", rep.urges)

    def test_mood_is_derived_not_drawn_by_lot(self) -> None:
        with LocalNet() as base:
            w = self._wanderer(base)
            w.drives.confusion = 0.9
            rep = w.journey(pages=1)
        self.assertEqual(rep.mood, w.drives.mood())

    def test_exhaustion_ends_the_journey_early(self) -> None:
        """التعب يتراكم داخل الرحلة نفسها — ينام قبلها فيبدأ صافياً."""
        with LocalNet() as base:
            w = self._wanderer(base)
            w.drives.fatigue = 0.95
            rep = w.journey(pages=1)
            self.assertFalse(rep.came_home_early, "لم ينم قبل أن يخرج")

            long_walk = self._wanderer(base)
            rep = long_walk.journey(pages=30)    # أطول ممّا يحتمل
        self.assertTrue(rep.came_home_early)
        self.assertLess(rep.stored, 30)
        self.assertGreater(long_walk.drives.fatigue, 0.8)

    def test_drives_persist_across_journeys(self) -> None:
        with LocalNet() as base:
            first = self._wanderer(base)
            first.journey(pages=3)
            saved = first.drives.boredom
            second = self._wanderer(base)
        # الرحلة الجديدة تبدأ من حيث انتهت السابقة (بعد راحة تخفّف لا تمحو)
        self.assertGreater(second.drives.boredom, 0.0)
        self.assertLessEqual(second.drives.boredom, saved + 0.01)

    def test_he_opens_questions_about_what_he_did_not_know(self) -> None:
        with LocalNet() as base:
            w = self._wanderer(base)
            rep = w.journey(pages=3)
        self.assertTrue(rep.asked, "قرأ ثلاث صفحات ولم يستوقفه شيء")
        # والصينية تُسأل كغيرها: «量子» مصطلحٌ لا شظيّة
        self.assertTrue(all(len(t) >= 2 for t in rep.asked))
        # كل ما سأله مسجّل، سواء بقي مفتوحاً أم أجابته صفحة تالية
        total = self.body.conn.execute(
            "SELECT COUNT(*) c FROM questions").fetchone()["c"]
        self.assertGreaterEqual(total, len(rep.asked))

    def test_a_passing_mention_is_not_an_answer(self) -> None:
        """السؤال لا يُغلق بورود المصطلح، بل بأن تكون الصفحة عنه."""
        self.body.ask("كلمة نادرة", "ar")
        mid = self.body.remember(title="ذكرى", summary="s", lang="ar")
        marginal = ["أول", "ثاني", "ثالث", "رابع", "خامس", "سادس", "كلمة نادرة"]
        self.assertEqual(self.body.resolve_by_keywords(marginal, "ar", mid), [])
        self.assertEqual(self.body.count_open_questions(), 1)
        central = ["كلمة نادرة", "أول", "ثاني"]
        self.assertEqual(self.body.resolve_by_keywords(central, "ar", mid),
                         ["كلمة نادرة"])
        self.assertEqual(self.body.count_open_questions(), 0)

    def test_he_returns_to_chase_yesterdays_question(self) -> None:
        """ما يصل رحلةً برحلة: يخرج اليوم ليكمل ما بدأه أمس."""
        from unittest.mock import patch

        self.body.ask("量子暗号", "ja")
        self.body.ask("сверхпроводник", "ru")
        with LocalNet() as base:
            w = self._wanderer(base)
            w.p.persistence = 1.0
            chased: list[str] = []
            w.on_event = lambda k, d: chased.append(d["term"]) if k == "chasing" else None
            # لا نخرج إلى الشبكة في الاختبار: قواعد الأبحاث مُحاكاة
            with patch.object(research, "search_papers", return_value=[]):
                w.journey(pages=2)
        self.assertTrue(chased, "لم يلتفت إلى سؤاله المعلّق")
        attempts = self.body.conn.execute(
            "SELECT SUM(attempts) s FROM questions").fetchone()["s"]
        self.assertGreater(attempts or 0, 0)

    def test_questions_get_closed_when_he_reads_about_them(self) -> None:
        with LocalNet() as base:
            w = self._wanderer(base)
            w.journey(pages=3)
            self.assertTrue(self.body.count_open_questions())
            w2 = self._wanderer(base)
            rep = w2.journey(pages=5)
        answered = self.body.conn.execute(
            "SELECT COUNT(*) c FROM questions WHERE status='answered'").fetchone()["c"]
        self.assertGreater(answered, 0)

    def test_a_question_chased_too_often_is_let_go(self) -> None:
        """الإصرار الأعمى ليس مثابرة."""
        self.body.ask("مصطلح لا يوجد", "ja")
        qid = self.body.open_questions()[0][0]
        for _ in range(9):
            self.body.note_attempt(qid)
        self.body.conn.commit()
        with LocalNet() as base:
            w = self._wanderer(base)
            w.p.persistence = 0.5
            w.journey(pages=1)
        row = self.body.conn.execute(
            "SELECT status FROM questions WHERE id=?", (qid,)).fetchone()
        self.assertEqual(row["status"], "abandoned")

    def test_obsessions_survive_forgetting(self) -> None:
        """الهاجس لا يُنسى بالخفوت — هذا معنى أن يكون هاجساً."""
        with LocalNet() as base:
            w = self._wanderer(base)
            w.p.obsessions = ["الوعي"]
            w.journey(pages=2)
            for _ in range(60):
                self.body.decay_interests(factor=0.9)
            w2 = self._wanderer(base)
            w2.p.obsessions = ["الوعي"]
            w2.journey(pages=2)
        terms = [t for t, _lg, _w in self.body.top_interests(50)]
        self.assertIn("الوعي", terms)

    def test_aversions_never_become_questions(self) -> None:
        with LocalNet() as base:
            w = self._wanderer(base)
            w.p.aversions = ["量子", "Квантовые", "الكمية", "量子計算"]
            rep = w.journey(pages=3)
        for term in rep.asked:
            self.assertFalse(w.p.repels(term), term)

    def test_service_makes_him_go_fill_your_gaps(self) -> None:
        """نزوع «الفجوة»: تجواله الحرّ يُسخَّر لما تصمت عنه لغتك."""
        sources.ensure_lexicon(self.body.conn)
        for lg, dst in (("zh", "量子计算"), ("ja", "量子計算"),
                        ("ar", "الحوسبة الكمية"), ("ru", None)):
            self.body.conn.execute(
                """INSERT OR REPLACE INTO lexicon
                   (term, src_lang, dst_lang, dst_term, learned_at)
                   VALUES('الحوسبة الكمية','ar',?,?,0)""", (lg, dst))
        for lg in ("zh", "ja", "ar"):
            for i in range(insight.MIN_PRESENCE + 1):
                self.body.remember(title=f"حشو {lg}{i}", summary="s", lang=lg)
        self.body.remember(title="量子计算 المقال", summary="s", lang="zh",
                           keywords=["量子计算"])
        self.body.conn.commit()

        with LocalNet() as base:
            w = self._wanderer(base)
            w.p.service_bias = 1.0       # كل تجواله الحرّ لك
            filling: list[dict] = []
            w.on_event = lambda k, d: filling.append(d) if k == "filling" else None
            w.journey(pages=2)

        self.assertTrue(w._gaps or filling, "لم يرَ الفجوة أصلاً")
        if filling:
            self.assertEqual(filling[0]["concept"], "الحوسبة الكمية")
            self.assertIn(filling[0]["lang"], ("ja", "ar"))

    def test_service_never_overrides_his_own_needs(self) -> None:
        """الخدمة تملأ تجواله الحرّ، ولا تزاحم تعبه ولا حيرته ولا سؤاله."""
        with LocalNet() as base:
            w = self._wanderer(base)
            w.p.service_bias = 1.0
            w.drives.confusion = 0.9      # حائر
            rep = w.journey(pages=2)
        self.assertNotIn("فجوة", rep.urges)
        self.assertIn("مألوف", rep.urges)

    def test_blocked_host_is_respected(self) -> None:
        with LocalNet() as base:
            w = self._wanderer(base, blocked_hosts=["127.0.0.1"])
            rep = w.journey(pages=2)
        self.assertEqual(rep.stored, 0)
        self.assertEqual(self.body.stats()["memories"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
