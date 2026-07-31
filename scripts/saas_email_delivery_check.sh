#!/bin/bash
# saas_email_delivery_check.sh — one-shot verification of the three
# 2026-07-31 saas.aunoo.ai changes, a day after they shipped:
#
#   1. correspondent brief EMAIL — the Newsroom-tier gate on outbound_email
#      removed, new correspondents defaulted to emailing their creator, and
#      the 22 pre-existing agents backfilled.
#   2. EDITOR LOCK — the direct-Postgres advisory-lock connect was timing
#      out on a busy worker event loop 52 times in 597 ticks (8.7%), each
#      one silently dropping that tenant's editorial serialization. Timeout
#      5s->15s plus 3 attempts. Expect a failure rate at or near zero.
#   3. EDITORIAL RATE — fabricated_claim rejections, whose dominant false
#      positive (claims grounded only in an article's summary, on citations
#      with no body) was fixed by adding summary to the grounding corpus.
#      Expect successes up and fabricated_claim near zero.
#
# Before the change: 13 of 35 active correspondents had a recipient, and 5
# of those had never delivered because the plan gate silently dropped them.
# After: 32 of 35 configured. This checks whether mail actually moved.
#
# Reports by email via Resend (key read from wileytest's .env, same as
# collector_health_check.sh) and logs to /var/log/aunoo-saas-email-check.log.
# Scheduled as a one-shot via `at`; does not reschedule itself.

set -u

CUTOVER='2026-07-31 20:45:00+02'   # when the email ungate went live
FIXED='2026-07-31 22:03:00'        # when the preflight + lock fixes deployed
# Both units run app.workers.pipeline_worker against the prod DB, so the
# editorial loop and its lock can log under either.
WORKER_UNITS="-u saas-worker.service -u saas-skills-worker.service"
DB=aunoo_saas_prod
LOG=/var/log/aunoo-saas-email-check.log
ALERT_TO="oliver.rochford@gmail.com"

RESEND_ENV=/home/orochford/tenants/wileytest.aunoo.ai/.env
RESEND_KEY=$(grep '^RESEND_API_KEY=' "$RESEND_ENV" 2>/dev/null | cut -d= -f2-)
RESEND_FROM=$(grep '^RESEND_FROM_EMAIL=' "$RESEND_ENV" 2>/dev/null | cut -d= -f2-)

ts() { date '+%Y-%m-%d %H:%M:%S'; }
# -t (tuples only) matters twice over: it keeps column headers out of the
# scalar values, and it makes an empty result an empty string so the
# ${VAR:-none} fallbacks below actually fire.
q() { sudo -u postgres psql -d "$DB" -X -A -t -F'  ' -c "$1" 2>&1; }

# --- gather -----------------------------------------------------------------

