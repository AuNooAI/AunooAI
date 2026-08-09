#!/bin/bash
# embedding_health_check.sh — checks A-D from docs/EMBEDDING_HEALTH_MONITORING.md.
#
# Exists because wbm wrote no embeddings for four weeks (2026-07-05 to 08-02)
# without anything noticing. collector_health_check.sh could not have caught it:
# collection, enrichment and brand alerts were all healthy the whole time. The
# failure was per-article and non-fatal, and the consumer (bw_article_stories)
# treats a missing embedding as absence rather than error.
#
# These four checks are invariants, not rates. They need no baseline and cannot
# false-positive on a quiet traffic day:
#
#   A. code EMBEDDING_DIM == articles.embedding column width, and the two derived
#      centroid columns match it. This alone catches the wbm outage.
#   B. the DeBERTa encoder answers, and answers at the expected width. The alert
#      body carries the probe latency and the load average, because a starved
#      encoder looks identical to a crashed one from the caller's side: on
#      2026-08-09 a load spike (127 on 20 cores) made this check report the
#      encoder down when it was up and serving the whole time.
#   C. no vector-write errors in the journal (the direct symptom).
#   D. the HNSW index exists and indisvalid — an invalid index is silently
#      ignored by the planner, so search degrades to seq scans with no error.
#
# Deliberately NOT included: any "articles collected but not embedded" check.
# Articles are only indexed after the relevance and quality gates, so that fires
# constantly on a normal quiet spell (wbm, 2026-08-02: processed 2, enriched 2,
# relevant 0, saved 0 — correct behaviour, 160 articles legitimately unindexed).
# See checks E/F in the spec for the way around it; neither is built.
#
# Alerts by email via Resend (key read from wileytest's .env), logs to
# /var/log/aunoo-embedding-health.log. Repeat alerts for the same condition are
# suppressed for 6 hours; a recovery clears the suppression. Same shape as
# collector_health_check.sh — keep the two consistent.
#
# Installed in root's crontab: runs every 30 minutes.
# Tracked at scripts/embedding_health_check.sh; deployed to /home/orochford/bin/.
# KEEP THOSE TWO IN SYNC — the collector check drifted once (7dd5d56c).

TENANTS="bugfixing wileytest wiley wbm"
LOG=/var/log/aunoo-embedding-health.log
STATE_DIR=/var/tmp/embedding_health_state
ALERT_TO="oliver.rochford@gmail.com"
SUPPRESS_SECS=21600   # 6h between repeat alerts for the same condition
JOURNAL_WINDOW="-40 min"

RESEND_ENV=/home/orochford/tenants/wileytest.aunoo.ai/.env
RESEND_KEY=$(grep '^RESEND_API_KEY=' "$RESEND_ENV" 2>/dev/null | cut -d= -f2-)
RESEND_FROM=$(grep '^RESEND_FROM_EMAIL=' "$RESEND_ENV" 2>/dev/null | cut -d= -f2-)

mkdir -p "$STATE_DIR"
ts() { date '+%Y-%m-%d %H:%M:%S'; }
sysload() { echo "$(cut -d' ' -f1-3 /proc/loadavg) (1/5/15 min) on $(nproc) CPUs"; }

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
    send_email "[aunoo/$tenant] embedding health alert: $check" \
"Tenant:  $tenant.aunoo.ai
Check:   $check
Time:    $(ts)

$msg

Background: docs/EMBEDDING_HEALTH_MONITORING.md
Log:     $LOG
This check runs every 30 min from root's crontab (embedding_health_check.sh)."
}

recover() {
    local tenant="$1" check="$2"
    local state="$STATE_DIR/${tenant}_${check}"
    if [ -f "$state" ]; then
        rm -f "$state"
        echo "$(ts) [$tenant] RECOVERED: $check" >> "$LOG"
    fi
}

