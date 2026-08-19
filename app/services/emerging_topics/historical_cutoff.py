"""Per-theme cutoff for deciding whether a theme already had older coverage.

There is no universal cosine distance that means "related" in this embedding
space. deberta-base is anisotropic: on the bugfixing corpus, distances from a
real query to 5,000 random articles ran 0.072–0.455 with a median of 0.148, so
the 0.85 the pipeline shipped with matched 100% of articles and decided nothing.
Every theme with any older coverage became an ongoing topic.

A fixed replacement constant would fail the same way, just at a different
corpus or after the next encoder change. The cutoff is calibrated per theme
instead, from two distributions measured at the moment of the decision:

    cutoff = min(
        p75(distances of the theme's own validated articles) + 0.02,
        p10(distances to a background sample of in-scope historical articles),
        0.20,
    )

The first term says "about as close as this theme's own articles are". The
second says "closer than the nearest tenth of unrelated older material", which
is what makes it adaptive to the corpus rather than to the encoder. The third is
a hard ceiling so a degenerate calibration cannot open the gate.

Passing that cutoff is necessary but not sufficient. A theme counts as ongoing
only with at least ``min_articles`` qualifying historical articles spanning at
least two sources and two publication dates — one syndicated wire story
republished five times is not a history of coverage.

When calibration data is too thin to trust, a deliberately tight provisional
cutoff is used instead. The bias throughout is towards ``llm_proposed``:
wrongly suppressing a genuinely new topic is the worse failure, because it is
invisible — the topic simply never appears.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

# Hard ceiling: no calibration may produce a looser cutoff than this.
MAX_CUTOFF = 0.20

# Used when either distribution is too small to calibrate from. Tighter than
# any expected calibrated value, so thin data errs towards "new".
PROVISIONAL_CUTOFF = 0.12

# Slack added to the theme's own p75, so an article marginally further out than
# the theme's typical member still counts.
THEME_SLACK = 0.02

# Below these counts a percentile is noise rather than a distribution.
MIN_THEME_DISTANCES = 4
MIN_BACKGROUND_DISTANCES = 20

# Corroboration required before older coverage is called a history.
MIN_SOURCES = 2
MIN_DATES = 2


def percentile(values: Sequence[float], fraction: float) -> Optional[float]:
    """Linear-interpolated percentile of an unsorted sequence.

    Returns None for an empty input. Implemented here rather than pulled from
    numpy so this module stays importable in the lightweight paths.
    """
    cleaned = sorted(float(v) for v in values if v is not None)
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return cleaned[0]

    position = fraction * (len(cleaned) - 1)
    lower = int(position)
    upper = min(lower + 1, len(cleaned) - 1)
    weight = position - lower
    return cleaned[lower] * (1 - weight) + cleaned[upper] * weight


@dataclass
class CutoffDecision:
    """What was decided, and everything needed to explain it in one log line."""
    cutoff: float
    provisional: bool
    is_ongoing: bool
    qualifying_articles: int = 0
    qualifying_sources: int = 0
    qualifying_dates: int = 0
    candidates_examined: int = 0
    theme_p75: Optional[float] = None
    background_p10: Optional[float] = None
    reason: str = ""

    def describe(self) -> str:
        """One line naming the cutoff and what actually qualified under it.

        Deliberately reports the qualifying count, not the top-k retrieval
        count. The old log said "50 historical articles" for every theme,
        because 50 was the retrieval limit — it read as evidence and was an
        artefact.
        """
        basis = "provisional" if self.provisional else (
            f"p75={self.theme_p75:.3f}+{THEME_SLACK}, p10={self.background_p10:.3f}"
            if self.theme_p75 is not None and self.background_p10 is not None
            else "partial calibration"
        )
        return (
            f"cutoff={self.cutoff:.3f} ({basis}); "
            f"{self.qualifying_articles} of {self.candidates_examined} historical "
            f"candidates qualified across {self.qualifying_sources} sources and "
            f"{self.qualifying_dates} dates -> "
            f"{'ongoing_topic' if self.is_ongoing else 'llm_proposed'}"
            f"{'; ' + self.reason if self.reason else ''}"
        )


def calibrate_cutoff(
    theme_distances: Sequence[float],
    background_distances: Sequence[float],
) -> tuple:
    """Return ``(cutoff, provisional, theme_p75, background_p10)``.

    ``provisional`` is True when either distribution was too thin to calibrate
    from, in which case the conservative constant is used.
    """
    theme_values = [d for d in (theme_distances or []) if d is not None]
    background_values = [d for d in (background_distances or []) if d is not None]

    theme_p75 = (
        percentile(theme_values, 0.75)
        if len(theme_values) >= MIN_THEME_DISTANCES else None
    )
    background_p10 = (
        percentile(background_values, 0.10)
        if len(background_values) >= MIN_BACKGROUND_DISTANCES else None
    )

    if theme_p75 is None or background_p10 is None:
        return (PROVISIONAL_CUTOFF, True, theme_p75, background_p10)

    cutoff = min(theme_p75 + THEME_SLACK, background_p10, MAX_CUTOFF)
    # A non-positive cutoff would admit nothing at all; fall back rather than
    # silently classifying every theme as new for an unrelated reason.
    if cutoff <= 0:
        return (PROVISIONAL_CUTOFF, True, theme_p75, background_p10)
    return (cutoff, False, theme_p75, background_p10)


def decide(
    theme_distances: Sequence[float],
    background_distances: Sequence[float],
    candidates: List[Dict[str, Any]],
    min_articles: int = 3,
) -> CutoffDecision:
    """Classify a theme from its calibration data and historical candidates.

    ``candidates`` are the nearest in-scope historical articles, each a dict
    with ``distance``, ``news_source``, and ``publication_day``.
    """
    cutoff, provisional, theme_p75, background_p10 = calibrate_cutoff(
        theme_distances, background_distances
    )

    qualifying = [c for c in candidates if c.get("distance") is not None
                  and float(c["distance"]) <= cutoff]
    sources = {c.get("news_source") for c in qualifying if c.get("news_source")}
    dates = {c.get("publication_day") for c in qualifying if c.get("publication_day")}

    decision = CutoffDecision(
        cutoff=cutoff,
        provisional=provisional,
        is_ongoing=False,
        qualifying_articles=len(qualifying),
        qualifying_sources=len(sources),
        qualifying_dates=len(dates),
        candidates_examined=len(candidates),
        theme_p75=theme_p75,
        background_p10=background_p10,
    )

    if len(qualifying) < min_articles:
        decision.reason = f"fewer than {min_articles} qualifying articles"
        return decision
    if len(sources) < MIN_SOURCES:
        decision.reason = (
            f"only {len(sources)} source(s); a single outlet republishing a "
            "story is not a history of coverage"
        )
        return decision
    if len(dates) < MIN_DATES:
        decision.reason = (
            f"only {len(dates)} publication date(s); one day of coverage is a "
            "moment, not a history"
        )
        return decision

    decision.is_ongoing = True
    return decision
