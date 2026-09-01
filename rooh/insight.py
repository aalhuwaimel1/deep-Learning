"""الاستبصار — ما الذي يعطيك إياه هذا الكائن ولا يعطيكه غيره.

جمعُ الصفحات ليس منفعة. قوقل يجمع أكثر منه وأسرع. المنفعة الوحيدة التي
لا تجدها في مكان آخر هي هذه: أنت تقرأ العالم من نافذة لغتك، فترى ما
تراه لغتك فقط. هذا الكائن يقف في عشر نوافذ في آنٍ واحد، فيستطيع أن
يقول لك:

    «هذا الموضوع يكتب عنه اليابانيون منذ سنة، ولا وجود له بالعربية.»

هذه جملة لا يستطيع محرّك بحث أن يقولها لك، لأنه يبحث داخل لغتك لا
عبرها.

أساس هذا كله جدول `lexicon`: المفهوم الواحد بأسماء أهله. بدونه تكون
المقارنة بين «الذكاء الاصطناعي» و«人工知能» مقارنةَ نصّين مختلفين لا
مقارنةَ عالَمين.

تحذير مبنيّ في الكود: «لا تغطية بالكورية» ليست حقيقةً عن العالم إن كان
لم يزر الكورية أصلاً. تلك حقيقة عنه هو. نفرّق بين الاثنين صراحةً.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from . import sources
from .body import Body
from .languages import arabic_name
from .net import Fetcher

#: أقلّ عدد ذكريات في لغةٍ ما حتى نعدّ غيابَ موضوعٍ عنها خبراً عن العالم
#: لا خبراً عن كسل الكائن.
MIN_PRESENCE = 5


@dataclass
class LangView:
    """ما يراه عالَمٌ لغويٌّ واحد في موضوع واحد."""
    lang: str
    term: str = ""              # المصطلح بلسانهم
    count: int = 0              # كم ذكرى عنده منهم في هذا الموضوع
    titles: list[str] = field(default_factory=list)
    summaries: list[str] = field(default_factory=list)
    explored: int = 0           # كم زار هذه اللغة إجمالاً

    @property
    def covered(self) -> bool:
        return self.count > 0

    @property
    def trustworthy(self) -> bool:
        """هل زار هذه اللغة بما يكفي ليكون غيابُ الموضوع عنها ذا معنى؟"""
        return self.explored >= MIN_PRESENCE


@dataclass
class Coverage:
    concept: str
    views: dict[str, LangView] = field(default_factory=dict)

    @property
    def covering(self) -> list[str]:
        return [lg for lg, v in self.views.items() if v.covered]

    @property
    def real_gaps(self) -> list[str]:
        """لغاتٌ زارها كثيراً ولم يجد فيها هذا الموضوع. هذه فجوة حقيقية."""
        return [lg for lg, v in self.views.items()
                if not v.covered and v.trustworthy and v.term]

    @property
    def unexplored(self) -> list[str]:
        """لغاتٌ لم يزرها بما يكفي. غيابُ الموضوع عنها لا يعني شيئاً."""
        return [lg for lg, v in self.views.items()
                if not v.covered and not v.trustworthy]

    @property
    def untranslatable(self) -> list[str]:
        """لغاتٌ لا مقابل للمفهوم فيها أصلاً — وهذا بذاته خبر."""
        return [lg for lg, v in self.views.items() if not v.term]


# ── القياس ───────────────────────────────────────────────────────────────
def _explored(body: Body) -> dict[str, int]:
    rows = body.conn.execute(
        "SELECT lang, COUNT(*) c FROM memories GROUP BY lang").fetchall()
    return {r["lang"]: r["c"] for r in rows}


def _memories_about(body: Body, term: str, lang: str,
                    limit: int = 5) -> list[tuple[str, str]]:
    """ذكرياته بهذه اللغة التي يدور فيها هذا المصطلح.

    نطابق جزئياً لا بالمساواة: مصطلح «人工知能» يظهر في مفاتيح الصفحة
    ثنائيّاتٍ (人工، 工知، 知能)، فالمساواة تفوّته دائماً.
    """
    like = f"%{term}%"
    rows = body.conn.execute(
        """SELECT title, summary FROM memories
           WHERE lang = ? AND (title LIKE ? OR summary LIKE ? OR body LIKE ?
                               OR keywords LIKE ?)
           ORDER BY importance DESC, created_at DESC LIMIT ?""",
        (lang, like, like, like, like, limit),
    ).fetchall()
    return [(r["title"] or "", r["summary"] or "") for r in rows]


def _known_translation(body: Body, term: str, lang: str) -> Optional[str]:
    sources.ensure_lexicon(body.conn)
    row = body.conn.execute(
        """SELECT dst_term FROM lexicon
           WHERE term=? AND src_lang='ar' AND dst_lang=?""",
        (term, lang),
    ).fetchone()
    return row[0] if row else None


def coverage(body: Body, concept: str, langs: list[str],
             fetcher: Optional[Fetcher] = None,
             learn: bool = False) -> Coverage:
    """كيف يغطّي كل عالَمٍ لغويٍّ هذا المفهوم، بحسب ما جمعه حتى الآن.

    `learn=True` يخرج إلى الشبكة ليتعلّم المقابلات الناقصة. بدونه يعمل
    بما في معجمه فقط — أسرع، وبلا إنترنت.
    """
    explored = _explored(body)
    out = Coverage(concept=concept)

    for lg in langs:
        term = concept if lg == "ar" else _known_translation(body, concept, lg)
        if term is None and learn and fetcher is not None:
            term = sources.translate_term(fetcher, body.conn, concept, "ar", lg)
        view = LangView(lang=lg, term=term or "", explored=explored.get(lg, 0))
        if term:
            found = _memories_about(body, term, lg)
            view.count = len(found)
            view.titles = [t for t, _ in found]
            view.summaries = [s for _, s in found if s]
        out.views[lg] = view
    return out


def concepts_of(body: Body, limit: int = 25) -> list[str]:
    """المفاهيم التي يستحقّ أن نسأل عن تغطيتها: ما تعلّم مقابله بلغةٍ ما.

    نأخذها من المعجم لا من خريطة الفضول، لأن المعجم وحده يحمل مفاهيم
    قابلة للمقارنة بين اللغات — والباقي مصطلحاتٌ حبيسة لغتها.
    """
    sources.ensure_lexicon(body.conn)
    rows = body.conn.execute(
        """SELECT term, COUNT(*) c FROM lexicon
           WHERE src_lang='ar' AND dst_term IS NOT NULL
           GROUP BY term ORDER BY c DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [r["term"] for r in rows]


