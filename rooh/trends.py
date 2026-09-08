"""التسارع — ما الذي يسخن الآن، ومقارنةً بماذا.

الفخّ الذي يجب تجنّبه أوّلاً: لو عددنا الذكريات عدّاً خاماً، لظهر كل شيء
يابانيٍّ «متسارعاً» في أسبوعٍ زار فيه اليابانية أكثر من غيرها. وذلك قياسٌ
لتجواله هو لا للعالم — نفس الخطأ الذي حُرس منه في §الفجوات.

فنقيس **حصّة** المصطلح داخل لسانه، لا عدده المطلق. إن ارتفعت حصّة «量子»
من ٣٪ إلى ٩٪ من قراءاته اليابانية، فذلك تسارعٌ حقيقي حتى لو قرأ يابانيةً
أقلّ هذا الأسبوع.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Optional

from .body import Body

#: أقلّ عددٍ من الذكريات في النافذة حتى تُقارَن. ما دونه ضجيجُ عيّنة:
#: مصطلحٌ ظهر مرّةً ثم مرّتين ليس «تضاعفاً».
MIN_SAMPLE = 3
#: وأقلّ عددٍ من الظهور في النافذة الحديثة حتى نسمّيه تسارعاً.
MIN_RECENT = 3


@dataclass
class Trend:
    term: str
    lang: str
    now: int              # مرّاته في النافذة الحديثة
    before: int           # مرّاته في النافذة السابقة
    share_now: float      # حصّته من قراءات لسانه، حديثاً
    share_before: float
    titles: list[str]

    @property
    def ratio(self) -> float:
        """كم تضاعفت حصّته. لا نقسم على صفر: الجديد كلّياً له معاملٌ خاص."""
        if self.share_before <= 0:
            return float("inf")
        return self.share_now / self.share_before

    @property
    def is_new(self) -> bool:
        return self.before == 0

    def describe(self) -> str:
        from .languages import arabic_name

        who = arabic_name(self.lang)
        if self.is_new:
            return f"«{self.term}» ظهر في {who} ولم يكن قبل ({self.now} مرّات)"
        return (f"«{self.term}» في {who}: حصّته تضاعفت {self.ratio:.1f}× "
                f"({self.before} ← {self.now} مرّة)")


def _window(body: Body, start: float, end: float) -> tuple[dict[tuple[str, str], int],
                                                           dict[str, int],
                                                           dict[tuple[str, str], list[str]]]:
    """عدّ المصطلحات ومجموع الذكريات لكل لسان في نافذةٍ زمنية."""
    counts: dict[tuple[str, str], int] = {}
    totals: dict[str, int] = {}
    titles: dict[tuple[str, str], list[str]] = {}
    rows = body.conn.execute(
        """SELECT lang, keywords, title FROM memories
           WHERE created_at >= ? AND created_at < ?""", (start, end)).fetchall()
    for r in rows:
        lang = r["lang"] or "mul"
        totals[lang] = totals.get(lang, 0) + 1
        try:
            kws = json.loads(r["keywords"] or "[]")
        except (json.JSONDecodeError, TypeError):
            kws = []
        for kw in kws[:8]:
            key = (kw, lang)
            counts[key] = counts.get(key, 0) + 1
            if r["title"] and len(titles.setdefault(key, [])) < 3:
                titles[key].append(r["title"])
    return counts, totals, titles


def trends(body: Body, days: int = 7, limit: int = 8,
           now: Optional[float] = None) -> list[Trend]:
    """ما ارتفعت حصّته داخل لسانه بين النافذتين الأخيرتين."""
    end = now if now is not None else time.time()
    mid = end - days * 86400
    start = mid - days * 86400

    recent, recent_tot, titles = _window(body, mid, end)
    older, older_tot, _ = _window(body, start, mid)

    out: list[Trend] = []
    for (term, lang), n in recent.items():
        if n < MIN_RECENT:
            continue
        tot_now = recent_tot.get(lang, 0)
        tot_before = older_tot.get(lang, 0)
        # لا نحكم على لسانٍ لم يُقرأ فيه ما يكفي في أيٍّ من النافذتين
        if tot_now < MIN_SAMPLE:
            continue
        before = older.get((term, lang), 0)
        share_now = n / tot_now
        share_before = (before / tot_before) if tot_before else 0.0
        if before and share_now <= share_before * 1.5:
            continue                      # ارتفاعٌ ضعيف ليس تسارعاً
        if not before and tot_before < MIN_SAMPLE:
            continue                      # لم يكن يقرأ هذا اللسان أصلاً
        out.append(Trend(term=term, lang=lang, now=n, before=before,
                         share_now=share_now, share_before=share_before,
                         titles=titles.get((term, lang), [])))

    # الجديد كلّياً أوّلاً، ثم الأعلى تضاعفاً، ثم الأكثر تكراراً
    out.sort(key=lambda t: (t.is_new, t.ratio if t.ratio != float("inf") else 999,
                            t.now), reverse=True)
    return out[:limit]


def render(items: list[Trend]) -> str:
    if not items:
        return "لا شيء يسخن هذا الأسبوع."
    return "\n".join(f"  • {t.describe()}" for t in items)
