"""الواجهة — كيف تكلّمه أنت."""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Optional

from . import config, insight, languages, notify, research, sources, trends
from .body import Body
from .drives import MODES, Drives
from .mind import LLM, Mind, describe_backend
from .net import FetchError, Fetcher
from .personality import DEFAULT_PERSONALITY, Personality
from .wanderer import Wanderer


def _when(ts: Optional[float]) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "—"


def _human_bytes(n: int) -> str:
    for unit in ("ب", "ك.ب", "م.ب", "غ.ب"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} ت.ب"


# ── الأوامر ──────────────────────────────────────────────────────────────
def cmd_init(args: argparse.Namespace) -> int:
    home = config.ensure_home()
    p_path = config.personality_path()
    if p_path.exists() and not args.force:
        print(f"موجود مسبقاً: {p_path}\nاستعمل --force لإعادة التهيئة.")
    else:
        Personality.default().save(p_path)
        print(f"كُتبت الشخصية: {p_path}")
    s_path = config.sources_path()
    if not s_path.exists() or args.force:
        sources.save_sources(s_path, sources.DEFAULT_SOURCES)
        print(f"كُتبت المصادر: {s_path}")
    with Body() as b:
        st = b.stats()
    print(f"الجسد جاهز: {st['db']}")
    print(f"\nالبيت: {home}\nالخطوة التالية:  rooh wander -n 5")
    return 0


def cmd_who(args: argparse.Namespace) -> int:
    p = Personality.load()
    if args.json:
        from dataclasses import asdict

        print(json.dumps(asdict(p), ensure_ascii=False, indent=2))
        return 0
    print(p.describe())
    with Body() as b:
        st = b.stats()
    print(f"\nوُلد: {_when(st['born_at'])}")
    print(f"في جسده: {st['memories']} ذكرى من {st['pages']} صفحة، "
          f"عبر {st['journeys']} رحلة")
    if st["by_lang"]:
        top = "، ".join(f"{k}:{v}" for k, v in list(st["by_lang"].items())[:6])
        print(f"لغات ذاكرته: {top}")
    with Body() as b:
        d = Drives.loads(b.load_drives())
        open_q = b.count_open_questions()
    print(f"حاله الآن: {d.mood()} — يريد أن {d.urge(open_q > 0)}")
    print(describe_backend(Mind(p, use_llm=not args.no_llm)))
    return 0


def cmd_wander(args: argparse.Namespace) -> int:
    p = Personality.load()
    mind = Mind(p, use_llm=not args.no_llm)
    quiet = args.quiet
    mode = args.mode

    def on_event(kind: str, data: dict) -> None:
        if quiet:
            return
        if kind == "wake":
            print(f"⟶ يخرج وهو {data['mood']} (يريد أن {data.get('urge','يتجوّل')}) "
                  f"— يبحث عن: {'، '.join(data['seeds'][:4])}")
        elif kind == "chasing":
            print(f"   ⟳ يلاحق سؤاله: «{data['term']}»")
        elif kind == "asked":
            print(f"   ؟ مرّ به ما لا يعرفه: «{data['term']}»")
        elif kind == "answered":
            print(f"   ✔ أغلق سؤاله: «{data['term']}»")
        elif kind == "tired":
            print(f"   … أنهكه الطريق، يعود بـ{data['stored']} من {data['of']}")
        elif kind == "translate":
            print(f"   ↯ «{data['from']}» تُقال «{data['to']}» بـ{data['lang']}")
        elif kind == "visit":
            print(f"   · [{data['lang']}] {data['source']}")
        elif kind == "kept":
            print(f"   ✓ [{data['lang']}] {data['title'][:70]} "
                  f"(وزن {data['importance']})")
        elif kind == "learned" and data["gain"] > 0.6:
            print(f"     ↳ تعلّم منها ({data['gain']:.2f}) — صار {data['mood']}")
        elif kind == "fail":
            print(f"   ✗ {data['why']}", file=sys.stderr)
        elif kind == "home":
            print(f"⟵ عاد ومعه {data['stored']} من {data['visited']}")

    with Body() as body:
        if mode:
            body.set_meta("mode", mode)
        w = Wanderer(body, p, mind, on_event=on_event,
                     mode=mode or body.get_meta("mode", "كامل"))
        try:
            rep = w.journey(pages=args.pages, only_lang=args.lang)
        except KeyboardInterrupt:
            print("\nقُطعت الرحلة. ما حُفظ حتى الآن باقٍ في الجسد.")
            return 130
        except Exception as e:                    # رحلةٌ سقطت: نسجّل ولا نبتلع
            _record_health(body, ok=False, why=f"{type(e).__name__}: {e}")
            raise
        # صحّته تُقاس بما عاد به لا بأنه خرج: رحلةٌ بلا صيدٍ إخفاق.
        _record_health(body, ok=rep.stored > 0,
                       why="" if rep.stored else "عاد بلا شيء")
    print("\n" + "─" * 50)
    print(rep.journal)
    print("─" * 50)
    print(f"({rep.duration:.0f} ثانية • يوميّاته في {config.journal_dir()})")
    return 0


def cmd_live(args: argparse.Namespace) -> int:
    """يظلّ يخرج ويعود، إلى أن توقفه."""
    every = args.every * 60
    print(f"يعيش الآن: رحلة كل {args.every} دقيقة. Ctrl-C ليتوقّف.\n")
    n = 0
    while True:
        n += 1
        print(f"╭─ رحلة #{n} — {_when(time.time())}")
        try:
            cmd_wander(args)
        except KeyboardInterrupt:
            print("\nنام.")
            return 0
        except Exception as e:                 # رحلة تفشل لا تقتل الحياة
            print(f"تعثّر: {type(e).__name__}: {e}", file=sys.stderr)
        if args.times and n >= args.times:
            return 0
        try:
            print(f"╰─ ينام {args.every} دقيقة…\n")
            time.sleep(every)
        except KeyboardInterrupt:
            print("\nنام.")
            return 0


