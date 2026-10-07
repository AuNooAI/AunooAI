#!/bin/bash
# collector_health_check.sh — recurring test that each Aunoo tenant is still
# collecting news. Two checks per tenant:
#   1. heartbeat: app.tasks.keyword_monitor must have logged within the last
#      90 minutes (catches the 2026-07-11 class of failure where the monitor
#      loop hangs on a stuck HTTP call and everything else keeps running)
#   2. volume: at least FLOOR articles saved to the DB in the last 12 hours
#   3. collection health: GET /api/health/collection on the tenant's own port
#      and relay its "alerts" list (stalled checkpoints, overdue providers,
#      feeds failing >24h, configuration-blocked articles). Tenants without
#      the endpoint (non-200) are skipped.
# Alerts by email via Resend (key read from wileytest's .env) and logs to
# /var/log/aunoo-collector-health.log. Repeat alerts for the same condition
# are suppressed for 6 hours; a recovery clears the suppression.
# Installed in root's crontab: runs every 30 minutes.

set -u

# abbott removed 2026-07-16 — tenant shut down (service stopped+disabled, data retained)
# wbm added 2026-08-02 — it had never been covered here, and it is the tenant that
# then spent four weeks writing no embeddings without anything noticing.
# wiley + pearson removed 2026-08-12 — both services stopped during the Aug 11-12
# load incident (wiley: not production; pearson: revived for testing then shut down).
# They were emitting service_down every 6 h with nothing to fix. RE-ADD THEM HERE
# when either service is started again, or the tenant runs unwatched.
# 7 Oct 2026: wiley is running again (re-added per the note above), and
# abm, oviva, panaya and sunstar had never been covered. Check 3 (the app's
# /api/health/collection alerts, incl. stalled checkpoints) merged in from the
# repo copy, where it had been written but never deployed.
TENANTS="bugfixing wileytest wiley wbm abm oviva panaya sunstar"
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

. /home/orochford/bin/discord_notify.sh