SENT=$(q "SELECT count(*) FROM outbound_logs
          WHERE channel='email' AND status='sent'
            AND created_at >= TIMESTAMPTZ '$CUTOVER'")
FAILED=$(q "SELECT count(*) FROM outbound_logs
            WHERE channel='email' AND status<>'sent'
              AND created_at >= TIMESTAMPTZ '$CUTOVER'")
RECIPS=$(q "SELECT count(DISTINCT recipient) FROM outbound_logs
            WHERE channel='email' AND status='sent'
              AND created_at >= TIMESTAMPTZ '$CUTOVER'")

BY_RECIPIENT=$(q "SELECT recipient, status, count(*) AS n,
                         to_char(max(created_at),'MM-DD HH24:MI') AS latest
                  FROM outbound_logs
                  WHERE channel='email' AND created_at >= TIMESTAMPTZ '$CUTOVER'
                  GROUP BY 1,2 ORDER BY 1,2")

# The real failure signal: a run found matches, the agent is configured to
# email, and yet no email row exists for that execution.
MISSED=$(q "SELECT a.id, a.name, e.matches_found,
                   to_char(e.completed_at,'MM-DD HH24:MI') AS ran
            FROM agent_executions e
            JOIN observer_agents a ON a.id = e.agent_id
            WHERE e.created_at >= TIMESTAMPTZ '$CUTOVER'
              AND e.matches_found > 0
              AND (a.config->>'send_email')::boolean IS TRUE
              AND NOT EXISTS (
                    SELECT 1 FROM outbound_logs o
                    WHERE o.execution_id = e.id AND o.channel='email')
            ORDER BY e.completed_at")

RUNS=$(q "SELECT count(*) FROM agent_executions
          WHERE created_at >= TIMESTAMPTZ '$CUTOVER'")
RUNS_MATCHED=$(q "SELECT count(*) FROM agent_executions
                  WHERE created_at >= TIMESTAMPTZ '$CUTOVER' AND matches_found > 0")

ERRORS=$(q "SELECT status, count(*) FROM outbound_logs
            WHERE channel='email' AND status<>'sent'
              AND created_at >= TIMESTAMPTZ '$CUTOVER'
            GROUP BY 1")

STILL_UNCONFIGURED=$(q "SELECT count(*) FROM observer_agents
                        WHERE is_active AND NOT (config ? 'email_recipients')")

# --- editor lock -------------------------------------------------------------
# Ticks are the denominator: a failure rate only means something against how
# many times the lock was actually attempted.
WLOG=$(journalctl $WORKER_UNITS --since "$FIXED" --no-pager 2>/dev/null)
TICKS=$(grep -c 'editorial_briefing: filtered' <<<"$WLOG")
LOCK_FAIL=$(grep -c 'direct lock connection failed' <<<"$WLOG")
LOCK_RETRY=$(grep -c 'editor lock connect attempt' <<<"$WLOG")
LOCK_ACQ_FAIL=$(grep -c 'advisory lock acquire failed' <<<"$WLOG")
if [ "${TICKS:-0}" -gt 0 ]; then
    LOCK_PCT=$(( LOCK_FAIL * 100 / TICKS ))
else
    LOCK_PCT="n/a"
fi

# --- editorial rate ----------------------------------------------------------
EDITORIAL=$(q "SELECT status,
                      coalesce(nullif(left(error,38),''),'-') AS err,
                      count(*)
               FROM editorial_briefing_runs
               WHERE started_at >= TIMESTAMP '$FIXED'
               GROUP BY 1,2 ORDER BY 3 DESC")
ED_OK=$(q "SELECT count(*) FROM editorial_briefing_runs
           WHERE started_at >= TIMESTAMP '$FIXED' AND status='success'")
ED_FAB=$(q "SELECT count(*) FROM editorial_briefing_runs
            WHERE started_at >= TIMESTAMP '$FIXED'
              AND error='editor_verdict:fabricated_claim'")
ED_TOTAL=$(q "SELECT count(*) FROM editorial_briefing_runs
              WHERE started_at >= TIMESTAMP '$FIXED' AND status<>'running'")
ED_STUCK=$(q "SELECT count(*) FROM editorial_briefing_runs
              WHERE started_at >= TIMESTAMP '$FIXED' AND status='running'")
if [ "${ED_TOTAL:-0}" -gt 0 ]; then
    ED_PCT=$(( ED_OK * 100 / ED_TOTAL ))
else
    ED_PCT="n/a"
fi
# Baselines to compare against, measured before the fixes went in.
ED_BASELINE="prior 30d: 356 fabricated_claim; 07-31 alone 13 (one tenant, one token)"
LOCK_BASELINE="prior 24h: 52 failures / 597 ticks = 8.7%"

# --- verdict ----------------------------------------------------------------

if [ "${SENT:-0}" -gt 0 ] && [ -z "$MISSED" ]; then
    VERDICT="PASS — $SENT email(s) delivered to $RECIPS recipient(s), no matched run went unmailed."
elif [ "${SENT:-0}" -gt 0 ]; then
    VERDICT="PARTIAL — $SENT email(s) sent, but some matched runs produced no email (listed below)."
else
    VERDICT="FAIL — no correspondent emails sent since the cutover."
fi

# Separate verdicts so one green area can't hide a red one in the subject.
if [ "${TICKS:-0}" -eq 0 ]; then
    LOCK_VERDICT="NO DATA — no editor ticks logged since the fix (journal rotated, or the loop is not running)."
elif [ "${LOCK_FAIL:-0}" -eq 0 ]; then
    LOCK_VERDICT="PASS — 0 lock failures in $TICKS ticks (was 8.7%)."
elif [ "${LOCK_PCT:-100}" -lt 3 ]; then
    LOCK_VERDICT="IMPROVED — $LOCK_FAIL/$TICKS = ${LOCK_PCT}% (was 8.7%)."
else
    LOCK_VERDICT="STILL FAILING — $LOCK_FAIL/$TICKS = ${LOCK_PCT}% (was 8.7%). Timeout/retry did not cover it."
fi

if [ "${ED_TOTAL:-0}" -eq 0 ]; then
    ED_VERDICT="NO DATA — no completed editorial runs since the fix."
elif [ "${ED_FAB:-0}" -eq 0 ]; then
    ED_VERDICT="PASS — 0 fabricated_claim in $ED_TOTAL completed runs (${ED_PCT}% success)."
else
    ED_VERDICT="$ED_FAB fabricated_claim in $ED_TOTAL completed runs (${ED_PCT}% success) — check whether it is a new false-positive class."
fi

BODY="saas.aunoo.ai — day-after check on the 2026-07-31 changes
Generated: $(ts)

  1. email delivery : $VERDICT
  2. editor lock    : $LOCK_VERDICT
  3. editorial rate : $ED_VERDICT

===============================================================
1. CORRESPONDENT EMAIL   (since $CUTOVER)
===============================================================
Totals
  emails sent      : ${SENT:-?}
  emails failed    : ${FAILED:-?}
  distinct inboxes : ${RECIPS:-?}
  agent runs       : ${RUNS:-?} (${RUNS_MATCHED:-?} of them found matches)
  active agents still without a recipient: ${STILL_UNCONFIGURED:-?}  (expected 3 - the @aunoo.test synthetics)

Per recipient (recipient / status / count / latest)
${BY_RECIPIENT:-  none}

Matched runs that sent no email (agent id / name / matches / ran)
${MISSED:-  none - good}

Non-sent statuses
${ERRORS:-  none}

Context: before 2026-07-31 the outbound_email feature was Newsroom-tier only
and sub-tier sends were dropped with a debug log. 19 agents were backfilled
to email their creator. First scheduled fires were 21:45 on 07-31 onward.

===============================================================
2. EDITOR LOCK   (since $FIXED)
===============================================================
$LOCK_VERDICT
  $LOCK_BASELINE

  editor ticks            : ${TICKS:-?}
  lock connect failures   : ${LOCK_FAIL:-?}   (-> ran unserialized)
  lock connect retries    : ${LOCK_RETRY:-?}   (recovered by the new retry)
  advisory acquire failed : ${LOCK_ACQ_FAIL:-?}

Retries > 0 with failures at 0 is the good outcome: the connect is still
losing races on a busy event loop, and the retry is now catching them.

===============================================================
3. EDITORIAL RATE   (since $FIXED)
===============================================================
$ED_VERDICT
  $ED_BASELINE

  completed runs   : ${ED_TOTAL:-?}
  succeeded        : ${ED_OK:-?}
  fabricated_claim : ${ED_FAB:-?}
  still running    : ${ED_STUCK:-?}   (a large number here is its own problem)

Breakdown (status / error / count)
${EDITORIAL:-  none}
"

echo "$(ts) ---- saas email delivery check ----" >> "$LOG"
echo "$BODY" >> "$LOG"

if [ -z "$RESEND_KEY" ]; then
    echo "$(ts) ERROR: RESEND_API_KEY not readable from $RESEND_ENV — report not emailed" >> "$LOG"
    exit 1
fi

SUBJECT="[aunoo] 07-31 changes day-after — email ${VERDICT%% *} / lock ${LOCK_VERDICT%% *} / editorial ${ED_VERDICT%% *}"
payload=$(python3 - "$RESEND_FROM" "$ALERT_TO" "$SUBJECT" "$BODY" <<'PYEOF'
import json, sys
print(json.dumps({"from": sys.argv[1], "to": [sys.argv[2]],
                  "subject": sys.argv[3], "text": sys.argv[4]}))
PYEOF
)
curl -s -m 30 -X POST https://api.resend.com/emails \
    -H "Authorization: Bearer $RESEND_KEY" \
    -H "Content-Type: application/json" \
    -d "$payload" >> "$LOG" 2>&1
echo >> "$LOG"