def cmd_recall(args: argparse.Namespace) -> int:
    with Body() as b:
        found = b.recall(args.query, limit=args.limit)
    if not found:
        print("لا يذكر شيئاً عن هذا.")
        return 1
    for m in found:
        print(f"\n[{m.lang}] {m.title}   ({_when(m.created_at)}، وزن {m.importance})")
        if m.summary:
            print(f"  {m.summary}")
        if m.keywords:
            print(f"  مفاتيح: {'، '.join(m.keywords[:8])}")
        if m.source_url:
            print(f"  ← {m.source_url}")
        if args.echoes:
            with Body() as b:
                for _mid, title, lg, n in insight.echoes(b, m.keywords, m.lang, m.id):
                    print(f"    ↔ [{lg}] {title[:60]}  ({n} مفاتيح مشتركة)")
    return 0


def cmd_recent(args: argparse.Namespace) -> int:
    with Body() as b:
        for m in b.recent(limit=args.limit, lang=args.lang):
            print(f"[{m.lang}] {_when(m.created_at)}  {m.title[:70]}")
    return 0


def cmd_interests(args: argparse.Namespace) -> int:
    with Body() as b:
        rows = b.top_interests(limit=args.limit, lang=args.lang)
    if not rows:
        print("فضوله فارغ بعد — أرسله في رحلة.")
        return 1
    width = max(len(t) for t, _, _ in rows)
    for term, lg, weight in rows:
        bar = "█" * max(1, int(weight * 6))
        print(f"{term:<{width}}  [{lg}]  {bar} {weight:.2f}")
    return 0


def cmd_journal(args: argparse.Namespace) -> int:
    with Body() as b:
        entries = b.read_journal(limit=args.limit)
    if not entries:
        print("لم يكتب شيئاً بعد.")
        return 1
    for ts, entry in entries:
        print(f"\n── {_when(ts)} " + "─" * 30)
        print(entry)
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    """تضع أنت شيئاً في ذاكرته مباشرة، بلا إنترنت."""
    text = " ".join(args.text)
    with Body() as b:
        mid = b.remember(title=args.title or text[:60], summary=text, body=text,
                         lang=args.lang, kind="note", importance=0.8)
    print(f"حُفظت في جسده (#{mid}).")
    return 0


def cmd_papers(args: argparse.Namespace) -> int:
    """بحث مباشر في قواعد الأبحاث المفتوحة، بأي لغة."""
    p = Personality.load()
    f = Fetcher(respect_robots=True)
    query = " ".join(args.query)
    lg = args.lang or ""

    # يسأل بلسان أهل اللغة لا بلسانك، تماماً كما يفعل وهو يتجوّل
    if lg and lg != "ar":
        with Body() as b:
            term = sources.translate_term(f, b.conn, query, "ar", lg)
        if term and term != query:
            print(f"«{query}» تُقال «{term}» بـ{languages.arabic_name(lg)}\n")
            query = term

    providers = tuple(args.source) if args.source else research.PROVIDERS
    found = research.search_papers(f, query, lang=lg, limit=args.limit,
                                   providers=providers)
    if not found:
        print("لا شيء. جرّب لغة أخرى أو مصطلحاً أعمّ.")
        return 1

    for pp in found:
        head = f"[{pp.lang or '؟'}] {pp.title}"
        print(f"\n{head}")
        meta = [x for x in (str(pp.year) if pp.year else "", pp.venue,
                            f"استُشهد به {pp.cited_by}" if pp.cited_by else "") if x]
        if meta:
            print("  " + " • ".join(meta))
        if pp.authors:
            print(f"  {'، '.join(a for a in pp.authors[:4] if a)}")
        if pp.abstract:
            print(f"  {pp.abstract[:280]}{'…' if len(pp.abstract) > 280 else ''}")
        print(f"  ← {pp.url or ('doi:' + pp.doi)}   [{pp.provider}]")

    if args.save:
        mind = Mind(p, use_llm=not args.no_llm)
        with Body() as b:
            kept = 0
            for pp in found:
                url = pp.url or f"doi:{pp.doi}"
                if b.has_seen(url):
                    continue
                text = pp.as_text()
                page_id = b.store_page(journey_id=None, url=url, host=pp.provider,
                                       lang=pp.lang or lg or "en",
                                       source=pp.provider, title=pp.title, text=text)
                if page_id is None:
                    continue
                d = mind.digest(pp.title, text, pp.lang or lg or "en")
                b.remember(title=pp.title, summary=d["summary"], body=text[:4000],
                           lang=pp.lang or lg or "en", kind="paper",
                           keywords=d["keywords"], source_url=url,
                           importance=max(0.6, d["importance"]), page_id=page_id)
                kept += 1
        print(f"\nحُفظت {kept} ورقة في جسده.")
    return 0


