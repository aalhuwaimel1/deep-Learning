"""الدوافع — لماذا يخرج، ولماذا يغيّر وجهته، ولماذا يعود.

قبل هذا الملف كان «المزاج» زينة: يُختار عشوائياً ويُطبع في اليوميّات ولا
يغيّر قراراً واحداً. هنا يصير المزاج **نتيجة** لا سبباً، والدوافع هي التي
تقود.

الفكرة المركزية: الدافع ليس الجدّة بذاتها، بل **معدّل التعلّم**.

    صفحة لا جديد فيها  →  لا يتعلّم  →  ملل
    صفحة كلها جديد     →  لا يجد ما يربطها بشيء يعرفه  →  حيرة
    صفحة بينهما        →  يربط الجديد بالقديم  →  هذا هو التعلّم

الشيء المألوف جداً والغريب جداً كلاهما عقيم. المنطقة الخصبة بينهما،
وموضعها يحدّده انفتاح الشخصية. الكائن يقيس أين وقع، فيتحرّك نحو المنطقة
الخصبة — وهذا وحده يولّد سلوكاً يبدو كأنّ صاحبه يريد شيئاً.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Optional


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass
class Drives:
    """حالته الداخلية اللحظية. تُحفظ في الجسد بين الرحلات."""

    curiosity: float = 0.55      # الفضول: شدّة اندفاعه نحو ما لا يعرف
    boredom: float = 0.10        # الملل: تراكمُ صفحاتٍ لم تعلّمه شيئاً
    confusion: float = 0.10      # الحيرة: تراكمُ غريبٍ لم يستطع ربطه
    longing: float = 0.0         # الشوق: أسئلةٌ فتحها ولم يغلقها بعد
    fatigue: float = 0.0         # التعب: كم مشى في هذه الرحلة
    satisfaction: float = 0.3    # الرضا: كم تعلّم فعلاً مؤخّراً

    # ── القياس ───────────────────────────────────────────────────────────
    @staticmethod
    def novelty(keywords: list[str], known: set[str]) -> float:
        """كم من هذه الصفحة جديد عليه؟ صفر = يعرفها كلها، واحد = لا يعرف منها شيئاً."""
        if not keywords:
            return 0.0
        fresh = sum(1 for k in keywords if k.lower() not in known)
        return fresh / len(keywords)

    @staticmethod
    def learning(novelty: float, openness: float = 0.5) -> float:
        """كم تعلّم من صفحةٍ جِدّتُها كذا؟ ذروتها في المنطقة الخصبة.

        الانفتاح يزحزح الذروة: المنفتح يتعلّم من الأغرب، والمتحفّظ يحتاج
        أرضاً مألوفة أكثر ليربط عليها.
        """
        op = _clamp(openness)
        peak = 0.30 + 0.35 * op                   # ٠٫٣ للمتحفّظ، ٠٫٦٥ للمنفتح
        # قاعدة المنحنى يجب ألا تتجاوز الجِدّة ١٫٠ مهما بلغ الانفتاح: صفحةٌ
        # لا يتّصل منها شيءٌ بشيءٍ يعرفه لا تُعلّمه شيئاً بحكم التعريف. وبدون
        # هذا القيد كان المنفتح (٠٫٩) يأخذ مكافأة ٠٫٢٠ من ضوضاء محضة، فينهار
        # حصانته من «التلفاز المشوّش» — وهي أهمّ ما يميّز معدّل التعلّم عن
        # الجِدّة الصرفة.
        width = min(0.30 + 0.20 * op, 1.0 - peak)
        return _clamp(1.0 - abs(novelty - peak) / width)

    # ── التحديث بعد كل صفحة ──────────────────────────────────────────────
    def observe(self, novelty: float, openness: float = 0.5,
                depth: float = 0.6) -> float:
        """يهضم أثر صفحةٍ واحدة على حالته. يعيد مقدار ما تعلّمه منها."""
        gain = self.learning(novelty, openness)

        if novelty < 0.15:                       # عرفها سلفاً
            self.boredom = _clamp(self.boredom + 0.16)
        else:
            self.boredom = _clamp(self.boredom - 0.09 * gain)

        if novelty > 0.85:                       # غريبة عليه كلياً
            self.confusion = _clamp(self.confusion + 0.14 * (1.0 - openness))
        else:
            self.confusion = _clamp(self.confusion - 0.08 * gain)

        self.satisfaction = _clamp(self.satisfaction * 0.92 + 0.30 * gain)
        # الصفحة العميقة تُتعب أكثر، والتعلّم يخفّف وقع التعب
        self.fatigue = _clamp(self.fatigue + 0.05 + 0.05 * depth - 0.02 * gain)
        # الملل يشعل الفضول، والحيرة تطفئه
        self.curiosity = _clamp(
            self.curiosity + 0.06 * self.boredom - 0.05 * self.confusion
        )
        return gain

    def rest(self) -> None:
        """ينام. التعب يزول، وأثر الرحلة يخفت لا ينمحي."""
        self.fatigue = 0.0
        self.boredom *= 0.6
        self.confusion *= 0.7
        self.satisfaction *= 0.85

    #: عدد الأسئلة الذي يبلغ عنده الشوق تمامه. منخفضٌ عمداً: لو جعلناه
    #: كبيراً لاحتاج المثابرُ ستّة أسئلة قبل أن يلتفت إلى واحد، فضاع
    #: السؤال الفرد دائماً — وهو أثمن ما يملك.
    QUESTIONS_FOR_FULL_LONGING = 5

    def feel_questions(self, open_count: int, persistence: float = 0.5) -> None:
        """الأسئلة المعلّقة تولّد شوقاً — والمثابر يشتاق أسرع."""
        pressure = min(1.0, open_count / self.QUESTIONS_FOR_FULL_LONGING)
        self.longing = _clamp(pressure * (0.4 + 0.6 * _clamp(persistence)))

    def answered(self) -> None:
        """أغلق سؤالاً. هذا أحلى ما يصيبه."""
        self.satisfaction = _clamp(self.satisfaction + 0.22)
        self.longing = _clamp(self.longing - 0.15)
        self.confusion = _clamp(self.confusion - 0.10)

    # ── ما الذي يريده الآن ───────────────────────────────────────────────
    def urge(self, has_questions: bool = False) -> str:
        """نزوعه في هذه اللحظة. هذا ما يختار الوجهة، لا العشوائية وحدها.

        الترتيب مقصود: التعب يسبق كل شيء (لا يفيد تجوّلٌ بلا انتباه)،
        ثم الحيرة، لأن من ضاع لا ينفعه مزيدٌ من الغريب.
        """
        if self.fatigue > 0.85:
            return "عودة"
        if self.confusion > 0.65:
            return "مألوف"        # يرجع لأرضٍ يعرفها ليربط عليها ما جمع
        if has_questions and self.longing > 0.35:
            return "سؤال"         # يلاحق سؤالاً فتحه ولم يغلقه
        if self.boredom > 0.55:
            return "غريب"         # يغيّر اللسان والباب معاً
        if self.curiosity > 0.6:
            return "تجوّل"
        return "تجوّل"

    def mood(self) -> str:
        """المزاج نتيجةٌ لحالته، لا قرعة. هذا ما يجعله يعني شيئاً."""
        if self.fatigue > 0.8:
            return "متعب"
        if self.confusion > 0.65:
            return "حائر"
        if self.boredom > 0.6:
            return "ضجِر"
        if self.longing > 0.6:
            return "مشغول بسؤال"
        if self.satisfaction > 0.65:
            return "منشرح"
        if self.curiosity > 0.7:
            return "متحفّز"
        return "صافٍ"

    def describe(self) -> str:
        rows = [
            ("الفضول", self.curiosity), ("الملل", self.boredom),
            ("الحيرة", self.confusion), ("الشوق", self.longing),
            ("التعب", self.fatigue), ("الرضا", self.satisfaction),
        ]
        width = max(len(n) for n, _ in rows)
        out = []
        for name, value in rows:
            bar = "█" * max(0, round(value * 20))
            out.append(f"{name:<{width}}  {bar:<20} {value:.2f}")
        return "\n".join(out)

    # ── الحفظ ────────────────────────────────────────────────────────────
    def dumps(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def loads(cls, raw: Optional[str]) -> "Drives":
        if not raw:
            return cls()
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return cls()
        if not isinstance(data, dict):      # ملفٌ عُبث به: نبدأ من جديد
            return cls()
        base = cls()
        for k, v in data.items():
            if hasattr(base, k) and isinstance(v, (int, float)):
                setattr(base, k, _clamp(float(v)))
        return base
