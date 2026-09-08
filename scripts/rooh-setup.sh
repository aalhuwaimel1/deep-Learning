#!/usr/bin/env bash
# تهيئةٌ كاملة بأمرٍ واحد: يجهّز البيت، ويفحص المصادر، ويهيّئ التوصيل،
# ويجرّب رحلةً حقيقية، ويجدول الدورة. آمنٌ للتكرار — لا يكسر ما بُني.
#
#   bash scripts/rooh-setup.sh
#
# ما لا يفعله: لا يكتب رمز تلغرام إلا إن أعطيته إيّاه، ولا يمسّ crontab
# قبل أن تأذن.

set -uo pipefail
ROOH_HOME="${ROOH_HOME:-$HOME/.rooh}"
export ROOH_HOME
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
ROOH="$PY $HERE/rooh.py"
CYCLE="$HERE/scripts/rooh-cycle.sh"

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  ✓ %s\n' "$*"; }
warn() { printf '  ⚠ %s\n' "$*"; }
# طرفيةٌ إن وُجدت، وإلا المُدخل القياسي: يُشغَّل أحياناً عبر ssh أو أنبوب.
ask()  {
  local p="$1" v=""
  if [ -r /dev/tty ] && [ -t 1 ]; then
    read -r -p "  $p " v </dev/tty || v=""
  else
    printf '  %s ' "$p"
    read -r v || v=""
    printf '\n'
  fi
  printf '%s' "$v"
}

say "١/٦ — فحص البيئة"
ver=$($PY -c 'import sys; print("%d.%d"%sys.version_info[:2])' 2>/dev/null) || {
  warn "لم أجد $PY. ثبّت بايثون ٣٫٩ فأحدث."; exit 1; }
ok "بايثون $ver"
$PY -c 'import sqlite3' 2>/dev/null && ok "sqlite متاح" || { warn "sqlite ناقص"; exit 1; }

say "٢/٦ — البيت والشخصية"
$ROOH init 2>&1 | sed 's/^/  /'

say "٣/٦ — حزمتان اختياريتان (تحسّنان ولا تُشترطان)"
if $PY -c 'import stopwordsiso' 2>/dev/null; then
  ok "stopwordsiso مثبّتة — قوائم توقّف لـ٥٨ لغة"
else
  a=$(ask "أثبّت stopwordsiso؟ (تحسّن جودة المفاتيح كثيراً) [y/N]")
  case "$a" in [yY]*) $PY -m pip install --quiet stopwordsiso && ok "ثُبّتت" || warn "أخفق التثبيت — يعمل بدونها";; *) warn "تخطّي";; esac
fi
if $PY -c 'import anthropic' 2>/dev/null; then
  ok "anthropic مثبّتة — تلخيصٌ ويوميّاتٌ بصوته"
else
  warn "anthropic غير مثبّتة — سيلخّص محلياً (أخشن، لكن لا يهلوس)"
fi

say "٤/٦ — فحص المصادر (الأهمّ قبل أن تتركه)"
out=$($ROOH sources --check 2>&1); echo "$out" | sed 's/^/  /'
dead=$(printf '%s' "$out" | grep -c '^✗' || true)
[ "$dead" -gt 0 ] && warn "$dead خلاصة معطّلة — احذفها من $ROOH_HOME/sources.json"

say "٥/٦ — قناة التوصيل"
ENV_FILE="$ROOH_HOME/env"
if [ -f "$ENV_FILE" ] && grep -q ROOH_TELEGRAM_TOKEN "$ENV_FILE" 2>/dev/null; then
  ok "تلغرام مهيّأ مسبقاً ($ENV_FILE)"
