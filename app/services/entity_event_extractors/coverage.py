"""Events from somebody else's reporting, and corroboration for ours.

This extractor was registered and switched off from the start, with the reason
attached: deterministic rules cannot tell an article *about* a company from one
that merely names it. That was true, and it stayed true. What changed is where
the judgement happens. ``market_post_review.review_earned`` now reads trade
press once, decides which company it concerns and what it reports, and writes
that down. This extractor reads the decision, exactly as ``owned_post`` reads
the vendor-post decision, and calls no model itself.

The more valuable half of the work is not creating events. It is **raising the
belief in events we already have.** A vendor announces a launch on LinkedIn and
it is recorded as ``vendor_claim``, which is all a company saying it
establishes. When a trade publication reports the same launch, attaching that
article to the existing event moves it to ``single_source`` — and two
publications make it ``corroborated``. Creating a second event instead would
leave the first still resting on the vendor's word and put the same launch on
the wire twice.

So each reviewed article is first offered to the events we already hold.

Matching is deliberately hard to satisfy. Sharing a company and an event type
is not enough: one vendor can ship two products in a fortnight, and attaching
the press about the second to the first would manufacture exactly the false
agreement this system exists to detect. The article and the event must also
share a **distinctive token** — a product name, a sum of money, a counterparty
— and the vendor's own name is excluded from that test, because both texts
carry it by construction and it therefore proves nothing.

When nothing matches, the article becomes its own event at ``single_source``.
That is the honest reading: somebody unconnected to the company reported it,
and nobody else has yet.

A press-release wire is not a newsroom. GlobeNewswire, PR Newswire and the rest
carry the company's own announcement verbatim for a fee, so treating one as an
outside source would let any vendor buy its way to ``corroborated`` — the exact
failure the independence key exists to prevent. Those articles still record
their event, because the launch did happen; their evidence is just keyed to the
vendor rather than to the publisher, so it lifts nothing. ``report_corpus``
already maintains that list for the same reason, and this reads it rather than
starting a second one.

The asymmetry is deliberate. A corroboration we miss understates what we know.
A corroboration we invent is manufactured consensus. When the rule is unsure it
creates a separate event, which is the recoverable mistake.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import text

from app.services import entity_events
from app.services.entity_event_extractors.owned_post import (
    KIND_TO_EVENT, NOT_EVENTS, _parsed,
)

logger = logging.getLogger(__name__)

#: How far apart a report and the event it describes may sit. Trade press runs
#: a few days behind an announcement and occasionally ahead of it, so the
#: window is symmetric. Widening it does not find more corroboration — the
#: token test is what decides — it only admits more chances to be wrong.
MATCH_DAYS = int(os.getenv("MARKET_COVERAGE_MATCH_DAYS", "14") or 14)

#: How far a report may sit *before* the event it corroborates. Not symmetric
#: after all: a report two weeks ahead of an announcement is almost always
#: about something else. securitybrief.in's 19 Aug piece on Intezer's response
#: workflows was attached to Intezer's 2 Sep Amplify Hub launch, exactly 14
#: days later, and made that launch read as independently reported. A couple
#: of days covers an embargo lifting early or a time-zone gap.
MATCH_DAYS_BEFORE = int(os.getenv("MARKET_COVERAGE_MATCH_DAYS_BEFORE", "2") or 2)

#: Words that appear in every other security headline and distinguish nothing.
#: A shared "security" is not evidence that two texts describe one event.
_COMMON = frozenset("""
security operations platform company announces announced announcement today
new launch launches launched release released available general partnership
partners customer customers funding round raises raised million billion series
acquires acquisition agreement solution solutions product products technology
technologies cyber cybersecurity threat threats detection response automation
intelligence artificial machine learning agentic agent agents team teams
enterprise enterprises business businesses market markets industry report
reports first leading global support supports integration integrations
""".split())

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9&.\-]*|\$?\d[\d.,]*[MBK]?")


_LOOKS_LIKE_DOMAIN = re.compile(r"^[a-z0-9][a-z0-9.\-]*\.[a-z]{2,}$")


def _source_key(news_source: Optional[str], url: Optional[str],
                bias_source: Optional[str]) -> str:
    """One key per publisher, whichever field carried its name.

    Earned rows in this corpus arrive with an empty ``url`` — all six of the
    first reviewed batch did — so the shared helper falls through to
    ``source:<news_source>``. That is usually the domain already, but not
    always spelled alike: the corpus holds both ``Futurum`` and
    ``futurum.com``. Keyed verbatim those are two independent voices, and one
    publisher would corroborate itself. Anything domain-shaped is normalised
    to a ``domain:`` key so the two spellings collapse, which is the whole
    distinction between widely reported and widely copied.
    """
    key = entity_events.independence_key_for_article(news_source, url, bias_source)
    if not key.startswith("source:"):
        return key
    name = key.split(":", 1)[1].strip().lower()
    if name.startswith("www."):
        name = name[4:]
    return f"domain:{name}" if _LOOKS_LIKE_DOMAIN.match(name) else f"source:{name}"


def _is_wire(news_source: Optional[str], url: Optional[str]) -> bool:
    """A paid distribution channel rather than a newsroom."""
    from urllib.parse import urlsplit

    from app.services.report_corpus import wire_sources

    wires = wire_sources()
    if not wires:
        return False
    host = (urlsplit(url or "").netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    source = (news_source or "").strip().lower()
    return any(w in host or w == source for w in wires)


def _distinctive(blob: str, exclude: Set[str]) -> Set[str]:
    """Tokens specific enough that sharing one means something.

    Three things qualify: a token carrying a digit (``$33M``, ``4.7``), a
    capitalised word (a product, a person, a counterparty), and a long
    lowercase word that is not market boilerplate. Everything in ``exclude``
    is dropped — that is where the vendor's own name goes.
    """
    out: Set[str] = set()
    for raw in _WORD.findall(blob or ""):
        token = raw.strip(".,;:&-")
        if len(token) < 3:
            continue
        low = token.lower()
        if low in exclude or low in _COMMON:
            continue
        if any(ch.isdigit() for ch in token):
            out.add(low)
        elif token[:1].isupper():
            out.add(low)
        elif len(token) >= 8:
            out.add(low)
    return out


def _name_tokens(*names: Optional[str]) -> Set[str]:
    """Every word of the company's names, which both texts share anyway."""
    out: Set[str] = set()
    for name in names:
        for raw in _WORD.findall(name or ""):
            token = raw.strip(".,;:&-").lower()
            if token:
                out.add(token)
                # "Secure.com" and "secure" should both be excluded.
                out.update(p for p in token.split(".") if len(p) >= 3)
    return out


