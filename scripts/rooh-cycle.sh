#!/usr/bin/env bash
# دورةٌ واحدة من حياة رُوح. مصمّمةٌ لتُنادى من cron كل ساعة، وأن تعمل
# أسبوعين بلا أن ينظر إليها أحد.
#
#   crontab -e  ثم:
#     0 * * * * ROOH_HOME=$HOME/.rooh /path/to/rooh-cycle.sh >/dev/null 2>&1
#
# ما يحرسه هذا السكربت:
#   • ألّا تتراكب دورتان (قفلٌ ذرّي بـ mkdir، يعمل حيث لا يوجد flock).
#   • ألّا تعلق دورةٌ إلى الأبد (مهلةٌ صارمة لكل أمر).
#   • ألّا يضيع سببُ الخلل (سجلٌّ يدوَّر، وخطأٌ يُسجَّل في الجسد).
#   • ألّا يُفوَّت اليوم (اللقطة والرسالة مرّةً كل يومٍ تقويمي، ولو
#     أخفقت الرحلات كلها — رسالةُ «أخفقت» أهمّ من لا رسالة).

set -uo pipefail

ROOH_HOME="${ROOH_HOME:-$HOME/.rooh}"
export ROOH_HOME

# cron لا يورّث بيئتك. والرمزُ في سطر crontab يظهر في ps ويُقرأ من ملفّ
# الجدولة، فنقرأه من ملفٍّ صلاحيّته 600 بدل ذلك.
if [ -f "$ROOH_HOME/env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOH_HOME/env"
  set +a
fi
ROOH_BIN="${ROOH_BIN:-}"
PAGES="${ROOH_PAGES:-8}"
WANDER_TIMEOUT="${ROOH_WANDER_TIMEOUT:-1800}"   # نصف ساعة لكل رحلة
LOG="$ROOH_HOME/cycle.log"
LOCK="$ROOH_HOME/.cycle.lock"
STAMP="$ROOH_HOME/.last-day"
MAX_LOG_BYTES=$((5 * 1024 * 1024))

mkdir -p "$ROOH_HOME"

# ── تحديد كيف نُشغّل رُوح ───────────────────────────────────────────────
if [ -z "$ROOH_BIN" ]; then
  if command -v rooh >/dev/null 2>&1; then
    ROOH_BIN="rooh"
  else
    HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    ROOH_BIN="${PYTHON:-python3} $HERE/rooh.py"
  fi
fi

log() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; }

# ── تدوير السجلّ قبل أي شيء، وإلا امتلأ القرص في أسبوعين ───────────────
if [ -f "$LOG" ]; then
  size=$(wc -c < "$LOG" 2>/dev/null || echo 0)
  if [ "$size" -gt "$MAX_LOG_BYTES" ]; then
    mv -f "$LOG" "$LOG.1" 2>/dev/null && log "دُوِّر السجلّ (كان $size بايت)"
  fi
fi

# ── قفلٌ ذرّي: mkdir ينجح لواحدٍ فقط ────────────────────────────────────
if ! mkdir "$LOCK" 2>/dev/null; then
  # قفلٌ يتيم من دورةٍ قُتلت: نحرّره بعد ساعتين
  if [ -d "$LOCK" ]; then
    age=$(( $(date +%s) - $(stat -c %Y "$LOCK" 2>/dev/null || stat -f %m "$LOCK" 2>/dev/null || date +%s) ))
    if [ "$age" -gt 7200 ]; then
      log "قفلٌ يتيم عمره ${age}ث — أُزيل"
      rmdir "$LOCK" 2>/dev/null && mkdir "$LOCK" 2>/dev/null || exit 0
    else
      log "دورةٌ أخرى تعمل — تخطّي"
      exit 0
    fi
  fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT INT TERM

run() {  # run <وصف> <مهلة> <أمر...>
  local what="$1" limit="$2"; shift 2
  local out rc
  out=$(timeout "$limit" "$@" 2>&1); rc=$?
  if [ $rc -eq 0 ]; then
    log "$what: تمّ"
  elif [ $rc -eq 124 ]; then
    log "$what: انتهت المهلة (${limit}ث)"
  else
    log "$what: أخفق (رمز $rc) — $(printf '%s' "$out" | tail -3 | tr '\n' ' ')"
  fi
  return $rc
}

# ── الرحلة ──────────────────────────────────────────────────────────────
log "── بدء الدورة (ROOH_HOME=$ROOH_HOME) ──"
run "رحلة" "$WANDER_TIMEOUT" $ROOH_BIN wander -n "$PAGES" -q || true

# ── مرّةً كل يومٍ تقويمي: لقطةٌ ورسالة ──────────────────────────────────
TODAY="$(date '+%Y-%m-%d')"
LAST="$(cat "$STAMP" 2>/dev/null || echo '')"
if [ "$TODAY" != "$LAST" ]; then
  log "يومٌ جديد ($TODAY)"
  run "لقطة" 300 $ROOH_BIN snapshot --json >/dev/null || true
  # الرسالة تُرسل حتى لو أخفقت الرحلات: «أخفقت» خبرٌ يجب أن يصلك
  if run "رسالة اليوم" 300 $ROOH_BIN daily; then
    printf '%s' "$TODAY" > "$STAMP"
  else
    log "لم تُرسل رسالة اليوم — سيُعاد في الدورة القادمة"
  fi
fi

log "── انتهت الدورة ──"
exit 0
