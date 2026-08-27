"""الواجهة — كيف تكلّمه أنت."""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Optional

from . import config, sources
from .body import Body
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
            print(f"⟶ يخرج وهو {data['mood']} — فضوله: "
                  f"{'، '.join(data['seeds'][:4])}")
        elif kind == "translate":
            print(f"   ↯ «{data['from']}» تُقال «{data['to']}» بـ{data['lang']}")
        elif kind == "visit":
            print(f"   · [{data['lang']}] {data['source']}")
        elif kind == "kept":
            print(f"   ✓ [{data['lang']}] {data['title'][:70]} "
                  f"(وزن {data['importance']})")
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


def cmd_status(args: argparse.Namespace) -> int:
    with Body() as b:
        st = b.stats()
        interests = b.top_interests(limit=5)
    print(f"الجسد   : {st['db']} ({_human_bytes(st['size_bytes'])})")
    print(f"وُلد    : {_when(st['born_at'])}")
    print(f"رحلات  : {st['journeys']}")
    print(f"صفحات  : {st['pages']}")
    print(f"ذكريات : {st['memories']}")
    print(f"فضول   : {st['interests']} مصطلحاً")
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