def _candidate_events(conn, brand_id: int, event_type: str,
                      published: Optional[datetime]) -> List[Dict[str, Any]]:
    """Events this article could be reporting, newest first.

    An undated event is always in range: nobody recorded when it happened, so
    no date can rule it out. A dated one must sit inside the window.
    """
    params: Dict[str, Any] = {"b": brand_id, "t": event_type}
    window = ""
    if published is not None:
        window = ("AND (e.occurred_at IS NULL"
                  "     OR e.occurred_at BETWEEN :lo AND :hi)")
        # The report is published at most MATCH_DAYS after the event and at
        # most MATCH_DAYS_BEFORE ahead of it.
        params["lo"] = published - timedelta(days=MATCH_DAYS)
        params["hi"] = published + timedelta(days=MATCH_DAYS_BEFORE)

    rows = conn.execute(text(f"""
        SELECT e.id, e.title, e.description, e.occurred_at, e.corroboration
          FROM bw_entity_events e
          JOIN bw_entity_event_entities ee ON ee.event_id = e.id
         WHERE ee.brand_id = :b
           AND e.event_type = :t
           AND e.status NOT IN ('superseded', 'rejected')
           {window}
         ORDER BY e.occurred_at DESC NULLS LAST, e.id DESC
         LIMIT 25
    """), params).mappings().all()
    return [dict(r) for r in rows]