def cmd_langs(args: argparse.Namespace) -> int:
    """اللغات التي يعرف كيف يتجوّل فيها، وكيف توزّع وقته بينها."""
    p = Personality.load()

    if args.profile:
        weights = languages.profile(args.profile)
        known = languages.profile("العالم")
        if args.profile not in ("العالم", "world", "all", "متوازن") \
                and args.profile not in languages.REGIONS:
            print(f"لا أعرف توزيعاً باسم «{args.profile}».")
            print(f"المتاح: متوازن، العالم، {'، '.join(languages.REGIONS)}")
            return 1
        p.languages = weights
        p.language_profile = args.profile
        p.save()
        print(f"صار يتجوّل في {len(weights)} لغة ({args.profile}):")
        print("  " + languages.describe(list(weights)[:12]))
        if len(weights) > 12:
            print(f"  …و{len(weights) - 12} أخرى")
        return 0

    if args.all:
        for region in languages.REGIONS:
            codes = languages.codes_in(region)
            print(f"\n{region} ({len(codes)}):")
            for c in codes:
                mark = "●" if c in p.languages else "○"
                print(f"  {mark} {c:<4} {languages.arabic_name(c):<16}"
                      f" {languages.native_name(c)}")
        print(f"\n● = يزورها الآن ({len(p.languages)} من {len(languages.LANGUAGES)})")
        return 0

    print(f"توزيعه الحالي: {p.language_profile} — {len(p.languages)} لغة\n")
    for code, w in sorted(p.languages.items(), key=lambda kv: -kv[1])[:args.limit]:
        bar = "█" * max(1, int(w * 120))
        print(f"  {code:<4} {languages.arabic_name(code):<16} {bar} {w:.3f}")
    print(f"\nكل اللغات: rooh langs --all")
    print(f"غيّر التوزيع: rooh langs --profile العالم")
    print(f"المتاح: متوازن، العالم، {'، '.join(languages.REGIONS)}")
    return 0


def cmd_drives(args: argparse.Namespace) -> int:
    """حالته الداخلية الآن: ما الذي يدفعه، وماذا يريد."""
    p = Personality.load()
    with Body() as b:
        d = Drives.loads(b.load_drives())
        open_q = b.count_open_questions()
    print(d.describe())
    urge = d.urge(open_q > 0)
    meaning = {
        "عودة": "أنهكه الطريق — يريد أن يرتاح",
        "مألوف": "جمع غريباً أكثر مما يستطيع ربطه — يريد أرضاً يعرفها",
        "سؤال": "عنده سؤال معلّق — يريد أن يغلقه",
        "غريب": "مَلَّ ممّا يعرف — يريد لساناً لم يزره",
        "تجوّل": "لا شيء يشدّه بعينه — يتمشّى",
    }
    print(f"\nمزاجه : {d.mood()}")
    print(f"يريد  : {urge} — {meaning.get(urge, '')}")
    print(f"أسئلته المفتوحة: {open_q}")
    if p.obsessions:
        print(f"وهواجسه الثابتة: {'، '.join(p.obsessions)}")
    if p.aspiration:
        print(f"وتحت ذلك كله: {p.aspiration}")
    return 0


