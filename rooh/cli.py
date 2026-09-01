"""الواجهة — كيف تكلّمه أنت."""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Optional

from . import config, insight, languages, research, sources
from .body import Body
from .drives import Drives
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
        w = Wanderer(body, p, mind, on_event=on_event)
        try:
            rep = w.journey(pages=args.pages, only_lang=args.lang)
        except KeyboardInterrupt:
            print("\nقُطعت الرحلة. ما حُفظ حتى الآن باقٍ في الجسد.")
            return 130
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

    if pending:
        print("\n؟ ما يشغله ولم يفهمه بعد")
        for _qid, term, lg, _a in pending:
            print(f"  • [{lg}] {term}")
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
    p.set_defaults(fn=cmd_wander)

    p = sub.add_parser("live", help="يظلّ يخرج ويعود على فترات")
    p.add_argument("--every", type=int, default=60, help="دقائق بين الرحلات")
    p.add_argument("--times", type=int, default=0, help="عدد الرحلات ثم يتوقّف (0=بلا حدّ)")
    p.add_argument("-n", "--pages", type=int, default=None)
    p.add_argument("--lang", default=None)
    p.add_argument("--no-llm", action="store_true")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(fn=cmd_live)

    p = sub.add_parser("recall", help="تسأله عمّا يذكر")
    p.add_argument("query")
    p.add_argument("-n", "--limit", type=int, default=8)
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
