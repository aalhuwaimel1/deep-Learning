"""العقل — ما يحدث للمعلومة بين لحظة رؤيتها ولحظة استقرارها في الذاكرة.

طبقتان:
  • طبقة محلية دائماً حاضرة: تلخيص استخراجي واستخلاص مفاتيح، بلا إنترنت
    وبلا مفاتيح API. لا تهلوس لأنها لا تؤلّف — تختار جُملاً موجودة أصلاً.
  • طبقة اختيارية بنموذج لغوي (Claude) إن وُجد اعتماد: تلخّص بالعربية مهما
    كانت لغة المصدر، وتكتب يوميّات الرحلة بصوت الشخصية.

الكائن يعمل كاملاً بدون الطبقة الثانية. هي تحسين، لا شرط.
"""

from __future__ import annotations

import os
import textwrap
from typing import Optional

from . import lang as L
from .personality import Personality

MODEL = "claude-opus-5"
MAX_INPUT_CHARS = 12_000       # ما نرسله من نص الصفحة إلى النموذج


class LLM:
    """جسر رفيع إلى Claude. يبقى صامتاً إن لم يكن متاحاً."""

    def __init__(self, model: str = MODEL, effort: str = "low"):
        self.model = model
        self.effort = effort
        self.client = None
        self.reason = ""
        try:
            import anthropic  # type: ignore
        except ImportError:
            self.reason = "حزمة anthropic غير مثبّتة (pip install anthropic)"
            return
        try:
            # يقرأ ANTHROPIC_API_KEY أو ملف اعتماد ant auth login
            self.client = anthropic.Anthropic()
        except Exception as e:
            self.reason = f"تعذّر تهيئة العميل: {e}"

    @property
    def available(self) -> bool:
        return self.client is not None

    def ask(self, system: str, prompt: str, max_tokens: int = 1200) -> Optional[str]:
        """سؤال واحد، إجابة نصّية. None عند أي عطل — والمنادي يتدبّر أمره."""
        if not self.client:
            return None
        try:
            resp = self.client.beta.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort},
                # يحوّل الطلب تلقائياً إلى نموذج بديل إن رفضه المصنّف
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except Exception:
            try:                       # بيئة قديمة لا تعرف fallbacks
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                )
            except Exception:
                return None
        if getattr(resp, "stop_reason", None) == "refusal":
            return None
        parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        return "\n".join(parts).strip() or None