# Expected vector width, read from the tenant's own code rather than assumed.
# Post-migration files define EMBEDDING_DIM; the older OpenAI path did not and
# used text-embedding-3-small at 1536.
code_dim_for() {
    local f="/home/orochford/tenants/$1.aunoo.ai/app/vector_store_pgvector.py"
    [ -f "$f" ] || return 1
    local d
    d=$(grep -oP '^EMBEDDING_DIM\s*=\s*\K[0-9]+' "$f" | head -1)
    if [ -z "$d" ] && grep -q 'text-embedding-3-small' "$f"; then
        d=1536
    fi
    [ -n "$d" ] && echo "$d"
}

psql_t() {   # psql_t <tenant> <sql>  — reads via the tenant's own credentials
    local envfile="/home/orochford/tenants/$1.aunoo.ai/.env"
    local db dbu dbp dbport
    db=$(grep '^DB_NAME=' "$envfile" | cut -d= -f2)
    dbu=$(grep '^DB_USER=' "$envfile" | cut -d= -f2)
    dbp=$(grep '^DB_PASSWORD=' "$envfile" | cut -d= -f2)
    dbport=$(grep '^DB_PORT=' "$envfile" | cut -d= -f2)
    [ -n "$db" ] && [ -n "$dbu" ] || return 1
    PGPASSWORD="$dbp" psql -h 127.0.0.1 -p "${dbport:-6432}" -U "$dbu" -d "$db" -tAc "$2" 2>>"$LOG"
}

for t in $TENANTS; do
    svc="$t.aunoo.ai.service"
    envfile="/home/orochford/tenants/$t.aunoo.ai/.env"

    if ! systemctl is-active --quiet "$svc"; then
        echo "$(ts) [$t] SKIP: $svc not active (collector check owns service_down)" >> "$LOG"
        continue
    fi

    # ---- A: code and column agree on dimension -------------------------------
    code_dim=$(code_dim_for "$t")
    if [ -z "$code_dim" ]; then
        alert "$t" "code_dim_unknown" \
