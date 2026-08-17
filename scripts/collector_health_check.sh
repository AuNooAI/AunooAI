#!/bin/bash
# collector_health_check.sh — recurring test that each Aunoo tenant is still
# collecting news. Two checks per tenant:
#   1. heartbeat: app.tasks.keyword_monitor must have logged within the last
#      90 minutes (catches the 2026-07-11 class of failure where the monitor
#      loop hangs on a stuck HTTP call and everything else keeps running)
#   2. volume: at least FLOOR articles saved to the DB in the last 12 hours
# Alerts by email via Resend (key read from wileytest's .env) and logs to
# /var/log/aunoo-collector-health.log. Repeat alerts for the same condition
# are suppressed for 6 hours; a recovery clears the suppression.
# Installed in root's crontab: runs every 30 minutes.

set -u

# abbott removed 2026-07-16 — tenant shut down (service stopped+disabled, data retained)
# wbm added 2026-08-02 — it had never been covered here, and it is the tenant that
# then spent four weeks writing no embeddings without anything noticing.
TENANTS="bugfixing wileytest wiley wbm"
LOG=/var/log/aunoo-collector-health.log
STATE_DIR=/var/tmp/collector_health_state
ALERT_TO="oliver.rochford@gmail.com"
SUPPRESS_SECS=21600   # 6h between repeat alerts for the same condition

# per-tenant minimum articles in the last 12h (bugfixing runs low-volume
# per-group collection, so only alert there on total silence)
floor_for() {
    case "$1" in
        wileytest) echo 30 ;;
        wiley)     echo 10 ;;
        # wbm 12h buckets over 14 days to 2026-08-02: median 231, p10 74.
        # 20 sits well under the normal weekend dip and only fires on near-silence.
        wbm)       echo 20 ;;
        *)         echo 1  ;;
    esac
}

RESEND_ENV=/home/orochford/tenants/wileytest.aunoo.ai/.env
RESEND_KEY=$(grep '^RESEND_API_KEY=' "$RESEND_ENV" 2>/dev/null | cut -d= -f2-)
RESEND_FROM=$(grep '^RESEND_FROM_EMAIL=' "$RESEND_ENV" 2>/dev/null | cut -d= -f2-)

mkdir -p "$STATE_DIR"
ts() { date '+%Y-%m-%d %H:%M:%S'; }

send_email() {
    local subject="$1" body="$2"
    if [ -z "$RESEND_KEY" ]; then
        echo "$(ts) ERROR: RESEND_API_KEY not readable from $RESEND_ENV — cannot email" >> "$LOG"
        return 1
    fi
    local payload
    payload=$(python3 - "$RESEND_FROM" "$ALERT_TO" "$subject" "$body" <<'PYEOF'
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
}

alert() {
    local tenant="$1" check="$2" msg="$3"
    local state="$STATE_DIR/${tenant}_${check}"
    if [ -f "$state" ]; then
        local age=$(( $(date +%s) - $(stat -c %Y "$state") ))
        if [ "$age" -lt "$SUPPRESS_SECS" ]; then
            echo "$(ts) [$tenant] $check STILL FAILING (email suppressed, ${age}s since last): $msg" >> "$LOG"
            return
        fi
    fi
    touch "$state"
    echo "$(ts) [$tenant] ALERT $check: $msg" >> "$LOG"
    send_email "[aunoo/$tenant] news collection alert: $check" \
"Tenant:  $tenant.aunoo.ai
Check:   $check
Time:    $(ts)

$msg

Remediation: sudo systemctl restart $tenant.aunoo.ai.service
Log:     $LOG
This check runs every 30 min from root's crontab (collector_health_check.sh)."
}

recover() {
    local tenant="$1" check="$2"
    local state="$STATE_DIR/${tenant}_${check}"
    if [ -f "$state" ]; then
        rm -f "$state"
        echo "$(ts) [$tenant] RECOVERED: $check" >> "$LOG"
        send_email "[aunoo/$tenant] recovered: $check" "$tenant.aunoo.ai check '$check' is passing again as of $(ts)."
    fi
}

for t in $TENANTS; do
    svc="$t.aunoo.ai.service"
    envfile="/home/orochford/tenants/$t.aunoo.ai/.env"

    # Check 0: service running at all
    if ! systemctl is-active --quiet "$svc"; then
        alert "$t" "service_down" "systemd unit $svc is not active."
        continue
    fi
    recover "$t" "service_down"

    # Check 1: keyword monitor heartbeat in the journal
    if journalctl -q -u "$svc" --since '-90 min' --no-pager 2>/dev/null \
            | grep -q 'app\.tasks\.keyword_monitor'; then
        recover "$t" "keyword_monitor_stalled"
    else
        alert "$t" "keyword_monitor_stalled" \
"No app.tasks.keyword_monitor log lines in the last 90 minutes.
The collection loop is likely hung on a blocking call (this froze wileytest
for 2 days starting 2026-07-11 via a Firecrawl HTTP read with no timeout).
Everything else (HTTP, RSS) can look healthy while this is broken."
    fi

    # Check 2: articles actually landing in the DB
    DB=$(grep '^DB_NAME=' "$envfile" | cut -d= -f2)
    DBU=$(grep '^DB_USER=' "$envfile" | cut -d= -f2)
    DBP=$(grep '^DB_PASSWORD=' "$envfile" | cut -d= -f2)
    DBPORT=$(grep '^DB_PORT=' "$envfile" | cut -d= -f2)
    if [ -z "$DB" ] || [ -z "$DBU" ]; then
        alert "$t" "env_unreadable" "Could not read DB credentials from $envfile (encrypted?)."
        continue
    fi
    recover "$t" "env_unreadable"

    # submission_date is TEXT ('YYYY-MM-DD HH24:MI:SS...'); lexical compare is safe
    count=$(PGPASSWORD="$DBP" psql -h 127.0.0.1 -p "${DBPORT:-6432}" -U "$DBU" -d "$DB" -tAc \
        "SELECT COUNT(*) FROM articles WHERE submission_date >= to_char(now() - interval '12 hours', 'YYYY-MM-DD HH24:MI:SS')" 2>>"$LOG")
    if [ -z "$count" ]; then
        alert "$t" "db_query_failed" "Could not query article count from DB '$DB'."
        continue
    fi
    recover "$t" "db_query_failed"

    floor=$(floor_for "$t")
    if [ "$count" -lt "$floor" ]; then
        alert "$t" "low_article_volume" \
"Only $count articles saved in the last 12 hours (minimum expected: $floor).
Collectors may be failing upstream (API quotas, auth) even though the
keyword monitor loop is alive — check journalctl -u $svc."
    else
        recover "$t" "low_article_volume"
    fi

    echo "$(ts) [$t] OK: articles_12h=$count" >> "$LOG"
done
