#!/bin/bash
# Deploy the brand relevance code from canonical to one monolith site, flag off.
#
#   scripts/brand_rollout/deploy_site.sh <site> [check|apply]
#
# check (default): preflight only. apply: back up every file it will touch to
# /var/tmp/brand_rollout/backup/<site>-<stamp>/, copy the new modules and
# scripts, patch brand_watcher_routes.py and brand_risk_assessment.py, run the
# ingest / alert-query / keyword-monitor transforms, write migration br_001 with
# the site's own head as its parent, then compile and import the app.
# It does not run the migration, set the flag or restart: those are separate
# steps (docs/BRAND_RELEVANCE_SPEC.md, Appendix B).
set -euo pipefail
site="${1:?site}"; mode="${2:-check}"
C=/home/orochford/tenants/bugfixing.aunoo.ai
T=/home/orochford/tenants/$site.aunoo.ai
P=/var/tmp/brand_rollout/patches
PY="$T/.venv/bin/python"
[ -x "$PY" ] || { echo "no venv python at $PY"; exit 2; }
NEW="app/services/brand_profile.py app/services/brand_decision.py app/services/brand_decision_store.py
app/services/brand_coverage.py app/services/brand_ingest_hooks.py app/services/brand_retry.py
scripts/brand_profile_keywords.py scripts/brand_profile_apply.py scripts/brand_relevance_eval.py scripts/brand_retry.py
eval/brand_relevance/profiles/sunstar.json eval/brand_relevance/profiles/oviva.json"
MOD="app/routes/brand_watcher_routes.py app/services/brand_risk_assessment.py app/tasks/brand_watcher_monitor.py
app/services/bw_digest_service.py app/tasks/keyword_monitor.py app/services/automated_ingest_service.py"

echo "== $site: preflight"
for f in $MOD; do [ -f "$T/$f" ] || { echo "missing $f"; exit 2; }; done
mkdir -p "$P"
for f in app/routes/brand_watcher_routes.py app/services/brand_risk_assessment.py; do
  git -C "$C" diff d43c27a5..HEAD -- "$f" > "$P/$(basename $f).patch"
  if grep -q '_bcov' "$T/$f"; then echo "  $f: already patched"; continue; fi
  (cd "$T" && patch -p1 --dry-run --forward -s < "$P/$(basename $f).patch") >/dev/null || { echo "  $f: patch does not apply"; exit 2; }
  echo "  $f: patch applies"
done
python3 "$C/scripts/brand_rollout/transform_ingest.py" "$T" | tail -1
python3 "$C/scripts/brand_rollout/transform_alert_queries.py" "$T" app/tasks/brand_watcher_monitor.py
python3 "$C/scripts/brand_rollout/transform_alert_queries.py" "$T" app/services/bw_digest_service.py
python3 "$C/scripts/brand_rollout/transform_keyword_monitor.py" "$T"
head=$(cd "$T" && "$T/.venv/bin/alembic" heads 2>/dev/null | grep -v -E '^(INFO|WARN)' | awk '{print $1}' | head -1)
[ -n "$head" ] || { echo "cannot read alembic head"; exit 2; }
echo "  alembic head: $head"
if [ "$mode" != "apply" ]; then echo "== check passed (nothing written)"; exit 0; fi

stamp=$(date +%Y%m%d_%H%M%S); BK=/var/tmp/brand_rollout/backup/$site-$stamp
mkdir -p "$BK"
for f in $MOD $NEW; do [ -f "$T/$f" ] && (cd "$T" && cp --parents "$f" "$BK/"); done
echo "== backup: $BK"
for f in $NEW; do mkdir -p "$T/$(dirname $f)"; cp "$C/$f" "$T/$f"; done
for f in app/routes/brand_watcher_routes.py app/services/brand_risk_assessment.py; do
  grep -q '_bcov' "$T/$f" || (cd "$T" && patch -p1 --forward -s --no-backup-if-mismatch < "$P/$(basename $f).patch")
done
python3 "$C/scripts/brand_rollout/transform_ingest.py" "$T" --apply | tail -1
python3 "$C/scripts/brand_rollout/transform_alert_queries.py" "$T" app/tasks/brand_watcher_monitor.py --apply
python3 "$C/scripts/brand_rollout/transform_alert_queries.py" "$T" app/services/bw_digest_service.py --apply
python3 "$C/scripts/brand_rollout/transform_keyword_monitor.py" "$T" --apply
mig="$T/alembic/versions/br_001_brand_relation_decisions.py"
if [ "$head" != "br_001" ]; then
  sed "s/^down_revision = 'mf_001'$/down_revision = '$head'/; s/^Revises: mf_001$/Revises: $head/" \
      "$C/alembic/versions/br_001_brand_relation_decisions.py" > "$mig"
  grep -q "^down_revision = '$head'" "$mig" || { echo "migration parent not set"; exit 2; }
fi
for f in $MOD $NEW; do case "$f" in *.py) "$PY" -m py_compile "$T/$f";; esac; done
(cd "$T" && timeout 240 "$PY" -c "
import logging; logging.disable(logging.CRITICAL)
import app.main as m
ok = any(getattr(r, 'path', '') == '/api/brand-watcher/brands/{brand_id}/coverage-split' for r in m.app.routes)
print('  app import ok; coverage endpoint registered:', ok)
") 2>&1 | tail -1
echo "== $site: code deployed with the flag off. Next: alembic upgrade br_001, restart when quiet, smoke check."
