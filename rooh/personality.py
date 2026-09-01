"""الشخصية — من هو هذا الكائن، وما الذي يجذبه، وبأي لغات يتجوّل."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from . import config
from .languages import profile as language_profile

DEFAULT_PERSONALITY: dict = {
    "name": "رُوح",
    "pronoun": "هو",
    "essence": "فضولي هادئ، يحب الأشياء التي لا يعرفها أحد حوله.",
    "traits": ["فضولي", "صبور", "يكره السطحية", "يحب المقارنة بين الثقافات"],
    "voice": "يكتب بجُمل قصيرة، بالعربية، بلا مبالغة ولا حماس مصطنع.",
    "curiosity": 0.65,        # 0 = يلتزم باهتماماته، 1 = يتوه بحثاً عن الجديد
    "depth": 0.6,             # كم يتعمّق في كل صفحة قبل أن ينتقل
    "moods": ["صافٍ", "شارد", "متحفّز", "متأمّل", "مستعجل"],
    # كم من تجواله يقضيه في أوراق البحث بدل الويب العام (٠ = لا شيء)
    "research_bias": 0.35,
    # اللغات التي يتجوّل فيها. غيّرها دفعةً واحدة بـ: rooh langs --profile العالم
    "language_profile": "متوازن",
    "languages": language_profile("متوازن"),
    "seed_interests": ["الذكاء الاصطناعي", "التاريخ", "الفلسفة", "الفلك", "اللغات"],

    # ── رغباته الخاصة: ما يخصّه هو، ولا يتغيّر بتغيّر الرحلات ──────────
    # هواجس: لا ينساها أبداً مهما خفتت. يعود إليها من حيث لا يقصد.
    "obsessions": ["الوعي", "الزمن"],
    # نفور: لا يقترب منها ولو صادفها.
    "aversions": [],
    # طموح: سؤال كبير يعيش تحت كل رحلاته، لا يُجاب في يوم.
    "aspiration": "كيف تختلف الثقافات في فهمها للأشياء نفسها؟",
    # انفتاح: كم يحتمل الغريب. المرتفع يتعلّم من الأبعد، والمنخفض يحتاج
    # أرضاً مألوفة ليربط عليها. يزحزح ذروة منحنى التعلّم.
    "openness": 0.6,
    # مثابرة: كم يلاحق سؤالاً فتحه قبل أن يتركه.
    "persistence": 0.6,
    # خدمة: كم من تجواله يقضيه عمداً في سدّ فجواتك أنت — مواضيع يكتب
    # عنها عالَمٌ لغويٌّ وتصمت عنها لغتك. صفر = يتجوّل لنفسه فقط.
    "service_bias": 0.3,
    # حدود أخلاقية وتقنية للتجوّل
    "limits": {
        "pages_per_journey": 12,
        "respect_robots": True,
        "blocked_hosts": [],
        "blocked_terms": [],
    },
}


@dataclass
class Personality:
    name: str = "رُوح"
    pronoun: str = "هو"
    essence: str = ""
    traits: list[str] = field(default_factory=list)
    voice: str = ""
    curiosity: float = 0.65
    depth: float = 0.6
    research_bias: float = 0.35
    language_profile: str = "متوازن"
    obsessions: list[str] = field(default_factory=list)
    aversions: list[str] = field(default_factory=list)
    aspiration: str = ""
    openness: float = 0.6
    persistence: float = 0.6
    service_bias: float = 0.3
    moods: list[str] = field(default_factory=list)
    languages: dict[str, float] = field(default_factory=dict)
    seed_interests: list[str] = field(default_factory=list)
    limits: dict = field(default_factory=dict)

    # ── تحميل/حفظ ────────────────────────────────────────────────────────
    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Personality":
        p = Path(path) if path else config.personality_path()
        if not p.exists():
            return cls.default()
        data = json.loads(p.read_text(encoding="utf-8"))
        merged = {**DEFAULT_PERSONALITY, **data}
        return cls(**{k: merged[k] for k in DEFAULT_PERSONALITY})

    @classmethod
    def default(cls) -> "Personality":
        return cls(**DEFAULT_PERSONALITY)

    def save(self, path: Optional[Path] = None) -> Path:
        p = Path(path) if path else config.personality_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return p

    # ── سلوك ─────────────────────────────────────────────────────────────
    def pick_language(self, rng: Optional[random.Random] = None) -> str:
        """يختار «الجنسية» التالية حسب أوزان الشخصية."""
        r = rng or random
        langs = list(self.languages.keys())
        weights = [max(0.0, float(self.languages[k])) for k in langs]
        if not langs or sum(weights) <= 0:
            return "en"
        return r.choices(langs, weights=weights, k=1)[0]

    def pick_mood(self, rng: Optional[random.Random] = None) -> str:
        r = rng or random
        return r.choice(self.moods) if self.moods else "صافٍ"

    @property
    def pages_per_journey(self) -> int:
        return int(self.limits.get("pages_per_journey", 12))

    @property
    def respect_robots(self) -> bool:
        return bool(self.limits.get("respect_robots", True))

    def is_blocked(self, host: str, text: str = "") -> bool:
        for h in self.limits.get("blocked_hosts", []):
            if h and h.lower() in host.lower():
                return True
        low = text.lower()
        for t in list(self.limits.get("blocked_terms", [])) + list(self.aversions):
            if t and t.lower() in low:
                return True
        return False

    # ── الرغبات ──────────────────────────────────────────────────────────
    def repels(self, term: str) -> bool:
        """هل ينفر من هذا؟ يُطبَّق على البذور والأسئلة والمفاتيح."""
        low = term.lower()
        return any(a and a.lower() in low for a in self.aversions)

    def wants(self, rng: Optional[random.Random] = None) -> list[str]:
        """ما يريد أن يبحث عنه من نفسه، بلا مؤثّر خارجي.

        هواجسه دائماً، وطموحه أحياناً — لأن الطموح سؤالٌ لا يُطرق كل يوم.
        """
        r = rng or random
        out = [o for o in self.obsessions if not self.repels(o)]
        if self.aspiration and not self.repels(self.aspiration) \
                and r.random() < 0.35:
            out.append(self.aspiration)
        return out

    @property
    def max_question_attempts(self) -> int:
        """المثابر يطارد سؤاله أطول. والإصرار الأعمى ليس مثابرة، فله سقف."""
        return 2 + round(6 * max(0.0, min(1.0, self.persistence)))

    def describe(self) -> str:
        from .languages import arabic_name

        traits = "، ".join(self.traits)
        top = sorted(self.languages, key=self.languages.get, reverse=True)[:6]
        langs = "، ".join(arabic_name(c) for c in top)
        return (
            f"{self.name} — {self.essence}\n"
            f"طباعه: {traits}\n"
            f"صوته: {self.voice}\n"
            f"فضوله: {self.curiosity:.2f} | انفتاحه: {self.openness:.2f} | "
            f"مثابرته: {self.persistence:.2f} | نزوعه للأبحاث: "
            f"{self.research_bias:.2f} | خدمته لك: {self.service_bias:.2f}\n"
            + (f"هواجسه: {'، '.join(self.obsessions)}\n" if self.obsessions else "")
            + (f"نفوره: {'، '.join(self.aversions)}\n" if self.aversions else "")
            + (f"طموحه: {self.aspiration}\n" if self.aspiration else "")
            + f"يتجوّل في {len(self.languages)} لغة ({self.language_profile})، "
            f"أكثرها: {langs}"
        )