send_email() {
    local subject="$1" body="$2"
    discord_notify "$subject" "$body" "$LOG"
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
    # --fail-with-body: HTTP 4xx/5xx exit non-zero so callers can tell a
    # rejected email from a delivered one (2026-08-10 review finding).
    if curl -s -m 30 --fail-with-body -X POST https://api.resend.com/emails \
        -H "Authorization: Bearer $RESEND_KEY" \
        -H "Content-Type: application/json" \
        -d "$payload" >> "$LOG" 2>&1; then
        echo >> "$LOG"
        return 0
    else
        echo " <- RESEND DELIVERY FAILED" >> "$LOG"
        return 1
    fi
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
    echo "$(ts) [$tenant] ALERT $check: $msg" >> "$LOG"
    # Host-level checks have no <tenant>.aunoo.ai.service to restart; the
    # generic remediation line only applies to real tenant units.
    local remediation=""
    if [ "$tenant" != "host" ]; then
        remediation="Remediation: sudo systemctl restart $tenant.aunoo.ai.service
"
    fi
    # Suppression starts only after CONFIRMED delivery — a failed email must
    # not silence retries for 6 hours (2026-08-10 review finding).
    if send_email "[aunoo/$tenant] news collection alert: $check" \
"Tenant:  $tenant.aunoo.ai
Check:   $check
Time:    $(ts)

$msg

${remediation}Log:     $LOG
This check runs every 30 min from root's crontab (collector_health_check.sh)."; then
        touch "$state"
    else
        echo "$(ts) [$tenant] $check alert email FAILED — suppression not set, will retry next run" >> "$LOG"
    fi
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

# Collection-health alerts from the tenant's own endpoint, one per line.
# Prints nothing on non-200 (older tenants do not have the endpoint) or on
# unparseable JSON; the caller treats "nothing" as "no alerts".
collection_alerts() {
    local port="$1" body code
    body=$(mktemp)
    code=$(curl -s -m 30 -o "$body" -w '%{http_code}' \
        -H 'X-Forwarded-Proto: https' \
        "http://127.0.0.1:${port}/api/health/collection" 2>>"$LOG")
    if [ "$code" = "200" ]; then
        python3 - "$body" <<'PYEOF' 2>>"$LOG"
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
for line in data.get("alerts") or []:
    print(str(line).replace("\n", " "))
PYEOF
    fi
    rm -f "$body"
    [ "$code" = "200" ]
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

    # Check 3: the app's own collection-health view (runs, feeds, quota)
    PORT=$(grep '^PORT=' "$envfile" | cut -d= -f2)
    PORT=${PORT:-10015}
    if ch_alerts=$(collection_alerts "$PORT"); then
        if [ -n "$ch_alerts" ]; then
            alert "$t" "collection_health" \
"GET http://127.0.0.1:$PORT/api/health/collection reports:

$ch_alerts

Providers that only return zero items do not appear here; these are runs
that have not succeeded for two expected intervals, continuations left
pending, feeds failing for more than a day, and articles the ingest held
back because the topic configuration blocks them."
        else
            recover "$t" "collection_health"
        fi
    else
        echo "$(ts) [$t] collection_health endpoint not available on port $PORT (skipped)" >> "$LOG"
    fi

    echo "$(ts) [$t] OK: articles_12h=$count" >> "$LOG"
done

# ── Host-level checks (added 2026-08-10, Phase 4 of the firehose remediation
#    plan). Absolute thresholds — the 7-day baseline is contaminated by the
#    2026-08-04..10 read-storm incident. Uses the same alert/suppress/recover
#    machinery with pseudo-tenant "host". ────────────────────────────────────

SARFILE="/var/log/sysstat/sa$(date +%d)"
# Midnight boundary: 31 minutes before 00:00-00:30 lands on YESTERDAY's clock
# time (23:29-23:59), but SARFILE is today's, whose rows all sit after 00:00.
# sar's -s filter compares clock times within the one file, so it matched
# nothing and the check fail-closed every night at 00:00 and 00:30
# (observed 2026-08-13). Clamp to 00:00:00 and measure the shorter window.
if [ "$(date -d '-31 min' +%d)" != "$(date +%d)" ]; then
    SINCE30="00:00:00"
else
    SINCE30=$(date -d '-31 min' +%H:%M:%S)
fi

# A measurement that cannot be taken must alert as monitor_failed, and must
# NEVER recover the condition it was supposed to measure (a dead monitor
# would otherwise clear a live alert) — 2026-08-10 review finding.
mfail() {
    # Per-check failure state (monitor_failed_<name>) so one healthy monitor
    # cannot clear another's failure alert (2026-08-10 review, round 2).
    alert "host" "monitor_failed_$1" "Monitoring check '$1' could not take its measurement: $2"
}
mrecover() { recover "host" "monitor_failed_$1"; }

# H1: md2 sustained reads. Storm signature was 119→934 MB/s daily averages;
#     50 MB/s over 30 min is far above any healthy steady state while
#     tolerating backup transfers shorter than the window.
#     Column positions are VERIFIED against the sar header before use
#     (Average rows: no AM/PM column, so rkB/s=$3, aqu-sz=$7 — interval
#     rows differ; this bit us once already).
SAROUT=$(sar -d -p -f "$SARFILE" -s "$SINCE30" 2>/dev/null)
SARHDR_OK=$(echo "$SAROUT" | awk '$3=="tps" && $4=="rkB/s" && $8=="aqu-sz" && $NF=="DEV" {print "ok"; exit}')
MD2=$(echo "$SAROUT" | awk '/^Average:/ && $NF=="md2" && NF==10 {printf "%d %d", $3/1024, $7+0}')
MD2_MBS=${MD2%% *}; MD2_AQU=${MD2##* }
if [ "$SARHDR_OK" != "ok" ] || [ -z "$MD2_MBS" ]; then
    mfail "sar" "sar output missing, header format changed, or md2 Average row absent (file: $SARFILE)."
else
    if [ "$MD2_MBS" -gt 50 ]; then
        alert "host" "md2_read_storm" \
"md2 30-min average read rate is ${MD2_MBS} MB/s (threshold 50).
This is the 2026-08 read-storm signature. Check pidstat -d for the reader;
if it is postgres backends on port 5431, see docs/FIREHOSE_SEARCH_REMEDIATION_PLAN.md."
    else
        recover "host" "md2_read_storm"
    fi
    if [ "$MD2_AQU" -gt 8 ]; then
        alert "host" "md2_queue_depth" "md2 30-min average queue depth is ${MD2_AQU} (threshold 8)."
    else
        recover "host" "md2_queue_depth"
    fi
    mrecover "sar"
fi

# H2: stuck or stacked firehose searches (server-side view)
NFPW=$(docker inspect aunooscraper_pg --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep POSTGRES_PASSWORD | cut -d= -f2)
if [ -z "$NFPW" ]; then
    mfail "firehose_queries" "could not read newsdb credentials from docker inspect."
    :
else
    NFQ=$(PGPASSWORD="$NFPW" psql -h 127.0.0.1 -p 5431 -U user -d newsdb -tAc \
        "SELECT count(*) FILTER (WHERE state='active') || ' ' || coalesce(max(EXTRACT(epoch FROM now()-query_start)) FILTER (WHERE state='active'),0)::int FROM pg_stat_activity WHERE usename='nf_search'" 2>>"$LOG")
    NF_ACTIVE=${NFQ%% *}; NF_MAXAGE=${NFQ##* }
    if [ -z "$NF_ACTIVE" ] || [ -z "$NF_MAXAGE" ]; then
        mfail "firehose_queries" "pg_stat_activity query against newsdb returned nothing (auth/connectivity)."
    else
        mrecover "firehose_queries"
        if [ "$NF_MAXAGE" -gt 120 ]; then
            alert "host" "firehose_stuck_query" "An nf_search query has been active for ${NF_MAXAGE}s (>120s despite the 60s statement_timeout — investigate)."
        else
            recover "host" "firehose_stuck_query"
        fi
        # Role CONNECTION LIMIT is 2: three active already means the
        # protection is bypassed — alert at >2, not >4 (review finding).
        if [ "$NF_ACTIVE" -gt 2 ]; then
            alert "host" "firehose_query_stacking" "${NF_ACTIVE} concurrent nf_search backends (role limit is 2 — limit bypass or role misconfig)."
        else
            recover "host" "firehose_query_stacking"
        fi
    fi
fi

# H3: client-side firehose error rate across tenant units (last hour).
# journalctl exit status is validated first — a dead journalctl piped into
# grep -c would read as "0 errors" (fail-closed, review round 2).
if JOUT=$(journalctl -q --since '-60 min' --no-pager -u bugfixing.aunoo.ai.service -u wileytest.aunoo.ai.service -u wiley.aunoo.ai.service -u wbm.aunoo.ai.service 2>/dev/null); then
    mrecover "client_errors"
    CERR=$(printf '%s' "$JOUT" | grep -cE 'NewsFirehose.*(Timeout|timeout|HTTP ERROR|status=(400|429|500))')
    if [ "${CERR:-0}" -gt 20 ]; then
        alert "host" "firehose_client_errors" "${CERR} NewsFirehose client error/timeout log lines in the last hour (threshold 20; the Aug 6 escalation jumped 4/day to 92/day)."
    else
        recover "host" "firehose_client_errors"
    fi
else
    mfail "client_errors" "journalctl query over tenant units failed."
fi

# H4: slow statements logged by the scraper postgres (log_min_duration=10s)
if DLOG=$(docker logs aunooscraper_pg --since 30m 2>&1); then
    mrecover "slow_queries"
    SLOW=$(printf '%s' "$DLOG" | grep -c 'duration: ')
    if [ "${SLOW:-0}" -gt 5 ]; then
        alert "host" "firehose_slow_queries" "${SLOW} statements over 10s logged by aunooscraper_pg in the last 30 min (threshold 5)."
    else
        recover "host" "firehose_slow_queries"
    fi
else
    mfail "slow_queries" "docker logs aunooscraper_pg failed."
fi

# H5: newsdb physical read growth (blks_read delta per 30-min run > 5 GB ≙ 10 GB/h)
if [ -z "$NFPW" ]; then
    mfail "read_growth" "could not read newsdb credentials from docker inspect."
else
    BR=$(PGPASSWORD="$NFPW" psql -h 127.0.0.1 -p 5431 -U user -d newsdb -tAc "SELECT blks_read FROM pg_stat_database WHERE datname='newsdb'" 2>>"$LOG")
    if [ -z "$BR" ]; then
        mfail "read_growth" "blks_read query against newsdb returned nothing."
    else
        mrecover "read_growth"
        PREV_F="$STATE_DIR/newsdb_blks_read"
        PREV=$(cat "$PREV_F" 2>/dev/null || echo "")
        # Every valid measurement must be able to recover the alert:
        # first sample and stats-reset re-baseline; equal means no reads
        # (2026-08-10 review, round 3).
        if [ -z "$PREV" ] || [ "$BR" -lt "$PREV" ]; then
            echo "$BR" > "$PREV_F"
            recover "host" "newsdb_read_growth"
        elif [ "$BR" -eq "$PREV" ]; then
            recover "host" "newsdb_read_growth"
        else
            DELTA_GB=$(( (BR - PREV) * 8 / 1048576 ))
            echo "$BR" > "$PREV_F"
            if [ "$DELTA_GB" -gt 5 ]; then
                alert "host" "newsdb_read_growth" "newsdb read ${DELTA_GB} GB from disk/cache in ~30 min (threshold 5 GB; storm rate was ~17 GB per query)."
            else
                recover "host" "newsdb_read_growth"
            fi
        fi
    fi
fi

# H6: memory pressure and OOM kills (float-safe compare — %d truncated
# 5.9 to 5 and could never fire at the stated threshold; review finding)
PSI=$(awk '/^full/ {for(i=1;i<=NF;i++) if($i ~ /^avg300=/){split($i,a,"="); print a[2]}}' /proc/pressure/memory)
PSI_HIGH=$(awk -v v="${PSI:-0}" 'BEGIN{print (v > 5.0) ? "yes" : "no"}')
if [ -z "$PSI" ]; then
    mfail "memory_psi" "could not read /proc/pressure/memory."
elif [ "$PSI_HIGH" = "yes" ]; then
    mrecover "memory_psi"
    alert "host" "memory_pressure" "memory PSI full avg300 is ${PSI}% (threshold 5%). The Aug 4-9 cache collapse started this way."
else
    mrecover "memory_psi"
    recover "host" "memory_pressure"
fi
if KOUT=$(journalctl -k -q --since '-30 min' --no-pager 2>/dev/null); then
    mrecover "oom"
    if printf '%s' "$KOUT" | grep -q 'Out of memory: Killed'; then
        alert "host" "oom_kill" "Kernel OOM-killed a process within the last 30 minutes. See dmesg -T | grep -i oom."
    else
        recover "host" "oom_kill"
    fi
else
    mfail "oom" "journalctl -k query failed; OOM state unknown."
fi

# H7: RAID member-state change (md2 is already degraded [UU_]; alert on ANY change)
MDSIG=$(grep -oE '\[[U_]+\]' /proc/mdstat 2>/dev/null | tr '\n' ' ')
SIG_F="$STATE_DIR/mdstat_signature"
PREV_SIG=$(cat "$SIG_F" 2>/dev/null || echo "")
if [ -z "$MDSIG" ]; then
    mfail "mdstat" "could not read RAID member signature from /proc/mdstat."
elif [ -z "$PREV_SIG" ]; then
    mrecover "mdstat"
    echo "$MDSIG" > "$SIG_F"
elif [ "$MDSIG" != "$PREV_SIG" ]; then
    mrecover "mdstat"
    alert "host" "raid_state_change" "RAID member signature changed: '$PREV_SIG' -> '$MDSIG'. md2 has NO redundancy; a further member loss is data loss."
    echo "$MDSIG" > "$SIG_F"
else
    mrecover "mdstat"
    recover "host" "raid_state_change"
fi

echo "$(ts) [host] OK: md2=${MD2_MBS:-?}MB/s aqu=${MD2_AQU:-?} nf_active=${NF_ACTIVE:-?} cerr=${CERR:-0} slow=${SLOW:-0} psi=${PSI:-0}%" >> "$LOG"