@dataclass
class Gap:
    concept: str
    covering: list[str]         # لغاتٌ تكتب عنه
    missing: list[str]          # لغاتٌ زارها كثيراً ولا تكتب عنه
    sample: list[tuple[str, str]] = field(default_factory=list)  # (لغة, عنوان)

    @property
    def weight(self) -> float:
        """قوّة الفجوة: كثرة من يكتب عنه، وكثرة من يصمت عنه."""
        return len(self.covering) * len(self.missing)


def gaps(body: Body, langs: list[str], limit: int = 10,
         fetcher: Optional[Fetcher] = None, learn: bool = False) -> list[Gap]:
    """مواضيع يكتب عنها بعض العالم ويصمت عنها بعضه — وأنت في الصامت."""
    found: list[Gap] = []
    for concept in concepts_of(body, limit=40):
        cov = coverage(body, concept, langs, fetcher, learn)
        missing = cov.real_gaps
        covering = cov.covering
        if not covering or not missing:
            continue
        sample: list[tuple[str, str]] = []
        for lg in covering[:3]:
            v = cov.views[lg]
            if v.titles:
                sample.append((lg, v.titles[0]))
        found.append(Gap(concept=concept, covering=covering, missing=missing,
                         sample=sample))
    found.sort(key=lambda g: g.weight, reverse=True)
    return found[:limit]


# ── الصياغة ──────────────────────────────────────────────────────────────
def render_coverage(cov: Coverage) -> str:
    """عرضٌ نصّي أمين: يفصل ما لا يعرفه عمّا يعرف أنه غير موجود."""
    lines = [f"«{cov.concept}» عبر عوالم اللغات:\n"]
    ordered = sorted(cov.views.values(), key=lambda v: (-v.count, v.lang))
    for v in ordered:
        if not v.term:
            continue
        mark = "●" if v.covered else ("○" if v.trustworthy else "·")
        name = arabic_name(v.lang)
        head = f"{mark} {name} ({v.lang})"
        if v.term != cov.concept:
            head += f" — «{v.term}»"
        lines.append(head)
        for t in v.titles[:3]:
            lines.append(f"      {t[:74]}")
        if not v.covered:
            lines.append("      لا شيء عنده منهم"
                         + ("" if v.trustworthy else " (ولم يزرهم بما يكفي)"))
    if cov.untranslatable:
        names = "، ".join(arabic_name(l) for l in cov.untranslatable)
        lines.append(f"\nلا مقابل للمفهوم في: {names} — وهذا بذاته خبر.")
    lines.append("\n●=عنده منهم   ○=زارهم ولم يجد   ·=لم يزرهم بما يكفي")
    return "\n".join(lines)


def synthesize(mind, cov: Coverage) -> Optional[str]:
    """يقارن بنموذج لغوي: على ماذا تتّفق العوالم، وبماذا ينفرد كلٌّ منها.

    بلا نموذج نعرض الجداول فقط — ولا نؤلّف مقارنةً لا نملك أدلّتها.
    """
    if not getattr(mind, "has_llm", False):
        return None
    blocks: list[str] = []
    for v in sorted(cov.views.values(), key=lambda v: -v.count):
        if not v.covered:
            continue
        body_text = "\n".join(f"- {t}: {s[:400]}"
                              for t, s in zip(v.titles, v.summaries))
        blocks.append(f"[{arabic_name(v.lang)} — «{v.term}»]\n{body_text}")
    if len(blocks) < 2:
        return None

    system = (
        "تُعطى خلاصاتٍ عن موضوعٍ واحد، مأخوذةً من مصادر بلغاتٍ مختلفة. "
        "اكتب بالعربية، في نقاطٍ قصيرة: (١) ما تتّفق عليه المصادر، "
        "(٢) ما ينفرد به كل لسان ولا يذكره غيره، (٣) ما يلفت النظر في "
        "اختلاف زوايا النظر. لا تضف معلومةً ليست في النصوص، وقل صراحةً "
        "إن كانت المصادر متشابهة ولا فرق يُذكر."
    )
    prompt = f"الموضوع: {cov.concept}\n\n" + "\n\n".join(blocks)
    return mind.llm.ask(system, prompt, max_tokens=1200)
