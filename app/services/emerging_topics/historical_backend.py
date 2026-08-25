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
from dataclasses import dataclass, field
from typing import List, Optional

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

# Row count is a floor, not a readiness test. An index can hold a million rows
# and still be unusable: half the corpus missing, two model revisions mixed
# together, or six weeks stale. The criteria below are what "ready" means.
MIN_E5_ROWS = 10_000

# The revision the vectors must all have been produced by. Mixing revisions puts
# two different geometries in one index, and distances across them are noise.
EXPECTED_MODEL = "intfloat/multilingual-e5-large"

# Fraction of articles that must carry an E5 vector. Shadow tolerates a partial
# index because a gap only weakens what it observes; enforcing on a partial
# index silently decides from whichever half happens to be present.
SHADOW_MIN_COVERAGE = 0.50
ENFORCE_MIN_COVERAGE = 0.90

# An index nobody has added to in this long is not tracking the corpus, so
# "no older coverage found" would just mean "not indexed yet".
MAX_STALENESS_DAYS = 7


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


@dataclass
class E5Readiness:
    """Everything that decides whether the E5 index may be used, and how far."""
    table_present: bool = False
    rows: int = 0
    articles: int = 0
    dimension: Optional[int] = None
    model_revisions: List[str] = field(default_factory=list)
    coverage_ratio: float = 0.0
    staleness_days: Optional[float] = None
    has_ann_index: bool = False
    failures: List[str] = field(default_factory=list)

    @property
    def shadow_ready(self) -> bool:
        """Enough to observe. A missing ANN index only makes queries slow."""
        return not [f for f in self.failures if not f.startswith("enforce:")]

    @property
    def enforce_ready(self) -> bool:
        """Enough to act on. Every criterion, including the index."""
        return not self.failures

    def describe(self) -> str:
        if not self.table_present:
            return "E5 not ready: no article_embeddings_ml table on this tenant"
        state = (
            "enforce-ready" if self.enforce_ready
            else "shadow-ready" if self.shadow_ready
            else "not ready"
        )
        return (
            f"E5 {state}: {self.rows} vectors for {self.articles} articles "
            f"({self.coverage_ratio:.1%}), dim={self.dimension}, "
            f"revisions={self.model_revisions or 'none'}, "
            f"stale={self.staleness_days if self.staleness_days is None else round(self.staleness_days, 1)}d, "
            f"ann_index={self.has_ann_index}"
            + (f"; blocked by: {'; '.join(self.failures)}" if self.failures else "")
        )


def assess_e5_readiness(conn) -> E5Readiness:
    """Measure the E5 index against every criterion. Never raises."""
    r = E5Readiness()
    try:
        r.table_present = bool(conn.execute(
            text("SELECT to_regclass(:name)"), {"name": E5_TABLE}
        ).scalar())
        if not r.table_present:
            r.failures.append("no article_embeddings_ml table")
            return r

        row = conn.execute(text(f"""
            SELECT COUNT(*),
                   COUNT(DISTINCT model_version),
                   MIN(model_version),
                   EXTRACT(EPOCH FROM (NOW() - MAX(embedded_at))) / 86400.0
            FROM {E5_TABLE}
        """)).fetchone()
        r.rows = row[0] or 0
        distinct_revisions = row[1] or 0
        r.staleness_days = float(row[3]) if row[3] is not None else None

        r.model_revisions = [
            x[0] for x in conn.execute(text(
                f"SELECT DISTINCT model_version FROM {E5_TABLE} "
                "WHERE model_version IS NOT NULL ORDER BY 1"
            )).fetchall()
        ]

        r.articles = conn.execute(text("SELECT COUNT(*) FROM articles")).scalar() or 0
        r.coverage_ratio = (r.rows / r.articles) if r.articles else 0.0

        dim_text = conn.execute(text(f"""
            SELECT format_type(a.atttypid, a.atttypmod)
            FROM pg_attribute a
            WHERE a.attrelid = to_regclass('{E5_TABLE}') AND a.attname = 'embedding'
        """)).scalar() or ""
        if dim_text.startswith("vector(") :
            try:
                r.dimension = int(dim_text[len("vector("):-1])
            except ValueError:
                r.dimension = None

        r.has_ann_index = bool(conn.execute(text("""
            SELECT COUNT(*) FROM pg_indexes
            WHERE tablename = :t
              AND (indexdef ILIKE '%hnsw%' OR indexdef ILIKE '%ivfflat%')
        """), {"t": E5_TABLE}).scalar())

        # Criteria. "enforce:" prefixed ones block acting but not observing.
        if r.dimension != E5_DIM:
            r.failures.append(f"dimension is {r.dimension}, expected {E5_DIM}")
        if r.rows < MIN_E5_ROWS:
            r.failures.append(f"only {r.rows} vectors, need {MIN_E5_ROWS}")
        if distinct_revisions > 1:
            r.failures.append(
                f"{distinct_revisions} model revisions mixed in one index: "
                f"{', '.join(r.model_revisions)}"
            )
        if r.model_revisions and EXPECTED_MODEL not in r.model_revisions[0]:
            r.failures.append(
                f"model is {r.model_revisions[0]!r}, expected {EXPECTED_MODEL!r}"
            )
        if r.coverage_ratio < SHADOW_MIN_COVERAGE:
            r.failures.append(
                f"coverage {r.coverage_ratio:.1%} below the {SHADOW_MIN_COVERAGE:.0%} "
                "needed even to observe"
            )
        elif r.coverage_ratio < ENFORCE_MIN_COVERAGE:
            r.failures.append(
                f"enforce: coverage {r.coverage_ratio:.1%} below "
                f"{ENFORCE_MIN_COVERAGE:.0%}"
            )
        if not r.has_ann_index:
            r.failures.append("enforce: no HNSW/IVFFlat index on the vectors")
        if r.staleness_days is not None and r.staleness_days > MAX_STALENESS_DAYS:
            r.failures.append(
                f"enforce: newest vector is {r.staleness_days:.1f} days old, "
                f"limit {MAX_STALENESS_DAYS}"
            )

    except Exception as exc:
        logger.warning("Could not assess the E5 store: %s", exc)
        r.failures.append(f"probe failed: {exc}")
    return r


_e5_probe: Optional[E5Readiness] = None


def e5_readiness(conn) -> E5Readiness:
    """Cached readiness assessment, probed once per process."""
    global _e5_probe
    if _e5_probe is None:
        _e5_probe = assess_e5_readiness(conn)
        logger.info("Emerging topics: %s", _e5_probe.describe())
    return _e5_probe


def e5_available(conn, for_enforce: bool = False) -> bool:
    """May this tenant's E5 index be used, for observation or for acting?"""
    readiness = e5_readiness(conn)
    return readiness.enforce_ready if for_enforce else readiness.shadow_ready


def reset_probe_cache() -> None:
    """Forget the cached probe. For tests."""
    global _e5_probe
    _e5_probe = None


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