class Mind:
    """يهضم الصفحات ويكتب اليوميّات، بصوت الشخصية."""

    def __init__(self, personality: Personality, llm: Optional[LLM] = None,
                 use_llm: bool = True):
        self.p = personality
        self.llm = llm if llm is not None else (LLM() if use_llm else None)

    @property
    def has_llm(self) -> bool:
        return bool(self.llm and self.llm.available)

    # ── هضم صفحة ─────────────────────────────────────────────────────────
    def digest(self, title: str, text: str, page_lang: str) -> dict:
        """يحوّل صفحة خاماً إلى ذكرى: خلاصة + مفاتيح + وزن."""
        keywords = L.keywords(text, page_lang, top=12)
        summary = ""

        if self.has_llm:
            summary = self._llm_summary(title, text, page_lang) or ""
        if not summary:
            summary = L.summarize(text, page_lang, max_sentences=3)

        return {
            "summary": summary,
            "keywords": keywords,
            "importance": self._weigh(text, keywords),
        }

    def _llm_summary(self, title: str, text: str, page_lang: str) -> Optional[str]:
        system = (
            f"أنت العقل الداخلي لكائن اسمه {self.p.name}. {self.p.persona()} "
            "تُعطى صفحة من الإنترنت بأي لغة، فتكتب خلاصتها بالعربية في ثلاث "
            "جُمل على الأكثر. لا تضف معلومة ليست في النص. إن كان النص فارغاً "
            "أو بلا فائدة فاكتب: (لا شيء يستحق)."
        )
        prompt = (
            f"لغة الصفحة: {page_lang}\nالعنوان: {title}\n\nالنص:\n"
            f"{text[:MAX_INPUT_CHARS]}"
        )
        out = self.llm.ask(system, prompt, max_tokens=700) if self.llm else None
        if out and "لا شيء يستحق" in out:
            return None
        return out

    def _weigh(self, text: str, keywords: list[str]) -> float:
        """كم تستحق هذه الصفحة أن تُتذكّر؟ الطول والتنوّع وتقاطعها مع فضوله."""
        score = 0.35
        score += min(0.25, len(text) / 40_000)              # نصّ أطول ⇒ أغنى
        score += min(0.15, len(set(keywords)) / 60)         # تنوّع المفاتيح
        interests = {i.lower() for i in self.p.seed_interests}
        if any(k.lower() in interests for k in keywords):
            score += 0.2                                    # يمسّ ما يحبّه
        return round(min(1.0, score), 3)

    # ── يوميّات العودة ───────────────────────────────────────────────────
    def reflect(self, mood: str, visited: int, stored: int,
                langs: list[str], highlights: list[tuple[str, str]],
                state: Optional[dict] = None) -> str:
        """ما يكتبه عن نفسه بعد أن يعود. بصوته، لا بصوت تقرير.

        `state` حالته الداخلية: ما أراده، وما تعلّمه، وما سأل وما أجاب.
        بها تصير اليوميّات شهادةً على ما جرى له، لا إحصاءً لما فعل.
        """
        st = state or {}
        if self.has_llm:
            entry = self._llm_reflect(mood, visited, stored, langs, highlights, st)
            if entry:
                return entry
        return self._plain_reflect(mood, visited, stored, langs, highlights, st)

    def _llm_reflect(self, mood, visited, stored, langs, highlights,
                     st: dict) -> Optional[str]:
        system = (
            f"{self.p.persona()} "
            "عُدتَ للتوّ من تجوّل في الإنترنت. اكتب في يوميّاتك فقرة قصيرة "
            "(٤ جُمل على الأكثر) بضمير المتكلّم عمّا جرى لك — لا عمّا فعلت. "
            "إن مللت فقل إنك مللت، وإن حِرت فقل. لا تعدّد أرقاماً، ولا "
            "تتكلّف الحماس، ولا تختم بعبرة."
        )
        seen = "\n".join(f"- [{lg}] {t}" for t, lg in highlights[:8]) or "- لا شيء"
        lines = [
            f"مزاجي: {mood}",
            f"ما كنت أريده: {'، '.join(st.get('urges', [])) or 'التجوّل فحسب'}",
            f"زرت {visited} صفحة، احتفظت بـ {stored}.",
            f"اللغات: {', '.join(langs) or 'لا شيء'}",
        ]
        if st.get("answered"):
            lines.append(f"أسئلة أغلقتها أخيراً: {'، '.join(st['answered'][:5])}")
        if st.get("met"):
            lines.append(f"أسماء قابلتها لأوّل مرّة: {'، '.join(st['met'][:5])}")
        if st.get("asked"):
            lines.append(f"أشياء مرّت بي ولا أعرفها: {'، '.join(st['asked'][:5])}")
        if st.get("aspiration"):
            lines.append(f"سؤالي الكبير الذي لا يُجاب: {st['aspiration']}")
        if st.get("came_home_early"):
            lines.append("عدت قبل أن أُكمل — أنهكني الطريق.")
        prompt = "\n".join(lines) + f"\n\nأبرز ما مررت به:\n{seen}"
        return self.llm.ask(system, prompt, max_tokens=600) if self.llm else None

    def _plain_reflect(self, mood, visited, stored, langs, highlights,
                       st: dict) -> str:
        lines = [f"خرجت وأنا {mood}. مررت بـ {visited} صفحة واحتفظت بـ {stored}."]
        if st.get("came_home_early"):
            lines[0] += " عدت قبل أن أُكمل — أنهكني الطريق."
        if langs:
            lines.append(f"تجوّلت في: {'، '.join(langs)}.")
        if st.get("answered"):
            lines.append(f"أغلقت أخيراً: {'، '.join(st['answered'][:4])}.")
        if st.get("met"):
            lines.append(f"وقابلت لأوّل مرّة: {'، '.join(st['met'][:4])}.")
        if st.get("asked"):
            lines.append(f"ومرّ بي ما لا أعرفه: {'، '.join(st['asked'][:4])}.")
        if highlights:
            lines.append("أكثر ما علق بي:")
            lines += [f"  • [{lg}] {t}" for t, lg in highlights[:5]]
        return "\n".join(lines)

    # ── انجراف الفضول ────────────────────────────────────────────────────
    def drift(self, current: list[str], harvested: list[str], keep: int = 8) -> list[str]:
        """يمزج اهتماماته القديمة بما التقطه للتوّ، بنسبة يحدّدها فضوله.

        هذا هو الفرق بين كائن يتجوّل وبين سكربت يعيد نفس البحث كل يوم.
        """
        n_new = max(1, round(keep * self.p.curiosity))
        n_old = max(0, keep - n_new)
        fresh = [h for h in harvested if h not in current][:n_new]
        return (current[:n_old] + fresh)[:keep]


def describe_backend(mind: "Mind") -> str:
    if mind.has_llm:
        return f"العقل موصول بنموذج ({MODEL})"
    reason = mind.llm.reason if mind.llm else "معطّل بطلبك"
    return f"العقل يعمل محلياً بلا نموذج — {reason}"