"Could not determine the expected vector width from
app/vector_store_pgvector.py (no EMBEDDING_DIM and no text-embedding-3-small).
Check A cannot run for this tenant."
        continue
    fi
    recover "$t" "code_dim_unknown"

    col_dims=$(psql_t "$t" "
        SELECT c.relname||'.'||a.attname||'='||
               regexp_replace(format_type(a.atttypid,a.atttypmod),'[^0-9]','','g')
        FROM pg_attribute a
        JOIN pg_class c ON c.oid=a.attrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND a.attnum>0 AND NOT a.attisdropped
          AND c.relkind='r'
          AND c.relname IN ('articles','emerging_topics','cluster_snapshots')
          AND a.attname IN ('embedding','centroid_embedding')
        ORDER BY 1")
    if [ -z "$col_dims" ]; then
        alert "$t" "db_query_failed" "Could not read vector column types."
        continue
    fi
    recover "$t" "db_query_failed"

    mismatch=""
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        got="${line##*=}"
        [ "$got" = "$code_dim" ] || mismatch="$mismatch  $line (code says $code_dim)"$'\n'
    done <<< "$col_dims"

    if [ -n "$mismatch" ]; then
        alert "$t" "dim_mismatch" \
"Code and database disagree on vector width. Every embedding write will fail
with 'expected N dimensions, not M' and articles will silently go unindexed.
This is the wbm failure of 2026-07-05.

Code EMBEDDING_DIM: $code_dim
Columns:
$mismatch
Fix: align the column via an alembic migration, or the code, so they match."
    else
        recover "$t" "dim_mismatch"
    fi

    # ---- B: encoder reachable, and at the right width -------------------------
    enc=$(grep '^DEBERTA_ENCODER_URL=' "$envfile" 2>/dev/null | cut -d= -f2-)
    enc="${enc:-http://localhost:8001}"
    probe_code=""; probe_secs=""
    if [ "$code_dim" != "1536" ]; then   # OpenAI-path tenants have no local encoder
        probe_tmp="$STATE_DIR/probe_body.$$"
        probe_meta=$(curl -s -m 10 -o "$probe_tmp" -w '%{http_code} %{time_total}' \
                  -X POST "$enc/encode" \
                  -H 'Content-Type: application/json' \
                  -d '{"title":"healthcheck","description":"","content":"probe"}' 2>/dev/null)
        probe=$(cat "$probe_tmp" 2>/dev/null); rm -f "$probe_tmp"
        probe_code="${probe_meta%% *}"; probe_secs="${probe_meta##* }"
        got_dim=$(printf '%s' "$probe" | python3 -c "
import json,sys
try:
    e = json.load(sys.stdin).get('embedding')
    print(len(e) if isinstance(e, list) else 'noembedding')
except Exception:
    print('unparseable')
" 2>/dev/null)
        if [ "$got_dim" = "$code_dim" ]; then
            recover "$t" "encoder_bad"
        else
            alert "$t" "encoder_bad" \
"DeBERTa encoder at $enc did not return a usable ${code_dim}d vector (got: ${got_dim:-no response}).
Probe: HTTP ${probe_code:-000} in ${probe_secs:-?}s (curl timeout 10s). Load: $(sysload).
The code raises rather than falling back, so articles go unindexed while this
is down. No bad vectors are written.
If the load is far above the CPU count, the encoder is starved, not crashed —
find and stop what is eating the CPU; restarting the encoder does not help
(this is what happened on 2026-08-09). Otherwise: restart the encoder service,
then re-run any backfill."
        fi
    fi

    # ---- C: vector-write errors in the journal --------------------------------
    errs=$(journalctl -q -u "$svc" --since "$JOURNAL_WINDOW" --no-pager 2>/dev/null \
           | grep -cE "vector upsert failed|expected [0-9]+ dimensions|DeBERTa encoder unreachable")
    if [ "${errs:-0}" -gt 0 ]; then
        sample=$(journalctl -q -u "$svc" --since "$JOURNAL_WINDOW" --no-pager 2>/dev/null \
                 | grep -E "vector upsert failed|expected [0-9]+ dimensions|DeBERTa encoder unreachable" \
                 | tail -2)
        alert "$t" "vector_write_errors" \
"$errs vector-write errors in the last 40 minutes. Articles are being collected
but not indexed, and nothing downstream will report it.
Load now: $(sysload) — if far above the CPU count, suspect encoder starvation
rather than an encoder crash.

$sample"
    else
        recover "$t" "vector_write_errors"
    fi

    # ---- D: HNSW index present and valid --------------------------------------
    idx=$(psql_t "$t" "
        SELECT coalesce((SELECT i.indisvalid::text FROM pg_index i
                         JOIN pg_class c ON c.oid=i.indexrelid
                         WHERE c.relname='articles_embedding_hnsw_idx'), 'missing')")
    # psql renders boolean::text as 'true'/'false' here, not 't'/'f' — accept both,
    # because getting this wrong turns a healthy index into a spurious alert.
    case "$idx" in
        t|true)  recover "$t" "hnsw_index" ;;
        f|false) alert "$t" "hnsw_index" \
"articles_embedding_hnsw_idx exists but indisvalid=false. The planner ignores an
invalid index, so semantic search silently falls back to sequential scans over
the whole articles table. A failed CREATE INDEX CONCURRENTLY leaves it this way.
Fix: DROP INDEX articles_embedding_hnsw_idx, then rebuild CONCURRENTLY." ;;
        missing) alert "$t" "hnsw_index" \
"articles_embedding_hnsw_idx does not exist. Semantic search still works but
scans the whole table. Expected after emb_768_01, which drops it deliberately —
it should be rebuilt once the backfill drains." ;;
        *)  alert "$t" "db_query_failed" "Could not read index state (got: '$idx')." ;;
    esac

    echo "$(ts) [$t] OK: dim=$code_dim cols_checked=$(printf '%s' "$col_dims" | grep -c .) journal_errs=$errs hnsw=$idx enc_s=${probe_secs:-n/a}" >> "$LOG"
done
