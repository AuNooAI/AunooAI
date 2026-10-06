#!/bin/bash
# Build a site's UI = its exact current base + the brand coverage panel, and deploy it.
#
#   scripts/brand_rollout/build_site_ui.sh <base-commit | base-dir> <site> [<site>...] [--extra <patch>]... [--apply]
#
# 1. git archive <base-commit> into scratch, apply each --extra patch (to rebuild
#    a base that was never committed as one tree), build; the news-feed chunk
#    hash must equal every listed site's deployed one, or it stops.
# 2. apply /var/tmp/brand_rollout/patches/ui_coverage_panel.patch, build again.
# 3. each site's templates must differ from the new build only in asset hashes.
# 4. with --apply: back up the site's static/trend-convergence and *_react.html
#    to /var/tmp/brand_rollout/backup/<site>-ui-<stamp>/, then rsync.
set -euo pipefail
C=/home/orochford/tenants/bugfixing.aunoo.ai
base="$1"; shift
sites=(); extras=(); apply=0
while [ $# -gt 0 ]; do
  case "$1" in --apply) apply=1;; --extra) shift; extras+=("$1");; *) sites+=("$1");; esac; shift
done
W=$(mktemp -d /var/tmp/brand_rollout/uibuild-XXXX)
if [ -d "$base" ]; then
  # A scratch tree an earlier session built a site's UI from (never committed as one tree).
  rsync -a --exclude node_modules --exclude 'ui/build' "$base/ui" "$W/"
  rsync -a "$base/static" "$base/templates" "$W/"
else
  git -C "$C" archive "$base" ui static/trend-convergence templates | tar -x -C "$W"
fi
ln -s "$C/ui/node_modules" "$W/ui/node_modules"
for x in "${extras[@]}"; do (cd "$W" && patch -p1 -s < "$x"); done
chunk() { grep -o -E 'newsfeed-[A-Za-z0-9_-]+\.js' "$1/static/trend-convergence/index-newsfeed.html" | head -1; }
(cd "$W" && SKIP_TYPECHECK=1 timeout 900 ./ui/deploy-react-ui.sh > "$W/base.log" 2>&1)
b=$(chunk "$W"); echo "base build: $b"
for s in "${sites[@]}"; do d=$(chunk "/home/orochford/tenants/$s.aunoo.ai"); [ "$b" = "$d" ] || { echo "$s deploys $d, base gives $b: not this base, stopping"; exit 2; }; echo "  $s: base reproduced exactly"; done
(cd "$W" && patch -p1 -s < /var/tmp/brand_rollout/patches/ui_coverage_panel.patch)
(cd "$W" && SKIP_TYPECHECK=1 timeout 900 ./ui/deploy-react-ui.sh > "$W/new.log" 2>&1)
echo "new build: $(chunk "$W")"
norm() { sed -E 's/-[A-Za-z0-9_-]{8}\.(js|css)/-HASH.\1/g' "$1"; }
for s in "${sites[@]}"; do
  T=/home/orochford/tenants/$s.aunoo.ai
  for f in $(cd "$W/templates" && ls *_react.html); do
    n=$(diff <(norm "$T/templates/$f") <(norm "$W/templates/$f") | grep -c '^[<>]' || true)
    [ "$n" = "0" ] || { echo "$s $f: $n non-hash lines differ, stopping"; exit 2; }
  done
  echo "  $s: templates differ only in asset hashes; $(comm -23 <(ls $T/static/trend-convergence/assets | sort) <(ls $W/static/trend-convergence/assets | sort) | wc -l) chunks replaced"
done
[ $apply = 1 ] || { echo "check only: $W"; exit 0; }
for s in "${sites[@]}"; do
  T=/home/orochford/tenants/$s.aunoo.ai; BK=/var/tmp/brand_rollout/backup/$s-ui-$(date +%Y%m%d_%H%M%S)
  mkdir -p "$BK/templates"; cp -a "$T/static/trend-convergence" "$BK/"; cp -a "$T"/templates/*_react.html* "$BK/templates/"
  rsync -a --delete "$W/static/trend-convergence/" "$T/static/trend-convergence/"
  rsync -a "$W"/templates/*_react.html "$T/templates/"
  chown -R --reference="$T/app" "$T/static/trend-convergence" "$T"/templates/*_react.html
  echo "  $s: deployed, now $(chunk "$T"); backup $BK"
done
