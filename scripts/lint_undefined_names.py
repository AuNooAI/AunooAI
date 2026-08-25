#!/usr/bin/env python3
"""Fail the build on a name that does not exist.

Written after `entity_projection` was used in `entity_ingest.py` and never
imported. Every snapshot-backed ingest raised `NameError`, a broad `except`
swallowed it, and the canonical rows updated while `bw_entity_profiles` — the
table vendor lists and filters actually read — silently did not. It survived
review, a full test suite and a production deploy, because the test asserted
the canonical row and stopped there.

A single-second check catches that class outright, so it is a gate rather than
a nicety.

The wider application carries a backlog of the same warnings from before this
existed. Failing on all of them would mean nobody could commit, so the rule is
the one the UI type-checker already uses here: the guarded paths must be clean,
and the rest must not get worse.

Usage:
    python scripts/lint_undefined_names.py            # gate
    python scripts/lint_undefined_names.py --report   # show everything
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Paths that must be clean. New work is added here; the backlog is not.
GUARDED = [
    'app/services/entity_content.py',
    'app/services/entity_dual_read.py',
    'app/services/entity_events.py',
    'app/services/entity_field_registry.py',
    'app/services/entity_flags.py',
    'app/services/entity_identity.py',
    'app/services/entity_ingest.py',
    'app/services/entity_narratives.py',
    'app/services/entity_observations.py',
    'app/services/entity_projection.py',
    'app/services/entity_resolution.py',
    'app/services/entity_review.py',
    'app/services/entity_social_read.py',
    'app/services/entity_event_extractors',
    'app/routes/market_entity_routes.py',
    'scripts/entity_intelligence_backfill.py',
]

# The count of pre-existing undefined names elsewhere in app/. Lower it when
# you fix some; never raise it to make a commit pass.
BASELINE = 30


def undefined_names(targets: list) -> list:
    """pyflakes output lines reporting an undefined name."""
    existing = [str(ROOT / t) for t in targets if (ROOT / t).exists()]
    if not existing:
        return []
    result = subprocess.run(
        [sys.executable, '-m', 'pyflakes', *existing],
        capture_output=True, text=True, cwd=ROOT)
    return [line for line in result.stdout.splitlines()
            if 'undefined name' in line]


def main() -> int:
    report = '--report' in sys.argv

    guarded = undefined_names(GUARDED)
    if guarded:
        print('Undefined names in guarded paths:\n')
        for line in guarded:
            print(f'  {line}')
        print(f'\n{len(guarded)} undefined name(s). These are errors at '
              f'runtime, not warnings.')
        return 1

    everything = undefined_names(['app'])
    print(f'Guarded paths clean. Rest of app/: {len(everything)} known '
          f'(baseline {BASELINE}).')
    if report:
        for line in everything:
            print(f'  {line}')
    if len(everything) > BASELINE:
        print(f'\nThat is {len(everything) - BASELINE} more than the baseline. '
              f'Fix them, or say why and move the baseline down deliberately — '
              f'never up to make a commit pass.')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
