"""Deterministic event extraction, and an honest account of what is missing.

Every extractor here reads data already in the database and applies a rule a
person could check. None of them calls a model. That ordering is deliberate:
deterministic extraction runs first and establishes what happened, so that when
a model is later used it is structuring prose around known facts rather than
supplying the facts itself.

Two extractors named in the plan are registered and switched off, with the
reason attached. ``coverage`` needs relevance judgements this codebase makes
with a model, and ``social`` needs a volume baseline that fourteen evaluated
mentions cannot provide. Declaring them and refusing to run them is better than
either omitting them silently or shipping something that produces plausible
output from insufficient data.

Dates are the recurring difficulty. When a source states when something
happened — a job posting's date, a page's Last-Modified header — that is the
event date. When it does not, the event gets no date at all rather than the
date we noticed. A headcount that moved between two readings a month apart
happened on some day nobody recorded, and stamping it with the day the reading
landed would be a fabrication the schema is designed to prevent.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from app.services.entity_event_extractors import (
    funding, jobs, owned_post, profile, web_diff,
)

logger = logging.getLogger(__name__)

# name -> (callable, enabled, reason-when-disabled)
EXTRACTORS: Dict[str, tuple] = {
    'owned_post': (owned_post.run, True, None),
    'profile': (profile.run, True, None),
    'funding': (funding.run, True, None),
    'web_diff': (web_diff.run, True, None),
    'jobs': (jobs.run, True, None),
    'coverage': (None, False,
                 'needs model-scored relevance on earned coverage; deterministic '
                 'rules cannot tell a mention from a story about the company'),
    'social': (None, False,
               'needs a conversation baseline to call a spike; 14 evaluated '
               'mentions is not a baseline'),
}


def run_all(conn, *, brand_id: Optional[int] = None,
            only: Optional[List[str]] = None,
            limit: Optional[int] = None) -> Dict[str, Any]:
    """Run the enabled extractors and report what each one did."""
    summary: Dict[str, Any] = {'events_created': 0, 'events_merged': 0,
                               'skipped': {}, 'by_extractor': {}}
    for name, (fn, enabled, reason) in EXTRACTORS.items():
        if only and name not in only:
            continue
        if not enabled:
            summary['skipped'][name] = reason
            continue
        try:
            outcome = fn(conn, brand_id=brand_id, limit=limit)
        except Exception:                                   # noqa: BLE001
            logger.exception('extractor=%s failed brand_id=%s', name, brand_id)
            summary['by_extractor'][name] = {'error': 'see log'}
            continue
        summary['by_extractor'][name] = outcome
        summary['events_created'] += outcome.get('created', 0)
        summary['events_merged'] += outcome.get('merged', 0)
    return summary
