#!/bin/bash
# Restart monolith sites when nobody is using them and nothing is mid-flight.
#
#   scripts/restart_when_quiet.sh [--check] [--soft MIN] [--max MIN] site...
#
# Signals, read every 30 s from the journal and the site's database:
#   hard (must all be zero before a restart):
#     users     successful /api/ requests in the last 3 min from any client but
#               127.0.0.1, excluding the public market-monitor report, feeds and
#               webhooks, the notification poll, health probes and the MCP
#               endpoint (the journal carries uvicorn's access log; nginx
#               passes the real client address)
#     chat      Auspex messages written in the last 5 min (covers MCP chats,
#               which make no browser requests)
#     jobs      detection runs 'running', background tasks 'running'/'pending'
#               started in the last 6 h, desk briefings touched in the last
#               10 min (a compose or finalize in progress)
#     due       observer agents past their next_run_at (a restart fires them
#               all at once; see reference_observer_agent_email_spam)
#     long      database queries active for more than 20 s
#   soft (waited out for --soft minutes, default 45, then ignored):
#     ingest    automated ingest / emerging topics / compose log lines in the
#               last 2 min. The ingest is periodic and resumes after a restart.
#
# Why not count model-call log lines: the ingest pipeline logs 'Starting
# response generation' and 'app.research' set_topic lines per article, so a
# busy ingest looked like a live chat and held wileytest's restart for an hour
# on 25 Sep 2026.
#
# --check prints the signals for each site and exits without restarting.
set -u
CHECK=0; SOFT=45; MAX=60
while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK=1; shift;;
    --soft) SOFT=$2; shift 2;;
    --max) MAX=$2; shift 2;;
    *) break;;
  esac
done

signals() {  # $1 site -> prints "users chat jobs due long ingest"
  local t=$1 d=/home/orochford/tenants/$1.aunoo.ai u=$1.aunoo.ai.service
  local P U N; P=$(grep ^DB_PASSWORD= $d/.env | cut -d= -f2- | tr -d '"'); U=$(grep ^DB_USER= $d/.env | cut -d= -f2- | tr -d '"'); N=$(grep ^DB_NAME= $d/.env | cut -d= -f2- | tr -d '"')
  q() { PGPASSWORD=$P psql -h localhost -U $U -d $N -At -c "$1" 2>/dev/null || echo 0; }
  local log; log=$(sudo journalctl -u $u --since "-180 sec" --no-pager)
  # A person who is logged in gets 200s on /api/ paths. Machines do not: the
  # aisocnews server fetches the public market report and feeds, BrightData
  # calls a webhook, monitors probe / and /login (307), scanners get 404s, and
  # 127.0.0.1 is our own checks. An idle browser tab polls /api/notifications
  # every minute, so that path does not count as activity either.
  local users; users=$(echo "$log" | grep -E 'INFO: +[0-9.]+:[0-9]+ - "(GET|POST|PUT|PATCH|DELETE) /api/[^ ]* HTTP/1.1" 200' | grep -vE 'INFO: +127\.0\.0\.1:' | grep -vE '/api/(market-monitor/(markets/[0-9]+/(report\.html|feed\.(json|xml))|webhooks/)|notifications|modules|health|mcp)' | wc -l)
  local chat; chat=$(q "SELECT count(*) FROM auspex_messages WHERE timestamp > now() - interval '5 min'")
  local jobs; jobs=$(q "SELECT (SELECT count(*) FROM detection_runs WHERE status='running' AND created_at > now() - interval '6 hours')
                       + (SELECT count(*) FROM background_tasks WHERE status IN ('running','pending') AND COALESCE(started_at, created_at) > now() - interval '6 hours')
                       + (SELECT count(*) FROM desk_briefings WHERE updated_at > now() - interval '10 min')")
  local due; due=$(q "SELECT count(*) FROM signal_instructions WHERE is_active AND next_run_at < now()")
  [ "$due" = 0 ] && due=$(q "SELECT count(*) FROM signal_instructions WHERE schedule_enabled AND next_run_at < now()")
  local long; long=$(q "SELECT count(*) FROM pg_stat_activity WHERE datname='$N' AND state='active' AND now()-query_start > interval '20 sec'")
  local ingest; ingest=$(echo "$log" | grep -E "automated_ingest_service - INFO|emerging_topics|\[compose\]" | grep -c .)
  echo "${users:-0} ${chat:-0} ${jobs:-0} ${due:-0} ${long:-0} ${ingest:-0}"
}

for t in "$@"; do
  d=/home/orochford/tenants/$t.aunoo.ai; u=$t.aunoo.ai.service
  PORT=$(grep ^PORT= $d/.env | cut -d= -f2- | tr -d '"')
  if [ $CHECK = 1 ]; then
    read users chat jobs due long ingest <<<"$(signals $t)"
    echo "$t: users=$users chat=$chat jobs=$jobs due=$due long=$long ingest=$ingest"
    continue
  fi
  mode=""; waited=0
  while [ $waited -lt $((MAX*60)) ]; do
    read users chat jobs due long ingest <<<"$(signals $t)"
    if [ "$users" = 0 ] && [ "$chat" = 0 ] && [ "$jobs" = 0 ] && [ "$due" = 0 ] && [ "$long" = 0 ]; then
      if [ "$ingest" = 0 ]; then mode="quiet"; break; fi
      if [ $waited -ge $((SOFT*60)) ]; then mode="ingest running, nothing else"; break; fi
    fi
    sleep 30; waited=$((waited+30))
  done
  if [ -z "$mode" ]; then
    echo "$t: NOT restarted after $MAX min (users=$users chat=$chat jobs=$jobs due=$due long=$long ingest=$ingest)"; continue
  fi
  sudo systemctl restart $u
  for i in $(seq 1 80); do c=$(curl -s -o /dev/null -w '%{http_code}' -H 'X-Forwarded-Proto: https' http://127.0.0.1:$PORT/); case $c in 200|30*) break;; esac; sleep 3; done
  sleep 60
  since=$(systemctl show -p ActiveEnterTimestamp --value $u | cut -d' ' -f2-3)
  tb=$(sudo journalctl -u $u --since "$since" --no-pager | grep -c Traceback)
  echo "$t: restarted ($mode) at $(date +%H:%M) | http $c | tracebacks $tb"
done