def cmd_questions(args: argparse.Namespace) -> int:
    """ما مرّ به ولم يعرفه — وما أغلقه أخيراً."""
    with Body() as b:
        if args.answered:
            rows = b.conn.execute(
                """SELECT q.term, q.lang, q.answered_at, m.title, m.source_url
                   FROM questions q LEFT JOIN memories m ON m.id = q.answer
                   WHERE q.status='answered'
                   ORDER BY q.answered_at DESC LIMIT ?""", (args.limit,)).fetchall()
            if not rows:
                print("لم يغلق سؤالاً بعد.")
                return 1
            for r in rows:
                print(f"\n✓ [{r['lang']}] {r['term']}   ({_when(r['answered_at'])})")
                if r["title"]:
                    print(f"    أجابه: {r['title'][:70]}")
                    if r["source_url"]:
                        print(f"    ← {r['source_url']}")
            return 0

        rows = b.conn.execute(
            """SELECT term, lang, asked_at, attempts, context FROM questions
               WHERE status='open' ORDER BY attempts ASC, asked_at ASC LIMIT ?""",
            (args.limit,)).fetchall()
        if not rows:
            print("لا سؤال معلّقاً عنده الآن.")
            return 1
        for r in rows:
            chased = f"طاردَه {r['attempts']} مرّة" if r["attempts"] else "لم يطارده بعد"
            print(f"\n؟ [{r['lang']}] {r['term']}   ({chased})")
            if r["context"]:
                print(f"    صادفه في: {r['context'][:70]}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """كيف يرى كل عالَمٍ لغويٍّ هذا الموضوع — وبماذا ينفرد كلٌّ منهم."""
    p = Personality.load()
    concept = " ".join(args.term)
    langs = args.lang or sorted(p.languages, key=p.languages.get, reverse=True)[:10]
    f = Fetcher(respect_robots=True) if args.learn else None

    with Body() as b:
        cov = insight.coverage(b, concept, langs, fetcher=f, learn=args.learn)
        print(insight.render_coverage(cov))

        if not cov.covering:
            print(f"\nلم يجمع شيئاً عن «{concept}» بعد.")
            print("أرسله في رحلة أولاً:  rooh wander -n 10")
            return 1

        gaps_found = cov.real_gaps
        if gaps_found:
            names = "، ".join(languages.arabic_name(l) for l in gaps_found)
            print(f"\n★ فجوة: يكتب عنه {len(cov.covering)} عالَماً، "
                  f"ويصمت عنه: {names}")

        mind = Mind(p, use_llm=not args.no_llm)
        told = insight.synthesize(mind, cov)
        if told:
            print("\n" + "─" * 54)
            print(told)
        elif not args.no_llm:
            print("\n(المقارنة بالنص تحتاج نموذجاً لغوياً — "
                  "pip install anthropic)")
    return 0


def cmd_gaps(args: argparse.Namespace) -> int:
    """مواضيع يكتب عنها بعض العالم وتصمت عنها لغتك."""
    p = Personality.load()
    langs = sorted(p.languages, key=p.languages.get, reverse=True)[:12]
    f = Fetcher(respect_robots=True) if args.learn else None

    with Body() as b:
        found = insight.gaps(b, langs, limit=args.limit, fetcher=f,
                             learn=args.learn)
        concepts = len(insight.concepts_of(b, limit=100))

    if not found:
        print("لا فجوات يعرفها بعد.")
        if concepts < 3:
            print(f"معجمه ما زال صغيراً ({concepts} مفهوماً). الفجوة تحتاج "
                  "مفهوماً يعرف مقابله بأكثر من لسان —")
            print("أرسله في رحلات أكثر:  rooh live --every 60")
        return 1

    for g in found:
        cover = "، ".join(languages.arabic_name(l) for l in g.covering)
        miss = "، ".join(languages.arabic_name(l) for l in g.missing)
        print(f"\n★ {g.concept}")
        print(f"   يكتب عنه : {cover}")
        print(f"   ويصمت عنه: {miss}")
        for lg, title in g.sample:
            print(f"      [{lg}] {title[:66]}")
    print(f"\nليقرأ عنها في اللغات الصامتة: rooh wander -n 10")
    return 0


def cmd_brief(args: argparse.Namespace) -> int:
    """خلاصةُ ما جدّ منذ آخر مرّة سألت. هذا ما يعطيكه ولا يعطيكه غيره."""
    p = Personality.load()
    langs = sorted(p.languages, key=p.languages.get, reverse=True)[:12]

    with Body() as b:
        row = b.conn.execute(
            "SELECT value FROM meta WHERE key='last_brief'").fetchone()
        since = float(row[0]) if row else 0.0
        fresh = b.conn.execute(
            """SELECT title, lang, summary, source_url, kind, created_at
               FROM memories WHERE created_at > ?
               ORDER BY importance DESC, created_at DESC LIMIT ?""",
            (since, args.limit),
        ).fetchall()
        found_gaps = insight.gaps(b, langs, limit=4)
        pending = b.open_questions(limit=5)
        met = b.people(limit=6, since=since)
        if not args.keep:
            b.conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('last_brief', ?)",
                (str(time.time()),))
            b.conn.commit()

    when = _when(since) if since else "البداية"
    print(f"منذ {when}\n" + "═" * 54)
    if not fresh:
        print("لا جديد. أرسله في رحلة:  rooh wander -n 10")
        return 1

    by_lang: dict[str, list] = {}
    for r in fresh:
        by_lang.setdefault(r["lang"], []).append(r)
    for lg, rows in sorted(by_lang.items(), key=lambda kv: -len(kv[1])):
        print(f"\n【 {languages.arabic_name(lg)} 】 {len(rows)}")
        for r in rows[: args.per_lang]:
            mark = "◆" if r["kind"] == "paper" else "•"
            print(f"  {mark} {r['title'][:70]}")
            if r["summary"]:
                print(f"     {r['summary'][:160]}")
            if r["source_url"]:
                print(f"     ← {r['source_url']}")

    if found_gaps:
        print("\n" + "═" * 54 + "\n★ فجوات لغتك")
        for g in found_gaps:
            miss = "، ".join(languages.arabic_name(l) for l in g.missing)
            print(f"  • {g.concept} — يصمت عنه: {miss}")

    if met:
        print("\n" + "═" * 54 + "\n👤 من قابل لأوّل مرّة")
        for r in met:
            venue = f" — {r['venues'][0]}" if r["venues"] else ""
            print(f"  • [{r['lang']}] {r['name']}{venue}")

    if pending:
        print("\n؟ ما يشغله ولم يفهمه بعد")
        for _qid, term, lg, _a in pending:
            print(f"  • [{lg}] {term}")
    return 0


def cmd_lead(args: argparse.Namespace) -> int:
    """أي عالَمٍ لغويٍّ سبق غيره إلى موضوعٍ ما، وبكم شهراً."""
    p = Personality.load()
    concept = " ".join(args.term)
    langs = args.lang or sorted(p.languages, key=p.languages.get, reverse=True)[:12]
    f = Fetcher(respect_robots=True) if args.learn else None
    with Body() as b:
        lead = insight.temporal_lead(b, concept, langs, fetcher=f, learn=args.learn)
        dated = b.conn.execute(
            "SELECT COUNT(*) FROM memories WHERE published IS NOT NULL").fetchone()[0]
        total = b.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    print(insight.render_lead(lead))
    if len(lead.firsts) < 2:
        print(f"\n(بتواريخ نشرٍ معروفة: {dated} من {total} ذكرى. الأخبار "
              f"والأوراق تحمل تواريخ؛ صفحات الويب العامّة لا تحملها غالباً.)")
        return 1
    return 0


def cmd_people(args: argparse.Namespace) -> int:
    """من قابله في قراءته — أسماء الباحثين والمؤلّفين، وكم تكرّر كلٌّ منهم.

    ليست علاقةً بهم: هو يقرأ ما نشروه للعموم ولا يتّصل بأحد. لكنّ تكرار
    اسمٍ بعينه في موضوعك، وبأكثر من لسان، خبرٌ لا يعطيكه محرّك بحث.
    """
    with Body() as b:
        if args.forget_all or args.forget:
            n = b.forget_people(args.forget)
            print(f"مُحي {n} سجلّاً." if n else "لا شيء ليُمحى.")
            return 0
        if args.across:
            rows = b.people_across_languages(limit=args.limit)
            if not rows:
                print("لم يقابل أحداً بأكثر من لسانٍ بعد.")
                return 1
            print("أسماء قابلها بأكثر من لسان:\n")
            for name, langs, times in rows:
                names = "، ".join(languages.arabic_name(l) for l in langs)
                print(f"  {name}  —  {names}  ({times} مرّة)")
            return 0

        since = None
        if args.new:
            row = b.conn.execute(
                "SELECT value FROM meta WHERE key='last_brief'").fetchone()
            since = float(row[0]) if row else 0.0
        rows = b.people(limit=args.limit, lang=args.lang, since=since)

    if not rows:
        print("لم يقابل أحداً بعد. أرسله في رحلاتٍ فيها أوراق بحث.")
        return 1
    for r in rows:
        seen = "مرّة واحدة" if r["times"] == 1 else f"{r['times']} مرّات"
        print(f"\n[{r['lang']}] {r['name']}   ({seen}، آخرها {_when(r['last_seen'])})")
        if r["venues"]:
            print(f"    ينشر في: {'، '.join(v for v in r['venues'][:3] if v)}")
        for work, url in r["works"][-2:]:
            print(f"    • {work[:66]}")
            if url:
                print(f"      ← {url}")
    return 0


def _record_health(b: Body, ok: bool, why: str = "") -> None:
    """يسجّل حال آخر رحلة. بدونه تعود بعد أسبوعين إلى رسائل فارغة
    لا تدري أهو صامتٌ لأنه لم يجد، أم لأنه ميّت منذ اليوم الثاني."""
    now = time.time()
    if ok:
        b.set_meta("last_ok", str(now))
        b.set_meta("fail_streak", "0")
        b.set_meta("last_error", "")
    else:
        streak = int(b.get_meta("fail_streak", "0") or 0) + 1
        b.set_meta("fail_streak", str(streak))
        b.set_meta("last_error", f"{time.strftime('%Y-%m-%d %H:%M')} — {why}"[:300])


def _health_warning(b: Body) -> Optional[str]:
    """سطرٌ يتصدّر رسالة اليوم إن كان في الأمر خلل. الصمت ليس خبراً ساراً."""
    streak = int(b.get_meta("fail_streak", "0") or 0)
    last_ok = float(b.get_meta("last_ok", "0") or 0)
    hours = (time.time() - last_ok) / 3600 if last_ok else None
    err = b.get_meta("last_error", "")

    lines: list[str] = []
    off = b.get_meta("robots_off_since", "")
    if off:
        lines.append("⚠️ robots.txt معطّل في شخصيته — يزور مواضع منعها أصحابها.")
        lines.append("   أعِده: limits.respect_robots = true في personality.json")
    if streak >= 3:
        lines.append(f"⚠️ أخفقت {streak} رحلة متتالية.")
    if hours is not None and hours > 36:
        lines.append(f"⚠️ آخر رحلةٍ مثمرة قبل {hours/24:.1f} يوم.")
    elif last_ok == 0:
        lines.append("⚠️ لم تنجح رحلةٌ واحدة بعد.")
    if lines and err:
        lines.append(f"   آخر خطأ: {err}")
    if lines:
        lines.append("   افحص: rooh sources --check")

    try:
        size = config.db_path().stat().st_size / 1e9
        if size > 20:
            lines.append(f"⚠️ حجم الجسد {size:.1f} غ.ب — راجع المساحة.")
    except OSError:
        pass
    return "\n".join(lines) if lines else None


def _compose_daily(b: Body, p: Personality, since: float, limit: int = 30) -> str:
    """يبني رسالة اليوم من كل ما يعرفه. نصٌّ عاديّ يُقرأ على جوّال."""
    langs = sorted(p.languages, key=p.languages.get, reverse=True)[:12]
    out: list[str] = []

    warning = _health_warning(b)
    if warning:
        out.append(warning)
        out.append("")

    entries = b.read_journal(1)
    if entries and entries[0][1]:
        out.append(entries[0][1].strip())
        out.append("")

    fresh = b.conn.execute(
        """SELECT title, lang, summary, source_url, kind FROM memories
           WHERE created_at > ? ORDER BY importance DESC, created_at DESC LIMIT ?""",
        (since, limit)).fetchall()
    if fresh:
        by_lang: dict[str, list] = {}
        for r in fresh:
            by_lang.setdefault(r["lang"], []).append(r)
        out.append(f"قرأت {len(fresh)} شيئاً في {len(by_lang)} لسان:")
        for lg, rows in sorted(by_lang.items(), key=lambda kv: -len(kv[1]))[:6]:
            out.append(f"\n【{languages.arabic_name(lg)}】")
            for r in rows[:3]:
                mark = "◆" if r["kind"] == "paper" else "•"
                out.append(f"{mark} {r['title'][:80]}")
                if r["source_url"]:
                    out.append(f"  {r['source_url']}")
    else:
        out.append("لم أقرأ جديداً منذ آخر مرّة.")

    hot = trends.trends(b, days=7, limit=5)
    if hot:
        out.append("\n\n🔥 ما يسخن هذا الأسبوع")
        out.append(trends.render(hot))
        # ولأسخنها: من سبق من؟
        top = hot[0]
        lead = insight.temporal_lead(b, top.term, langs)
        if len(lead.firsts) >= 2 and lead.earliest:
            worst = max(lead.firsts, key=lambda l: lead.firsts[l][0])
            months = (lead.lag_days(worst) or 0) / 30.4
            if months >= 3:
                out.append(f"  ↳ وفيه: {languages.arabic_name(lead.earliest)} سبقت "
                           f"{languages.arabic_name(worst)} بـ{months:.0f} شهراً.")

    found = insight.gaps(b, langs, limit=3)
    if found:
        out.append("\n\n★ فجوات لغتك")
        for g in found:
            miss = "، ".join(languages.arabic_name(l) for l in g.missing)
            out.append(f"  • {g.concept} — يصمت عنه: {miss}")

    met = b.people(limit=4, since=since)
    if met:
        out.append("\n\n👤 قابلت لأوّل مرّة")
        for r in met:
            venue = f" — {r['venues'][0]}" if r["venues"] else ""
            out.append(f"  • [{r['lang']}] {r['name']}{venue}")

    pending = b.open_questions(limit=4)
    if pending:
        out.append("\n\n؟ ما زال يشغلني")
        for _q, term, lg, _a in pending:
            out.append(f"  • [{lg}] {term}")

    return "\n".join(out)


def cmd_daily(args: argparse.Namespace) -> int:
    """رسالة اليوم: يبادر هو، ولا تسأله أنت."""
    p = Personality.load()
    with Body() as b:
        since = float(b.get_meta("last_daily", "0") or 0)
        text = _compose_daily(b, p, since, limit=args.limit)
        if not args.keep:
            b.set_meta("last_daily", str(time.time()))

    when = time.strftime("%Y-%m-%d", time.localtime())
    subject = f"{p.name} — {when}"
    if args.print:
        print(f"{subject}\n\n{text}")
        return 0
    result = notify.send(text, subject=subject)
    print(f"الملف: {result['file']}")
    print(f"تلغرام: {result['telegram']}")
    return 1 if result.get("error") and not notify.configured() is False else 0


def cmd_notify(args: argparse.Namespace) -> int:
    """إعداد قناة التوصيل واختبارها."""
    if args.setup or not (args.test or args.message):
        print(notify.SETUP)
        print(f"\nالحالة الآن: "
              f"{'مُهيّأ ✓' if notify.configured() else 'غير مُهيّأ — الملفّ فقط'}")
        print(f"صندوق الصادر: {notify.outbox()}")
        return 0
    text = " ".join(args.message) if args.message else (
        "تجربة اتّصال من رُوح. إن وصلتك هذه فالقناة تعمل.")
    result = notify.send(text, subject="رُوح — تجربة")
    print(f"الملف  : {result['file']}")
    print(f"تلغرام : {result['telegram']}")
    return 0 if not result.get("error") else 1


def cmd_trend(args: argparse.Namespace) -> int:
    """ما ارتفعت حصّته داخل لسانه — لا ما كثر عدده."""
    with Body() as b:
        hot = trends.trends(b, days=args.days, limit=args.limit)
        if not hot:
            total = b.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        print(trends.render(hot))
        if not hot:
            print(f"\n(في جسده {total} ذكرى. التسارع يحتاج نافذتين متتاليتين "
                  f"من {args.days} يوماً فيهما قراءةٌ كافية.)")
            return 1
        for t in hot[:3]:
            for title in t.titles[:1]:
                print(f"      {title[:70]}")
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    """لقطة يومية للقياس — سطر JSON واحد يُلحق بـ snapshots.jsonl.

    هذا هو ما يُحلَّل في التجربة، لا قاعدة البيانات نفسها: ستة أسابيع
    تشغيلٍ بلا لقطاتٍ يومية تنتج قاعدة بيانات، لا نتيجة.
    """
    p = Personality.load()
    path = config.snapshots_path()

    if args.show:
        if not path.exists():
            print("لا لقطات بعد.")
            return 1
        lines = path.read_text(encoding="utf-8").strip().splitlines()[-args.show:]
        print(f"{'التاريخ':<12} {'وضع':<8} {'رحلات':>6} {'صفحات':>7} {'ذكريات':>7} "
              f"{'أسئلة':>7} {'ملل':>5} {'حيرة':>5} {'لغات':>5}")
        print("─" * 74)
        for ln in lines:
            try:
                d = json.loads(ln)
            except json.JSONDecodeError:
                continue
            dl, cu, dr = d["delta"], d["cumulative"], d["drives"]
            print(f"{d['date']:<12} {d.get('mode','?'):<8} {dl['journeys']:>6} "
                  f"{dl['pages']:>7} {dl['memories']:>7} "
                  f"{cu['questions_open']:>7} {dr['boredom']:>5.2f} "
                  f"{dr['confusion']:>5.2f} {len(d['languages_delta']):>5}")
        return 0

    with Body() as b:
        since = float(b.get_meta("last_snapshot", "0") or 0)
        snap = b.snapshot(since)
        drives = Drives.loads(b.load_drives())
        open_q = b.count_open_questions()
        snap.update({
            "date": time.strftime("%Y-%m-%d", time.localtime()),
            "ts": round(time.time(), 3),
            "since": round(since, 3),
            "label": args.label or b.get_meta("label", "rooh"),
            "mode": b.get_meta("mode", "كامل"),
            "drives": {k: round(v, 4) for k, v in vars(drives).items()},
            "mood": drives.mood(),
            "urge": drives.urge(open_q > 0),
        })
        try:
            from . import insight

            langs = sorted(p.languages, key=p.languages.get, reverse=True)[:12]
            snap["gaps"] = len(insight.gaps(b, langs, limit=20))
        except Exception:          # الفجوات مؤشّرٌ مساعد، لا تُسقط اللقطة
            snap["gaps"] = None
        if args.label:
            b.set_meta("label", args.label)
        if not args.keep:
            b.set_meta("last_snapshot", str(snap["ts"]))

    line = json.dumps(snap, ensure_ascii=False, sort_keys=True)
    if not args.dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    if args.json:
        print(line)
        return 0

    dl, cu = snap["delta"], snap["cumulative"]
    print(f"لقطة {snap['date']} • {snap['label']} • وضع «{snap['mode']}»")
    print(f"  منذ اللقطة السابقة: {dl['journeys']} رحلة • {dl['pages']} صفحة • "
          f"{dl['memories']} ذكرى • فتح {dl['questions_opened']} سؤالاً "
          f"وأغلق {dl['questions_answered']}")
    print(f"  التراكمي: {cu['memories']} ذكرى • {cu['lexicon']} مفهوماً في معجمه • "
          f"{cu['questions_open']} سؤالاً مفتوحاً")
    if snap["languages_delta"]:
        top = sorted(snap["languages_delta"].items(), key=lambda kv: -kv[1])[:6]
        print("  لغات اليوم: " + "، ".join(
            f"{languages.arabic_name(k)} {v}" for k, v in top))
    print(f"  حاله: {snap['mood']} — يريد أن {snap['urge']}")
    if not args.dry_run:
        print(f"\n  ← {path}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    with Body() as b:
        st = b.stats()
        interests = b.top_interests(limit=5)
    print(f"الجسد   : {st['db']} ({_human_bytes(st['size_bytes'])})")
    print(f"وُلد    : {_when(st['born_at'])}")
    print(f"رحلات  : {st['journeys']}")
    print(f"صفحات  : {st['pages']}")
    print(f"ذكريات : {st['memories']}" +
          (f"  (منها {st['papers']} ورقة بحث)" if st.get("papers") else ""))
    print(f"فضول   : {st['interests']} مصطلحاً")
    print(f"أسئلة  : {st['questions_open']} مفتوح • "
          f"{st['questions_answered']} أُجيب")
    if st["by_lang"]:
        print("لغاته  : " + "، ".join(f"{k}={v}" for k, v in st["by_lang"].items()))
    if interests:
        print("أكثر ما يشغله: " + "، ".join(t for t, _, _ in interests))
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    src = sources.load_sources(config.sources_path())
    if not args.check:
        print(f"لغات ويكيبيديا: {' '.join(src['wiki_langs'])}\n")
        for lg, feeds in src.get("feeds", {}).items():
            print(f"[{lg}]")
            for fd in feeds:
                print(f"   {fd['name']:<20} {fd['url']}")
        print(f"\nعدّلها في: {config.sources_path()}")
        return 0

    f = Fetcher(respect_robots=True)
    bad = 0
    for lg, feeds in src.get("feeds", {}).items():
        for fd in feeds:
            try:
                resp = f.get(fd["url"], accept="application/rss+xml,application/xml,*/*")
                items = sources.parse_feed(resp.text())
                mark = "✓" if items else "؟"
                print(f"{mark} [{lg}] {fd['name']}: {len(items)} مقالاً")
                if not items:
                    bad += 1
            except FetchError as e:
                print(f"✗ [{lg}] {fd['name']}: {e}")
                bad += 1
    print(f"\nمعطّلة: {bad}")
    return 1 if bad else 0


def cmd_forget(args: argparse.Namespace) -> int:
    with Body() as b:
        cur = b.conn.execute("DELETE FROM memories WHERE id=?", (args.id,))
        b.conn.commit()
    if cur.rowcount:
        print(f"نُسيت الذكرى #{args.id}.")
        return 0
    print(f"لا توجد ذكرى بهذا الرقم: {args.id}")
    return 1


# ── التركيب ──────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="rooh",
        description="رُوح: روح تتجوّل في الشبكة، وجسد على جهازك يحفظ ما تعود به.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="يهيّئ البيت والشخصية والجسد")
    p.add_argument("--force", action="store_true", help="يعيد كتابة الشخصية")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("who", help="من هو، وماذا في جسده")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-llm", action="store_true")
    p.set_defaults(fn=cmd_who)

    p = sub.add_parser("wander", help="رحلة واحدة: يخرج ويعود")
    p.add_argument("-n", "--pages", type=int, default=None, help="كم صفحة يحفظ")
    p.add_argument("--lang", default=None, help="يقصر تجوّله على لغة واحدة (zh, ja, ru…)")
    p.add_argument("--no-llm", action="store_true", help="عقل محلي فقط")
    p.add_argument("-q", "--quiet", action="store_true")
    p.add_argument("--mode", choices=list(MODES), default=None,
                   help="وضع التجربة: كامل (رُوح) أو خطّ مرجعي")
    p.set_defaults(fn=cmd_wander)

    p = sub.add_parser("live", help="يظلّ يخرج ويعود على فترات")
    p.add_argument("--every", type=int, default=60, help="دقائق بين الرحلات")
    p.add_argument("--times", type=int, default=0, help="عدد الرحلات ثم يتوقّف (0=بلا حدّ)")
    p.add_argument("-n", "--pages", type=int, default=None)
    p.add_argument("--lang", default=None)
    p.add_argument("--no-llm", action="store_true")
    p.add_argument("-q", "--quiet", action="store_true")
    p.add_argument("--mode", choices=list(MODES), default=None)
    p.set_defaults(fn=cmd_live)

    p = sub.add_parser("recall", help="تسأله عمّا يذكر")
    p.add_argument("query")
    p.add_argument("-n", "--limit", type=int, default=8)
    p.add_argument("--echoes", action="store_true",
                   help="يعرض ما يتّصل بكل ذكرى من ذكرياته الأخرى")
    p.set_defaults(fn=cmd_recall)

    p = sub.add_parser("recent", help="آخر ما التقطه")
    p.add_argument("-n", "--limit", type=int, default=15)
    p.add_argument("--lang", default=None)
    p.set_defaults(fn=cmd_recent)

    p = sub.add_parser("interests", help="خريطة فضوله الآن")
    p.add_argument("-n", "--limit", type=int, default=15)
    p.add_argument("--lang", default=None)
    p.set_defaults(fn=cmd_interests)

    p = sub.add_parser("journal", help="يوميّاته بعد كل عودة")
    p.add_argument("-n", "--limit", type=int, default=3)
    p.set_defaults(fn=cmd_journal)

    p = sub.add_parser("note", help="تضع أنت ذكرى في جسده")
    p.add_argument("text", nargs="+")
    p.add_argument("--title", default=None)
    p.add_argument("--lang", default="ar")
    p.set_defaults(fn=cmd_note)

    p = sub.add_parser("papers", help="بحث في قواعد الأبحاث المفتوحة بأي لغة")
    p.add_argument("query", nargs="+")
    p.add_argument("--lang", default=None, help="لغة البحث (ja, ru, es…)")
    p.add_argument("-n", "--limit", type=int, default=5)
    p.add_argument("--source", action="append",
                   choices=list(research.PROVIDERS), help="يقصر السؤال على قاعدة")
    p.add_argument("--save", action="store_true", help="يحفظ النتائج في جسده")
    p.add_argument("--no-llm", action="store_true")
    p.set_defaults(fn=cmd_papers)

    p = sub.add_parser("langs", help="لغات العالم التي يتجوّل فيها")
    p.add_argument("--all", action="store_true", help="يعرض كل اللغات بالأقاليم")
    p.add_argument("--profile", default=None,
                   help="يغيّر التوزيع: متوازن | العالم | اسم إقليم")
    p.add_argument("-n", "--limit", type=int, default=20)
    p.set_defaults(fn=cmd_langs)

    p = sub.add_parser("drives", help="دوافعه الآن: ما الذي يحرّكه وماذا يريد")
    p.set_defaults(fn=cmd_drives)

    p = sub.add_parser("questions", help="أسئلته المعلّقة")
    p.add_argument("--answered", action="store_true", help="ما أغلقه بدل ما فتحه")
    p.add_argument("-n", "--limit", type=int, default=12)
    p.set_defaults(fn=cmd_questions)

    p = sub.add_parser("compare", help="كيف يرى كل عالَمٍ لغويٍّ موضوعاً واحداً")
    p.add_argument("term", nargs="+")
    p.add_argument("--lang", action="append", help="يقصر المقارنة على لغات بعينها")
    p.add_argument("--learn", action="store_true",
                   help="يخرج للشبكة ليتعلّم المقابلات الناقصة")
    p.add_argument("--no-llm", action="store_true")
    p.set_defaults(fn=cmd_compare)

    p = sub.add_parser("gaps", help="مواضيع يكتب عنها العالم وتصمت عنها لغتك")
    p.add_argument("-n", "--limit", type=int, default=8)
    p.add_argument("--learn", action="store_true")
    p.set_defaults(fn=cmd_gaps)

    p = sub.add_parser("brief", help="خلاصة ما جدّ منذ آخر مرّة سألت")
    p.add_argument("-n", "--limit", type=int, default=40)
    p.add_argument("--per-lang", type=int, default=4)
    p.add_argument("--keep", action="store_true",
                   help="لا يحرّك العلامة، فتراها ثانيةً في المرّة القادمة")
    p.set_defaults(fn=cmd_brief)

    p = sub.add_parser("lead", help="أيّ لسانٍ سبق غيره إلى موضوع، وبكم")
    p.add_argument("term", nargs="+")
    p.add_argument("--lang", action="append")
    p.add_argument("--learn", action="store_true")
    p.set_defaults(fn=cmd_lead)

    p = sub.add_parser("people", help="من قابله في قراءته")
    p.add_argument("-n", "--limit", type=int, default=12)
    p.add_argument("--lang", default=None)
    p.add_argument("--new", action="store_true", help="من قابلهم منذ آخر خلاصة")
    p.add_argument("--across", action="store_true",
                   help="من قابلهم بأكثر من لسان")
    p.add_argument("--forget", metavar="اسم", default=None,
                   help="يمحو اسماً بعينه")
    p.add_argument("--forget-all", action="store_true",
                   help="يمحو كل الأسماء المسجّلة")
    p.set_defaults(fn=cmd_people)

    p = sub.add_parser("daily", help="رسالة اليوم — يبادر هو ولا تسأله أنت")
    p.add_argument("-n", "--limit", type=int, default=30)
    p.add_argument("--print", action="store_true", help="يطبعها بدل أن يرسلها")
    p.add_argument("--keep", action="store_true", help="لا يحرّك علامة اليوم")
    p.set_defaults(fn=cmd_daily)

    p = sub.add_parser("notify", help="إعداد قناة التوصيل واختبارها")
    p.add_argument("--setup", action="store_true", help="يشرح خطوات تلغرام")
    p.add_argument("--test", action="store_true", help="يرسل رسالة تجربة")
    p.add_argument("message", nargs="*", help="نصٌّ ترسله بنفسك")
    p.set_defaults(fn=cmd_notify)

    p = sub.add_parser("trend", help="ما يسخن الآن (بالحصّة لا بالعدد)")
    p.add_argument("--days", type=int, default=7, help="طول النافذة بالأيام")
    p.add_argument("-n", "--limit", type=int, default=8)
    p.set_defaults(fn=cmd_trend)

    p = sub.add_parser("snapshot", help="لقطة يومية للقياس (JSONL)")
    p.add_argument("--json", action="store_true", help="سطر JSON فقط")
    p.add_argument("--show", type=int, metavar="N", help="يعرض آخر N لقطة")
    p.add_argument("--label", default=None, help="اسم هذه النسخة في التجربة")
    p.add_argument("--keep", action="store_true", help="لا يحرّك علامة الفارق")
    p.add_argument("--dry-run", action="store_true", help="بلا كتابة في السجلّ")
    p.set_defaults(fn=cmd_snapshot)

    p = sub.add_parser("status", help="حالة الجسد")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("sources", help="أين يتجوّل")
    p.add_argument("--check", action="store_true", help="يتأكّد أن الخلاصات حيّة")
    p.set_defaults(fn=cmd_sources)

    p = sub.add_parser("forget", help="يمحو ذكرى برقمها")
    p.add_argument("id", type=int)
    p.set_defaults(fn=cmd_forget)

    return ap


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config.ensure_home()
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
