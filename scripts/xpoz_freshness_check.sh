#!/bin/bash
# Hourly: probe Xpoz once per platform (xpoz_freshness_probe.py), keep the
# reading, and alert through the honeypot freshness script when a platform's
# newest result is too old. See both scripts for why.
#
# Installed as /etc/cron.d/aunoo-xpoz-freshness (hourly, as root).
# XPOZ_FRESHNESS_DRY_RUN=1 runs the probe for real (it spends credits) but
# prints the alert instead of sending it.
SITE_DIR=/home/orochford/tenants/bugfixing.aunoo.ai
OUT=/var/tmp/xpoz_freshness_latest.json
LOG=/var/log/aunoo-xpoz-freshness.log
export XPOZ_API_KEY=$(grep '^XPOZ_API_KEY=' "$SITE_DIR/.env" | cut -d= -f2- | tr -d '"')
# The probe's own daily allowances for the budgeted platforms: one Instagram
# search (12 credits) and one TikTok search (5) an hour, with a little room.
export XPOZ_INSTAGRAM_CREDITS_PER_DAY=300 XPOZ_TIKTOK_CREDITS_PER_DAY=130
cd "$SITE_DIR" || exit 1
if ! PYTHONPATH=. timeout 600 ./.venv/bin/python -W ignore scripts/xpoz_freshness_probe.py > "$OUT.tmp" 2>> "$LOG"; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') probe failed; see above" >> "$LOG"
    exit 0
fi
mv "$OUT.tmp" "$OUT"
reading=$(python3 - "$OUT" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
parts = []
for p, v in d["platforms"].items():
    parts.append(f"{p}={v['lag_h']}h" + (f" (error: {v['error'][:60]})" if v.get("error") else ""))
print(" ".join(parts) or ("paused" if d.get("paused") else "none"))
PY
)
echo "$(date '+%Y-%m-%d %H:%M:%S') reading: $reading" >> "$LOG"
env FRESHNESS_KIND=probe FRESHNESS_URL="file://$OUT" FRESHNESS_LOG="$LOG" \
    FRESHNESS_STATE=/var/tmp/xpoz_freshness_state ${XPOZ_FRESHNESS_DRY_RUN:+FRESHNESS_DRY_RUN=1} \
    /home/orochford/tenants/bugfixing.aunoo.ai/saasmvp-app/scripts/honeypot_freshness_check.sh
