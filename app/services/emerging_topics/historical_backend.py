"""Which embedding store, if any, may decide new-topic vs ongoing-topic.

The pipeline shipped a check that classified a theme as ongoing when at least 3
articles in the 60-day window sat within cosine distance 0.85 of it. Measured on
2026-08-19 against 5,000 bugfixing articles, distances ran 0.072-0.455 with a
median of 0.148, so 0.85 matched 100% of the corpus and the check always
answered "ongoing". Two invented themes — a fictional product recall and a
fictional licensing reform — were both labelled as having prior coverage from
around 40 sources.

The cause is the store, not the threshold. articles.embedding holds
deberta-base vectors, and deberta-base is a masked language model whose vectors
do not separate topical identity: the nearest historical article to gibberish
sat at 0.080, to a real theme at 0.071. No cutoff can divide those.

So DeBERTa is not an approved backend for this decision, and this module makes
that structural rather than a matter of remembering. :func:`require_approved`
raises on anything else, and the only caller that can classify is the one that
passes ``E5``.

The E5 store (article_embeddings_ml, vector(1024), intfloat/multilingual-e5-large)
does separate them — measured on wileytest, real themes at 0.109-0.151 against a
background median of 0.264-0.272, invented ones at 0.161-0.170. That is signal,
but it is not yet validated against a labelled set, and the real/invented ranges
overlap (0.151 vs 0.161). Until that validation happens E5 runs in shadow only:
it logs what it would have decided and changes nothing.

Modes, via ``EMERGING_TOPICS_HISTORICAL_MODE``:

``off`` (default)
    Do not classify. Every theme gets ``unknown`` and stays ``llm_proposed``.
``shadow``
    Classify with E5 where the store exists, log the decision, and still return
    ``unknown``. Nothing about the topic or its notifications changes.
``enforce``
    Act on the E5 decision. Not enabled anywhere; it is here so turning it on
    after validation is a config change rather than a code change.
"""

import logging
import os
from typing import Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Embedding stores this module knows about.
DEBERTA = "deberta"        # articles.embedding, vector(768)
E5 = "e5"                  # article_embeddings_ml, vector(1024)

# Stores permitted to decide new-vs-ongoing. DeBERTa is deliberately absent.
APPROVED_BACKENDS = frozenset({E5})

# Outcome of the check. "unknown" is a real answer, not a failure: it says we
# could not tell, which is the truth whenever there is no calibrated index.
ONGOING = "ongoing"
NOT_FOUND = "not_found"
UNKNOWN = "unknown"
STATUSES = (ONGOING, NOT_FOUND, UNKNOWN)

MODE_OFF = "off"
MODE_SHADOW = "shadow"
MODE_ENFORCE = "enforce"
MODES = (MODE_OFF, MODE_SHADOW, MODE_ENFORCE)

E5_TABLE = "article_embeddings_ml"
E5_DIM = 1024

# Enough E5 rows for a background distribution to mean anything.
MIN_E5_ROWS = 10_000


class UnsupportedBackend(RuntimeError):
    """Raised when something tries to classify with a store that cannot."""


def require_approved(backend: str) -> str:
    """Gate every classification call. Raises for unapproved stores.

    This exists so that wiring the classifier to DeBERTa fails loudly at the
    call site instead of quietly producing the confident nonsense it produced
    before.
    """
    if backend not in APPROVED_BACKENDS:
        raise UnsupportedBackend(
            f"'{backend}' is not approved for historical-coverage classification "
            f"(approved: {', '.join(sorted(APPROVED_BACKENDS))}). deberta-base "
            "does not separate a real topic from invented text — see "
            "app/services/emerging_topics/historical_backend.py."
        )
    return backend


def resolve_mode() -> str:
    """Read the configured mode, defaulting to off."""
    raw = (os.getenv("EMERGING_TOPICS_HISTORICAL_MODE") or MODE_OFF).strip().lower()
    if raw not in MODES:
        logger.warning(
            "Unknown EMERGING_TOPICS_HISTORICAL_MODE=%r; falling back to %r",
            raw, MODE_OFF,
        )
        return MODE_OFF
    return raw


_e5_ready: Optional[bool] = None


def e5_available(conn) -> bool:
    """Is there a usable E5 index on this tenant? Probed once per process."""
    global _e5_ready
    if _e5_ready is not None:
        return _e5_ready

    try:
        present = conn.execute(
            text("SELECT to_regclass(:name)"), {"name": E5_TABLE}
        ).scalar()
        if not present:
            _e5_ready = False
        else:
            rows = conn.execute(text(f"SELECT COUNT(*) FROM {E5_TABLE}")).scalar() or 0
            _e5_ready = rows >= MIN_E5_ROWS
            if not _e5_ready:
                logger.info(
                    "E5 store holds %s rows, below the %s needed to calibrate "
                    "against; historical classification stays unknown",
                    rows, MIN_E5_ROWS,
                )
    except Exception as exc:
        logger.warning("Could not probe the E5 store: %s", exc)
        _e5_ready = False

    return _e5_ready


def reset_probe_cache() -> None:
    """Forget the cached probe. For tests."""
    global _e5_ready
    _e5_ready = None


def describe(mode: str, available: bool) -> str:
    """A one-line explanation of why the check will or will not classify."""
    if mode == MODE_OFF:
        return "historical classification disabled (mode=off); every theme is unknown"
    if not available:
        return (
            f"no calibrated E5 index on this tenant (mode={mode}); "
            "every theme is unknown"
        )
    if mode == MODE_SHADOW:
        return "E5 shadow mode: decisions are logged and change nothing"
    return "E5 enforcing: decisions set detection_type"