def _best_match(article_blob: str, events: List[Dict[str, Any]],
                exclude: Set[str]) -> Optional[Dict[str, Any]]:
    """The event this article corroborates, or None.

    Scored on how many distinctive tokens the two texts share. Ties go to the
    event listed first, which is the most recent — a report is more likely to
    be about the latest thing than an older one of the same shape.
    """
    article = _distinctive(article_blob, exclude)
    if not article:
        return None
    best, best_score = None, 0
    for event in events:
        blob = f"{event.get('title') or ''} {event.get('description') or ''}"
        shared = article & _distinctive(blob, exclude)
        if len(shared) > best_score:
            best, best_score = {**event, "shared": sorted(shared)}, len(shared)
    return best


def run(conn, *, brand_id: Optional[int] = None,
        limit: Optional[int] = None) -> Dict[str, Any]:
    # ``about``, not ``mentions``. The link table already holds 56 earned-news
    # rows written by the mention pipeline, which records that a name appeared.
    # An appearance is not a story about the company, and building an event
    # from one is the mistake this extractor was switched off to avoid.
    where = ["ma.review_verdict = 'signal'", "l.channel = 'earned_news'",
             "l.relationship = 'about'"]
    params: Dict[str, Any] = {"lim": limit or 2000}
    if brand_id is not None:
        where.append("l.brand_id = :brand_id")
        params["brand_id"] = brand_id

    rows = conn.execute(text(f"""
        SELECT ma.article_uri, ma.review_kind, ma.review_reason,
               l.brand_id, a.title, a.summary, a.publication_date,
               a.news_source, a.url, a.bias_source, b.display_name
          FROM bw_market_articles ma
          JOIN bw_entity_content_links l ON l.article_uri = ma.article_uri
          JOIN articles a ON a.uri = ma.article_uri
          JOIN bw_brands b ON b.id = l.brand_id
         WHERE {' AND '.join(where)}
         ORDER BY ma.article_uri
         LIMIT :lim
    """), params).mappings().all()

    created = corroborated = skipped = wire = 0
    raised: Dict[str, int] = {}
    for row in rows:
        kind = (row["review_kind"] or "").lower()
        event_type = KIND_TO_EVENT.get(kind)
        if event_type is None:
            skipped += 1
            continue

        published = _parsed(row["publication_date"])
        # The publisher's domain is one voice however many times it runs the
        # story, and it is not the vendor's. This is what lifts corroboration —
        # except on a wire, where the vendor is the author and the key says so.
        if _is_wire(row["news_source"], row["url"]):
            key = f"owned:wire:{row['display_name']}".lower()
            wire += 1
        else:
            key = _source_key(row["news_source"], row["url"], row["bias_source"])
        excerpt = (row["summary"] or row["title"] or "")[:1000]
        blob = f"{row['title'] or ''} {row['summary'] or ''} {row['review_reason'] or ''}"
        exclude = _name_tokens(row["display_name"])

        match = _best_match(
            blob,
            _candidate_events(conn, int(row["brand_id"]), event_type, published),
            exclude)

        if match is not None:
            before = match["corroboration"]
            entity_events.add_evidence(
                conn, int(match["id"]), evidence_type="article",
                article_uri=row["article_uri"], relationship="supports",
                independence_key=key, excerpt=excerpt)
            after = entity_events.recompute_corroboration(
                conn, int(match["id"]))["corroboration"]
            entity_events.project_to_markets(conn, int(match["id"]))
            corroborated += 1
            if after != before:
                raised[f"{before}->{after}"] = raised.get(f"{before}->{after}", 0) + 1
            continue

        # Nobody had this. The press is the first and only source for it.
        entity_events.record(
            conn,
            event_type=event_type,
            title=(row["title"] or row["review_reason"] or "")[:500],
            description=(row["summary"] or row["review_reason"] or "")[:2000],
            brand_ids={int(row["brand_id"]): "subject"},
            attributes={"reviewer_kind": kind, "announced_by": "press"},
            occurred_at=published,
            precision="day" if published else "unknown",
            published_at=published,
            subtype=kind,
            evidence=[{
                "evidence_type": "article",
                "article_uri": row["article_uri"],
                "relationship": "originates",
                "independence_key": key,
                "excerpt": excerpt,
            }])
        created += 1

    return {"candidates": len(rows), "created": created,
            "corroborated": corroborated, "corroboration_raised": raised,
            "wire_not_independent": wire,
            "skipped_not_an_event": skipped}
