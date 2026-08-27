"""اللغة — استخلاص الكلمات المفتاحية من نصوص بأي كتابة.

المشكلة الحقيقية هنا: الصينية واليابانية لا تفصل الكلمات بمسافات، فتقطيع
النص بالمسافة يعطي «كلمة» واحدة طولها ألف حرف. لذلك نعالج الكتابات
اللاصقة (CJK) بثنائيّات الحروف، والباقي بالكلمات.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

# ── نطاقات الكتابة ────────────────────────────────────────────────────────
_CJK = (
    (0x3040, 0x30FF),    # كانا يابانية
    (0x3400, 0x4DBF),    # هان موسّع
    (0x4E00, 0x9FFF),    # هان
    (0xF900, 0xFAFF),    # هان توافقي
    (0xAC00, 0xD7AF),    # هانغول كوري
)

_STOPWORDS: dict[str, set[str]] = {
    "ar": set("""في من على عن إلى مع هذا هذه ذلك تلك التي الذي الذين كان كانت يكون
                 قد لقد ثم أو أم لا ما لم لن إن أن إذا حتى كل بعض غير بين عند لدى
                 هو هي هم هن نحن أنا أنت بعد قبل حيث كما أيضا كذلك لكن بل""".split()),
    "en": set("""the a an and or but if then than that this these those of in on at to
                 for from with without by as is are was were be been being have has had
                 do does did not no its it he she they we you i his her their our your
                 which who whom what when where why how all any some more most other""".split()),
    "ru": set("""и в во не что он на я с со как а то все она так его но да ты к у же
                 вы за бы по только ее мне было вот от меня еще нет о из ему теперь
                 когда даже ну вдруг ли если уже или ни быть был него до вас""".split()),
    "fr": set("""le la les de des du un une et ou mais donc or ni car en dans sur pour
                 par avec sans que qui quoi dont est sont être avoir ce cet cette ces""".split()),
    "de": set("""der die das den dem des ein eine einer und oder aber ist sind war waren
                 sein haben hat hatte nicht auch als bei für von mit auf im in zu""".split()),
    "es": set("""el la los las de del un una y o pero que quien como es son ser estar
                 en con por para sin sobre este esta estos esas no se su sus""".split()),
    "tr": set("""ve veya ama ile bir bu şu o için gibi çok daha en olan olarak da de
                 ki mi mı ne nasıl değil""".split()),
    "fa": set("""و یا اما با از به در که این آن را برای هم یک است بود می نمی هر تا بر""".split()),
}

# كلمات وظيفية شائعة في CJK لا تحمل معنى وحدها
_CJK_STOP = set("的了是在和有我你他她它们这那个不也就都很与及为以於之其而且或者について")

# الهيراغانا اليابانية قواعديّة في الغالب؛ الثنائيّة التي تحوي حرفاً منها
# تكون عادةً بقايا نحو («は人»، «である») لا مصطلحاً. نستبعدها ما لم يخلُ
# النص من غيرها.
_HIRAGANA = (0x3040, 0x309F)


def _is_hiragana(ch: str) -> bool:
    return _HIRAGANA[0] <= ord(ch) <= _HIRAGANA[1]

_TOKEN_RE = re.compile(r"[^\W\d_]{2,}", re.UNICODE)


def is_cjk_char(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _CJK)


def script_of(text: str) -> str:
    """يخمّن الكتابة الغالبة: cjk | arabic | cyrillic | latin | mixed."""
    counts = Counter()
    for ch in text[:4000]:
        if not ch.isalpha():
            continue
        if is_cjk_char(ch):
            counts["cjk"] += 1
            continue
        try:
            name = unicodedata.name(ch)
        except ValueError:
            continue
        if "ARABIC" in name:
            counts["arabic"] += 1
        elif "CYRILLIC" in name:
            counts["cyrillic"] += 1
        elif "LATIN" in name:
            counts["latin"] += 1
    if not counts:
        return "mixed"
    return counts.most_common(1)[0][0]


def _cjk_ngrams(text: str, n: int = 2) -> list[str]:
    """ثنائيّات الحروف داخل المقاطع الصينية/اليابانية/الكورية المتّصلة."""
    grams: list[str] = []
    kana_only: list[str] = []
    for run in re.findall(r"[^\s\W]{2,}", text):
        chars = [c for c in run if is_cjk_char(c)]
        if len(chars) < n:
            continue
        for i in range(len(chars) - n + 1):
            g = "".join(chars[i : i + n])
            if any(c in _CJK_STOP for c in g):
                continue
            if any(_is_hiragana(c) for c in g):
                kana_only.append(g)
            else:
                grams.append(g)
    # نصّ ياباني خالص بلا كانجي: نقبل الهيراغانا بدل أن نعود بلا شيء
    return grams or kana_only


def tokenize(text: str, lang: str = "en") -> list[str]:
    """يقطّع النص إلى وحدات ذات معنى، حسب الكتابة لا حسب اللغة المعلنة."""
    script = script_of(text)
    if script == "cjk":
        return _cjk_ngrams(text)
    stop = _STOPWORDS.get(lang, set()) | _STOPWORDS["en"]
    toks = [t.lower() for t in _TOKEN_RE.findall(text)]
    return [t for t in toks if t not in stop and len(t) > 2]


def keywords(text: str, lang: str = "en", top: int = 10) -> list[str]:
    """أبرز المفاتيح في النص. ترتيب بالتكرار مع تفضيل الوحدات الأطول قليلاً."""
    toks = tokenize(text, lang)
    if not toks:
        return []
    freq = Counter(toks)
    scored = {t: c * (1 + min(len(t), 12) / 40) for t, c in freq.items() if c > 1}
    if not scored:
        scored = {t: float(c) for t, c in freq.items()}
    ranked = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)
    return [t for t, _ in ranked[:top]]


# الفواصل الشرقية (。！？) لا يتبعها فراغ، فنقسم عندها بعرض صفري.
_SENT_SPLIT = re.compile(r"(?<=[。！？｡])\s*|(?<=[\.!\?؟۔])\s+|\n+")


def summarize(text: str, lang: str = "en", max_sentences: int = 3) -> str:
    """تلخيص استخراجي: نختار الجُمل الأغنى بالمفاتيح، ونحفظ ترتيبها الأصلي.

    هذا هو الاحتياطي حين لا يتوفّر نموذج لغوي. بسيط، لكنه لا يهلوس.
    """
    # نسحق الفراغات الأفقية فقط ونُبقي الأسطر: السطر حدّ جملة في النصّ
    # المستخرَج من HTML. لو سحقناه لالتصق عنوان الصفحة بأول جملة، فصارت
    # «جملة» لا تُطابق تكرارها لاحقاً فينجو التكرار من التنقية.
    text = re.sub(r"[ \t\r\f\v]+", " ", text or "").strip()
    if not text:
        return ""
    seen: set[str] = set()
    sentences: list[str] = []
    for s in _SENT_SPLIT.split(text):
        s = re.sub(r"\s+", " ", s).strip()
        # صفحات كثيرة تكرّر المقدّمة في أكثر من موضع؛ خلاصة تعيد الجملة
        # مرّتين ليست خلاصة.
        if len(s) > 20 and s not in seen:
            seen.add(s)
            sentences.append(s)
    if not sentences:
        return text[:400]
    if len(sentences) <= max_sentences:
        return " ".join(sentences)

    key_set = set(keywords(text, lang, top=25))
    scores: list[tuple[int, float]] = []
    for i, s in enumerate(sentences):
        toks = tokenize(s, lang)
        if not toks:
            scores.append((i, 0.0))
            continue
        overlap = sum(1 for t in toks if t in key_set) / len(toks)
        position_bonus = 1.15 if i == 0 else 1.0   # الجملة الأولى عادةً تعريفية
        scores.append((i, overlap * position_bonus))

    best = sorted(scores, key=lambda kv: kv[1], reverse=True)[:max_sentences]
    chosen = sorted(i for i, _ in best)
    return " ".join(sentences[i] for i in chosen)