else
  echo "  لتصلك رسائله على جوّالك تحتاج بوت تلغرام."
  echo "  (تفاصيل الخطوات:  $ROOH notify --setup)"
  tok=$(ask "رمز البوت (أو Enter للتخطّي):")
  if [ -n "$tok" ]; then
    chat=$(ask "رقم المحادثة (chat id):")
    umask 077
    { echo "ROOH_TELEGRAM_TOKEN='$tok'"; echo "ROOH_TELEGRAM_CHAT='$chat'"; } > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    ok "حُفظ في $ENV_FILE (صلاحية 600 — لا يظهر في crontab ولا في ps)"
    set -a; . "$ENV_FILE"; set +a
    $ROOH notify --test 2>&1 | sed 's/^/  /'
  else
    warn "تخطّي — كل رسالة ستُكتب في $ROOH_HOME/outbox/ على أي حال"
  fi
fi

say "٦/٦ — رحلةٌ حقيقية أولى"
echo "  (هذي أوّل مرّة يخرج فيها إلى إنترنت حقيقي — قد تأخذ دقيقة)"
$ROOH wander -n 5 2>&1 | tail -20 | sed 's/^/  /'
echo
$ROOH status 2>&1 | sed 's/^/  /'

# الحكم على التهيئة يكون بما عاد به، لا بأن السكربت وصل آخره. تهيئةٌ
# تقول «جاهز» بعد رحلةٍ فارغة تكذب عليك بنفس طريقة الرسالة الفارغة.
GOT=$($ROOH status 2>/dev/null | sed -n 's/^ذكريات *: *\([0-9][0-9]*\).*/\1/p' | head -1)
GOT="${GOT:-0}"
READY=1
if [ "$GOT" -eq 0 ]; then
  READY=0
  printf '\n\033[1;33m  ⚠ الرحلة الأولى عادت بلا شيء — التهيئة غير مكتملة.\033[0m\n'
  echo "     لا تجدوله قبل أن تعرف السبب. الأرجح واحدٌ من هذه:"
  echo "       • لا إنترنت، أو جدارٌ يحجب الخروج"
  echo "       • كل الخلاصات معطّلة  →  $ROOH sources --check"
  echo "       • ويكيبيديا محجوبة عندك (وهي عمود التجوّل)"
  echo "     جرّب مباشرةً:  curl -sI https://ar.wikipedia.org | head -1"
fi

say "الجدولة"
line="0 * * * * $CYCLE >/dev/null 2>&1"
if [ "$READY" -eq 0 ]; then
  warn "تخطّي الجدولة: لا تُجدول ما لم يعمل مرّةً واحدة."
  echo "  بعد أن تصلحه:  bash $HERE/scripts/rooh-setup.sh"
elif crontab -l 2>/dev/null | grep -Fq "rooh-cycle.sh"; then
  ok "مجدول مسبقاً في crontab"
else
  echo "  السطر المقترح:"
  echo "    $line"
  a=$(ask "أضيفه إلى crontab؟ [y/N]")
  case "$a" in
    [yY]*) { crontab -l 2>/dev/null; echo "$line"; } | crontab - && ok "أُضيف" || warn "أخفق — أضفه يدوياً";;
    *) warn "لم يُضف. أضفه متى شئت بـ: crontab -e";;
  esac
fi

if [ "$READY" -eq 0 ]; then
cat <<EOF

════════════════════════════════════════════════
غير جاهز. أصلح ما فوق ثم أعد تشغيل هذا السكربت.
البيت والشخصية جاهزان — لا تُعاد تهيئتهما.
════════════════════════════════════════════════
EOF
exit 1
fi

cat <<EOF

════════════════════════════════════════════════
جاهز. ماذا تتوقّع:

  • كل ساعة  : رحلة
  • كل يوم   : لقطةٌ للقياس، ورسالةٌ تصلك
  • السجلّ    : $ROOH_HOME/cycle.log
  • الرسائل   : $ROOH_HOME/outbox/

⚠️ لا تمشِ قبل أن تقرأ رسائل أوّل ثلاثة أيام. إن تصدّرها ⚠️ فثمّة خلل،
   والرسالة تقول لك ما هو.

  اقرأ الآن   :  $ROOH daily --print --keep
  حالته       :  $ROOH drives
  ما جمع      :  $ROOH status
════════════════════════════════════════════════
EOF
