"""اللغة — استخلاص الكلمات المفتاحية من نصوص بأي كتابة.

المشكلة الحقيقية هنا: الصينية واليابانية لا تفصل الكلمات بمسافات، فتقطيع
النص بالمسافة يعطي «كلمة» واحدة طولها ألف حرف. لذلك نعالج الكتابات
اللاصقة (CJK) بثنائيّات الحروف، والباقي بالكلمات.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Optional

# ── نطاقات الكتابة ────────────────────────────────────────────────────────
_CJK = (
    (0x3040, 0x30FF),    # كانا يابانية
    (0x3400, 0x4DBF),    # هان موسّع
    (0x4E00, 0x9FFF),    # هان
    (0xF900, 0xFAFF),    # هان توافقي
    (0xAC00, 0xD7AF),    # هانغول كوري
)

#: كتابات لا تفصل كلماتها بفراغ («scriptio continua»)، وكم حرفاً نأخذ
#: في الوحدة الواحدة. الشرق الأقصى مقطعه حرفان؛ التايلندية وأخواتها
#: مقاطعها أطول فنأخذ ثلاثة.
_CONTINUOUS: dict[str, tuple[tuple[tuple[int, int], ...], int]] = {
    "cjk": (_CJK, 2),
    "thai": (((0x0E00, 0x0E7F),), 3),
    "lao": (((0x0E80, 0x0EFF),), 3),
    "khmer": (((0x1780, 0x17FF),), 3),
    "myanmar": (((0x1000, 0x109F),), 3),
    "tibetan": (((0x0F00, 0x0FFF),), 3),
}

#: علامات التشكيل والحركات (Mn/Mc/Me). بايثون لا يعدّها حروفاً، فـ
#: `\w` يقطع الكلمة عندها: «प्रसंस्करण» تصير «करण»، و«தமிழ்» تختفي
#: كلياً. نمسحها مرّة عند الإقلاع من النطاق الذي يسع كل كتابات العالم
#: الحيّة (٠x300–٠x2100) — نحو ٧ آلاف محرف، أجزاء من الثانية.
_MARKS = "".join(
    chr(cp) for cp in range(0x0300, 0x2100)
    if unicodedata.category(chr(cp)) in ("Mn", "Mc", "Me")
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
    "hi": set("""और या के का की को में से पर है हैं था थे यह वह इस उस एक भी नहीं
                 कि जो तो ही हो कर लिए साथ बाद तक कुछ सभी अपने द्वारा गया गई किया""".split()),
    "bn": set("""এবং বা কিন্তু এই সেই যে যা তা করে হয় হয়েছে ছিল থেকে জন্য সঙ্গে
                 উপর মধ্যে না ও এক আরও সব কিছু তার তাদের""".split()),
    "ur": set("""اور یا لیکن کے کا کی کو میں سے پر ہے ہیں تھا تھے یہ وہ ایک بھی
                 نہیں کہ جو تو ہی ہو کر لیے ساتھ بعد تک کچھ سب""".split()),
    "id": set("""dan atau tetapi yang di ke dari pada untuk dengan adalah ini itu
                 tidak akan sudah telah oleh dalam sebagai juga dapat lebih""".split()),
    "ms": set("""dan atau tetapi yang di ke dari pada untuk dengan adalah ini itu
                 tidak akan sudah telah oleh dalam sebagai juga boleh lebih""".split()),
    "vi": set("""và hoặc nhưng của cho với từ trong trên là các những một này đó
                 không được đã sẽ khi nếu vì cũng như để""".split()),
    "pt": set("""o a os as de do da dos das um uma e ou mas que quem como é são ser
                 estar em com por para sem sobre este esta esse essa não se seu""".split()),
    "nl": set("""de het een en of maar dat die dit deze is zijn was waren worden
                 heeft hebben niet ook als bij voor van met op in te""".split()),
    "sv": set("""och eller men att som är var vara har hade inte också för av med
                 till på den det en ett de vi jag han hon""".split()),
    "he": set("""של את על אל עם לא כי אם גם רק אבל או הוא היא הם הן זה זאת אשר
                 היה היו יש אין כל אחד""".split()),
    "uk": set("""і та або але що як це той цей вона він вони ми ви не так вже ще
                 для від до на у в з за про""".split()),
    "pl": set("""i lub ale że jak to ten ta te jest są był była nie tak już jeszcze
                 dla od do na w z za o się który która""".split()),
    "sw": set("""na au lakini ya wa kwa katika ni si hii hiyo huo ile kama pia
                 zaidi kila yote hata baada kabla""".split()),
    "ko": set("""그리고 그러나 하지만 또는 이것 그것 저것 있다 없다 하다 되다 아니다
                 위해 대한 통해 따라 에서 으로 에게""".split()),
}

# كلمات وظيفية شائعة في CJK لا تحمل معنى وحدها
_CJK_STOP = set("的了是在和有我你他她它们这那个不也就都很与及为以於之其而且或者について")

# الهيراغانا اليابانية قواعديّة في الغالب؛ الثنائيّة التي تحوي حرفاً منها
# تكون عادةً بقايا نحو («は人»، «である») لا مصطلحاً. نستبعدها ما لم يخلُ
# النص من غيرها.
_HIRAGANA = (0x3040, 0x309F)


def _is_hiragana(ch: str) -> bool:
    return _HIRAGANA[0] <= ord(ch) <= _HIRAGANA[1]

# حرف أو علامة تشكيل، متتالية. ثم نصفّي ما لا يحوي حرفاً حقيقياً.
_TOKEN_RE = re.compile(rf"(?:[^\W\d_]|[{re.escape(_MARKS)}])+", re.UNICODE)


def is_cjk_char(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _CJK)


def _continuous_script_of(ch: str) -> Optional[str]:
    cp = ord(ch)
    for name, (ranges, _n) in _CONTINUOUS.items():
        if any(lo <= cp <= hi for lo, hi in ranges):
            return name
    return None


def is_continuous(script: str) -> bool:
    """هل هذه كتابة بلا فراغات بين الكلمات؟"""
    return script in _CONTINUOUS


def script_of(text: str) -> str:
    """يخمّن الكتابة الغالبة.

    القيم: cjk | thai | lao | khmer | myanmar | tibetan | arabic |
    cyrillic | devanagari | tamil | latin | mixed …
    """
    counts: Counter = Counter()
    for ch in text[:4000]:
        if not ch.isalpha():
            continue
        cont = _continuous_script_of(ch)
        if cont:
            counts[cont] += 1
            continue
        try:
            name = unicodedata.name(ch)
        except ValueError:
            continue
        # اسم المحرف في يونيكود يبدأ باسم كتابته: «TAMIL LETTER A»
        head = name.split(" ")[0].lower()
        counts[head if head not in ("latin", "arabic", "cyrillic") else head] += 1
    if not counts:
        return "mixed"
    return counts.most_common(1)[0][0]


def _continuous_ngrams(text: str, script: str) -> list[str]:
    """وحدات من حروف متتالية داخل الكتابات التي لا فراغ فيها.

    الطول يختلف بالكتابة: حرفان للشرق الأقصى (حيث الحرفان ≈ كلمة)،
    وثلاثة للتايلندية وأخواتها (مقاطعها أطول).
    """
    ranges, n = _CONTINUOUS[script]
    in_script = lambda c: any(lo <= ord(c) <= hi for lo, hi in ranges)  # noqa: E731
    grams: list[str] = []
    kana_only: list[str] = []
    for run in re.findall(r"\S{2,}", text):
        chars = [c for c in run if in_script(c)]
        if len(chars) < n:
            continue
        for i in range(len(chars) - n + 1):
            g = "".join(chars[i : i + n])
            if any(c in _CJK_STOP for c in g):
                continue
            if script == "cjk" and any(_is_hiragana(c) for c in g):
                kana_only.append(g)
            else:
                grams.append(g)
    # نصّ ياباني خالص بلا كانجي: نقبل الهيراغانا بدل أن نعود بلا شيء
    return grams or kana_only


def tokenize(text: str, lang: str = "en") -> list[str]:
    """يقطّع النص إلى وحدات ذات معنى، حسب الكتابة لا حسب اللغة المعلنة."""
    script = script_of(text)
    if is_continuous(script):
        return _continuous_ngrams(text, script)
    stop = _STOPWORDS.get(lang, set()) | _STOPWORDS["en"]
    toks: list[str] = []
    for raw in _TOKEN_RE.findall(text):
        # الوحدة التي لا حرف فيها (تشكيل شارد) ليست كلمة
        if not any(c.isalpha() for c in raw):
            continue
        t = raw.lower()
        if len(t) > 2 and t not in stop:
            toks.append(t)
    return toks


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
# دَنْدا الهندية (।॥) ونقطة الميانمار (။) والخمير (។) حدود جُمل كاملة
# كالنقطة تماماً، ولا يلزمها فراغ بعدها.
_SENT_SPLIT = re.compile(
    r"(?<=[。！？｡।॥။។])\s*|(?<=[\.!\?؟۔])\s+|\n+"
)


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
