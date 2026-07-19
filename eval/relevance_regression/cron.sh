#!/usr/bin/env bash
# Recurring relevance regression test. Add to crontab, e.g.:
#   # daily golden regression (deterministic, ~1 min)
#   30 6 * * *  /home/orochford/tenants/wbm.aunoo.ai/eval/relevance_regression/cron.sh golden
#   # weekly live drift check (nova-lite judges ~40 recent articles)
#   30 6 * * 1  /home/orochford/tenants/wbm.aunoo.ai/eval/relevance_regression/cron.sh live
set -euo pipefail
# Tenant dir = two levels up from this script (eval/relevance_regression/ -> tenant root)
TENANT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODE="${1:-golden}"
LOG="$TENANT_DIR/eval/relevance_regression/history.log"
cd "$TENANT_DIR"

# Bedrock creds for the cost-conscious judge / LLM fallback
set -a; source .env 2>/dev/null || true; set +a
export AWS_BEARER_TOKEN_BEDROCK="${AWS_BEDROCK_API_KEY:-}"
export AWS_REGION_NAME="${AWS_REGION_NAME:-us-east-1}"
export PYTHONPATH="$TENANT_DIR"
export HF_HUB_DISABLE_PROGRESS_BARS=1 TRANSFORMERS_VERBOSITY=error

TENANT_NAME="$(basename "$TENANT_DIR")"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Review mode: have a cost-conscious LLM review the trend history and email the
# digest (no pass/fail gate — this is a regular qualitative read of the trend).
if [ "$MODE" = "review" ]; then
  REVIEW="$(.venv/bin/python eval/relevance_regression/run.py --review 2>/dev/null)"
  echo "$TS  mode=review  $(printf '%s' "$REVIEW" | grep -i '^VERDICT:' | head -1)" >> "$LOG"
  if [ -n "${RESEND_API_KEY:-}" ] && [ -n "$REVIEW" ]; then
    BODY=$(printf '%s' "$REVIEW" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')
    curl -s -X POST https://api.resend.com/emails \
      -H "Authorization: Bearer $RESEND_API_KEY" -H "Content-Type: application/json" \
      -d "{\"from\":\"alerts@aunoo.ai\",\"to\":\"oliver.rochford@gmail.com\",\"subject\":\"[$TENANT_NAME] relevance trend review\",\"text\":$BODY}" >/dev/null || true
  fi
  exit 0
fi

if [ "$MODE" = "live" ]; then ARGS="--live 40"; else ARGS="--golden"; fi

# Capture the RESULT line; run.py exits non-zero on regression.
set +e
OUT="$(.venv/bin/python eval/relevance_regression/run.py $ARGS 2>/dev/null | grep -E 'accuracy=|agreement=|RESULT:')"
CODE=$?
set -e
echo "$TS  mode=$MODE  exit=$CODE  $(echo "$OUT" | tr '\n' ' ')" >> "$LOG"

if [ "$CODE" -ne 0 ]; then
  # Regression: alert via Resend if configured (mirrors the collector-health cron).
  if [ -n "${RESEND_API_KEY:-}" ]; then
    curl -s -X POST https://api.resend.com/emails \
      -H "Authorization: Bearer $RESEND_API_KEY" -H "Content-Type: application/json" \
      -d "{\"from\":\"alerts@aunoo.ai\",\"to\":\"oliver.rochford@gmail.com\",\"subject\":\"[$TENANT_NAME] relevance regression ($MODE)\",\"text\":\"$TS\n$OUT\"}" >/dev/null || true
  fi
fi
exit "$CODE"
