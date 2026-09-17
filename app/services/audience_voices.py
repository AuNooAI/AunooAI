"""What each audience says about a brand.

A weight-management provider wanted to see what doctors think of it next to
what patients think of it. Sentiment alone cannot answer that, because it
flattens a referring GP, a programme participant, a journalist and the
company's own account into one number. The social evaluation step now names
the author's role on every post (``articles.author_role``, see
``social_eval_service.AUTHOR_ROLES``); this module reads those roles back
per brand and window, and can ask a model for a short digest of what one
audience is saying, with verbatim quotes as evidence.

Two read paths, matching the Social tab: per-mention rows when Entity
Intelligence is on, the brand topic otherwise.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.services.social_eval_service import AUTHOR_ROLES, SOCIAL_SOURCES

logger = logging.getLogger(__name__)

# Display names and the order roles are shown in. Health roles first because
# the first customer for this view is a health provider; the UI ranks by
# volume anyway, so the order only breaks ties.
ROLE_LABELS: Dict[str, Dict[str, str]] = {
    "patient":      {"label": "Patients",      "plural": "patients",      "hint": "People on, referred to, or weighing up the programme or treatment"},
    "clinician":    {"label": "Clinicians",    "plural": "clinicians",    "hint": "Doctors, GPs, nurses, dietitians and other health professionals speaking as such"},
    "caregiver":    {"label": "Caregivers",    "plural": "caregivers",    "hint": "Relatives or carers speaking about someone else's care"},
    "customer":     {"label": "Customers",     "plural": "customers",     "hint": "End users or buyers, including prospective ones"},
    "academic":     {"label": "Academics",     "plural": "academics",     "hint": "Researchers, lecturers and scientists"},
    "professional": {"label": "Professionals", "plural": "industry professionals", "hint": "People working in the brand's industry but not for the brand"},
    "employee":     {"label": "Employees",     "plural": "employees",     "hint": "Current or former staff, including Glassdoor reviews"},
    "journalist":   {"label": "Press",         "plural": "journalists",   "hint": "Reporters, outlets and newsletter authors"},
    "investor":     {"label": "Investors",     "plural": "investors",     "hint": "Shareholders, equity analysts and VCs"},
    "brand":        {"label": "Brand voice",   "plural": "brand accounts", "hint": "The company, affiliates, resellers or paid promotion"},
    "unknown":      {"label": "Bystanders",    "plural": "bystanders",    "hint": "Commenting from the sidelines: the post shows no part in the programme, the profession or the company"},
    "unclassified": {"label": "Not yet classified", "plural": "posts not yet classified", "hint": "Scored before roles existed; run the backfill"},
}

# The pair the view opens on when both sides have posts. Health first, then
# the equivalent split for other industries.
PREFERRED_PAIRS = (("clinician", "patient"), ("professional", "customer"),
                   ("academic", "customer"))

_POS = re.compile(r"positiv|optimis", re.I)
_NEG = re.compile(r"negativ|pessimis|concern|critical|alarm", re.I)


def _bucket(sentiment: Optional[str]) -> Optional[str]:
    s = sentiment or ""
    if _NEG.search(s):
        return "negative"
    if _POS.search(s):
        return "positive"
    if s:
        return "neutral"
    return None


def _net(pos: int, neu: int, neg: int) -> Optional[int]:
    n = pos + neu + neg
    return round((pos - neg) / n * 100) if n else None


def _window(days_back: int) -> tuple:
    end = datetime.now()
    start = end - timedelta(days=days_back) if days_back else datetime(1900, 1, 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%dT%H:%M:%S")


def _platform(news_source: Optional[str], platform: Optional[str]) -> str:
    if platform:
        return platform
    s = (news_source or "").lower()
    if s.startswith("xpoz:"):
        return s.split(":", 1)[1] or "social"
    if "reddit" in s:
        return "reddit"
    if "bsky" in s or "bluesky" in s:
        return "bluesky"
    if s == "glassdoor":
        return "glassdoor"
    return "social"


def _meta(raw) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            v = json.loads(raw)
            return v if isinstance(v, dict) else {}
        except ValueError:
            return {}
    return {}


# ---------------------------------------------------------------------------
# Account-level roles: the profile beats the post, the post history beats
# one post
# ---------------------------------------------------------------------------

# Market Monitor's Top voices profiles an ACCOUNT and records its part in the
# market (social_accounts.metadata.market_role). That reading comes from the
# bio plus a sample of posts, so it is stronger evidence than the text of one
# post. Its list is vendor-shaped; this maps it onto the audience list.
# ``practitioner`` is "works in the field or is a customer" — a clinician on a
# health tenant, an industry professional elsewhere.
MARKET_ROLE_MAP = {
    "vendor": "brand",
    "vendor_staff": "employee",
    "practitioner": None,          # in the field, but which side? see FIELD_ROLES below
    "analyst_or_press": "journalist",
    "reseller": "brand",
    "promoter_or_bot": "brand",
    "unrelated": None,             # says nothing about who they are; keep the post's reading
}
HEALTH_ROLES = {"patient", "clinician", "caregiver"}
# "practitioner" on a market profile means "in the market's field", which
# covers both a prescribing GP and the patient on the programme. The profile
# confirms the account belongs to the conversation; which side it is on comes
# from what the account's posts say. Only when the posts say nothing does the
# tenant's industry decide (clinician on a health site, professional elsewhere).
FIELD_ROLES = {"patient", "clinician", "caregiver", "customer", "professional", "academic"}
_VOTE_MIN_POSTS = 2
_VOTE_MIN_SHARE = 0.6


def _author_key(platform: Optional[str], author: Optional[str]) -> Optional[tuple]:
    if not platform or not author:
        return None
    return (str(platform).lower(), str(author).strip().lstrip("@").lower())


def account_audiences(conn, pairs, health: Optional[bool] = None) -> Dict[tuple, Dict[str, Any]]:
    """Audience role per (platform, handle) from the account, not the post.

    Two sources, in order of strength: the market profile's role when the
    account was profiled, else a majority vote over every post of theirs
    the social evaluation has classified (at least two posts, at least 60 %
    agreeing, ``unknown`` never votes). Returns only the accounts where one
    of the two gave an answer.

    ``health`` decides what a profiled practitioner is; None = decide from
    the votes themselves (any patient/clinician/caregiver reading means a
    health tenant).
    """
    keys = sorted({k for k in pairs if k})
    if not keys:
        return {}
    plats = [k[0] for k in keys]
    handles = [k[1] for k in keys]

    votes: Dict[tuple, Dict[str, int]] = {}
    for plat, author, role, n in conn.execute(text("""
        SELECT LOWER(COALESCE(a.social_meta->>'platform', SPLIT_PART(a.news_source, ':', 2))),
               LOWER(a.social_meta->>'author'), a.author_role, COUNT(*)
          FROM articles a
         WHERE a.author_role IS NOT NULL AND a.author_role <> 'unknown'
           AND a.social_meta->>'author' IS NOT NULL
           AND (LOWER(COALESCE(a.social_meta->>'platform', SPLIT_PART(a.news_source, ':', 2))),
                LOWER(a.social_meta->>'author'))
               IN (SELECT LOWER(p), LOWER(h) FROM UNNEST(:plats, :handles) AS t(p, h))
         GROUP BY 1, 2, 3
    """), {"plats": plats, "handles": handles}).fetchall():
        votes.setdefault((plat, author), {})[role] = int(n)

    if health is None:
        health = any(r in HEALTH_ROLES for v in votes.values() for r in v)

    out: Dict[tuple, Dict[str, Any]] = {}
    try:
        profiled = conn.execute(text("""
            SELECT LOWER(platform), handle_canonical, metadata->>'market_role',
                   metadata->>'market_org', metadata->>'audience_role'
              FROM social_accounts
             WHERE metadata->>'market_role' IS NOT NULL
               AND (LOWER(platform), handle_canonical)
                   IN (SELECT LOWER(p), LOWER(h) FROM UNNEST(:plats, :handles) AS t(p, h))
        """), {"plats": plats, "handles": handles}).fetchall()
    except Exception as e:  # noqa: BLE001 - social_accounts may predate metadata
        logger.debug("account_audiences: profile lookup failed: %s", e)
        profiled = []
    for plat, handle, market_role, org, audience in profiled:
        # A vendor's own account is the brand's voice whatever its posts read
        # as: Oviva's UK account came back "patient" because it posts patient
        # stories. The market role is the stronger fact here.
        if market_role in ("vendor", "reseller", "promoter_or_bot"):
            audience = "brand"
        elif market_role == "vendor_staff" and audience not in ("investor", "employee"):
            audience = "employee"
        # A profile read with the account's on-brand posts in view names the
        # audience directly; that answers the question and needs no mapping.
        if audience and audience in AUTHOR_ROLES and audience != "unknown":
            out[(plat, handle)] = {"role": audience, "source": "account_profile",
                                   "market_role": market_role, "org": org, "n": None}
            continue
        mapped = MARKET_ROLE_MAP.get(market_role)
        if market_role == "practitioner":
            dist = votes.get((plat, handle), {})
            field = {r: n for r, n in dist.items() if r in FIELD_ROLES}
            if field:
                mapped = max(field.items(), key=lambda kv: kv[1])[0]
            else:
                # No classified post to say which side: leave it to the post
                # itself (apply_account_roles keeps a field role) and fall back
                # to the industry default only when that is unknown too.
                out[(plat, handle)] = {"role": None, "source": "account_profile",
                                       "market_role": market_role, "org": org, "n": None,
                                       "fallback": "clinician" if health else "professional"}
                continue
        if mapped:
            out[(plat, handle)] = {"role": mapped, "source": "account_profile",
                                   "market_role": market_role, "org": org, "n": None}

    for key, dist in votes.items():
        if key in out:
            continue
        total = sum(dist.values())
        role, n = max(dist.items(), key=lambda kv: kv[1])
        if total >= _VOTE_MIN_POSTS and n / total >= _VOTE_MIN_SHARE:
            out[key] = {"role": role, "source": "account_posts", "market_role": None,
                        "org": None, "n": total}
    return out


def apply_account_roles(conn, posts: List[Dict[str, Any]], *,
                        platform_key: str = "platform", author_key: str = "author",
                        role_key: str = "author_role") -> int:
    """Override post-level roles with account-level ones in place.

    Each post keeps its own reading in ``post_role`` and says where the final
    role came from in ``author_role_source`` (post, account_profile,
    account_posts). Glassdoor rows (employee by construction) and posts with
    no author are left alone. Returns how many posts changed.
    """
    pairs = {}
    for p in posts:
        if p.get(role_key) == "employee" and (p.get(platform_key) == "glassdoor"):
            continue
        k = _author_key(p.get(platform_key), p.get(author_key))
        if k:
            pairs[id(p)] = k
    health = any(p.get(role_key) in HEALTH_ROLES for p in posts) or None
    resolved = account_audiences(conn, set(pairs.values()), health=health) if pairs else {}
    changed = 0
    for p in posts:
        p.setdefault("post_role", p.get(role_key))
        p.setdefault("author_role_source", "post")
        hit = resolved.get(pairs.get(id(p)))
        if not hit:
            continue
        role = hit["role"]
        if role is None:
            # A profiled practitioner with no post history to pick a side:
            # this post's own reading stands when it names a side.
            own = p.get(role_key)
            role = own if own in FIELD_ROLES else hit.get("fallback")
            if not role:
                continue
        if role != p.get(role_key):
            changed += 1
        p[role_key] = role
        p["author_role_source"] = hit["source"]
        if hit.get("market_role"):
            p["account_market_role"] = hit["market_role"]
        if hit.get("org"):
            p["account_org"] = hit["org"]
    return changed


def _rows(conn, *, brand_id: int, display_name: str, days_back: int,
          mention_read: bool, min_relevance: float) -> List[Dict[str, Any]]:
    sd, ed = _window(days_back)
    fp = ("NOT EXISTS (SELECT 1 FROM bw_finding_reviews r "
          "WHERE r.article_uri = a.uri AND r.status = 'false_positive')")
    if mention_read:
        rows = conn.execute(text(f"""
            SELECT a.uri, a.title, a.summary, a.news_source, a.publication_date,
                   a.social_meta, COALESCE(m.sentiment, a.sentiment) AS sentiment,
                   m.relevance, a.author_role, a.author_role_reason,
                   m.channel, m.platform
              FROM bw_entity_mentions m
              JOIN articles a ON a.uri = m.article_uri
             WHERE m.brand_id = :b
               AND m.channel IN ('public_social', 'community', 'employee')
               AND m.status <> 'false_positive'
               AND m.relevance >= :min_rel
               AND a.publication_date >= :sd AND a.publication_date <= :ed
               AND {fp}
             ORDER BY a.publication_date DESC
        """), {"b": brand_id, "min_rel": min_relevance, "sd": sd, "ed": ed}
        ).mappings().all()
    else:
        src = " OR ".join(f"LOWER(a.news_source) LIKE :s{i}" for i in range(len(SOCIAL_SOURCES)))
        params: Dict[str, Any] = {"t": f"Brand Monitoring {display_name}",
                                  "min_rel": min_relevance, "sd": sd, "ed": ed}
        for i, s in enumerate(SOCIAL_SOURCES):
            params[f"s{i}"] = f"%{s}%"
        rows = conn.execute(text(f"""
            SELECT a.uri, a.title, a.summary, a.news_source, a.publication_date,
                   a.social_meta, a.sentiment, a.topic_alignment_score AS relevance,
                   a.author_role, a.author_role_reason,
                   NULL AS channel, NULL AS platform
              FROM articles a
             WHERE a.topic = :t
               AND (({src}) OR a.news_source = 'Glassdoor')
               AND a.topic_alignment_score >= :min_rel
               AND a.publication_date >= :sd AND a.publication_date <= :ed
               AND {fp}
             ORDER BY a.publication_date DESC
        """), params).mappings().all()

    out: List[Dict[str, Any]] = []
    seen = set()
    for r in rows:
        if r["uri"] in seen:
            continue
        seen.add(r["uri"])
        meta = _meta(r["social_meta"])
        is_glassdoor = (r["news_source"] == "Glassdoor" or r["channel"] == "employee")
        role = "employee" if is_glassdoor else (r["author_role"] or "unclassified")
        body = (r["summary"] or r["title"] or "").strip()
        out.append({
            "uri": r["uri"],
            "title": r["title"],
            "text": body,
            "platform": _platform(r["news_source"], r["platform"]),
            "publication_date": str(r["publication_date"]) if r["publication_date"] else None,
            "sentiment": _bucket(r["sentiment"]),
            "relevance": round(float(r["relevance"]), 3) if r["relevance"] is not None else None,
            "author": meta.get("author") or meta.get("author_handle") or None,
            "engagement": sum(int(meta.get(k) or 0) for k in ("likes", "reposts", "comments")),
            "author_role": role,
            "author_role_reason": r["author_role_reason"],
        })
    # A profiled account, or an account whose other posts all read the same
    # way, outranks the reading of one post.
    apply_account_roles(conn, out)
    fold_customers_into_patients(out)
    return out


def fold_customers_into_patients(posts: List[Dict[str, Any]]) -> int:
    """On a health brand, show "customer" posts under Patients.

    The role list is shared with publishers and vendors, where "customer" is
    the natural word. For a treatment or programme the classifier is told to
    call every user a patient, so the few posts that still come back
    "customer" are people weighing up paying for it, or a partner or insurer
    paying on someone's behalf. Splitting them out gave Oviva a one-post
    audience with a -100 net score, which reads as a finding and is not one.
    The brand counts as a health brand when any of its posts carries a
    patient, clinician or caregiver role. Returns how many posts were folded;
    each keeps the original reading in ``author_role_folded_from``.
    """
    if not any(p.get("author_role") in HEALTH_ROLES for p in posts):
        return 0
    n = 0
    for p in posts:
        if p.get("author_role") == "customer":
            p["author_role_folded_from"] = "customer"
            p["author_role"] = "patient"
            n += 1
    return n


# ---------------------------------------------------------------------------
# Profiling the accounts behind a brand's posts
# ---------------------------------------------------------------------------

PROFILABLE_PLATFORMS = {"twitter", "bluesky", "reddit", "instagram", "tiktok"}


def profile_context(conn, brand_id: int, display_name: str) -> str:
    """The name the profiler frames the account with: the market the brand
    sits in when there is one, so a Noom poster is read against the same
    weight-management market as an Oviva poster; the brand name otherwise."""
    try:
        row = conn.execute(text("""
            SELECT m.name FROM bw_market_brands mb
              JOIN bw_markets m ON m.id = mb.market_id
             WHERE mb.brand_id = :b ORDER BY m.id LIMIT 1
        """), {"b": brand_id}).fetchone()
        if row and row[0]:
            return str(row[0])
    except Exception as exc:  # noqa: BLE001 — no market tables on some sites
        logger.debug("profile_context: %s", exc)
    return display_name


def posters_to_profile(conn, *, brand_id: int, display_name: str, days_back: int = 90,
                       mention_read: bool = False, min_relevance: float = 0.4,
                       refresh: bool = False, limit: int = 80) -> List[Dict[str, Any]]:
    """The accounts behind this brand's posts that have no profile yet.

    Oviva's Voices table settled because nearly every account posting about it
    had been profiled under Top voices, and a profile turns a post the model
    could not place into a definite audience. Noom and WeightWatchers had no
    profiles, so a third to a half of their posts sat as bystanders. This
    lists the brand's posters, most posts first, so the same treatment can be
    run for any brand. ``refresh`` includes accounts already profiled.
    """
    posts = _rows(conn, brand_id=brand_id, display_name=display_name,
                  days_back=days_back, mention_read=mention_read,
                  min_relevance=min_relevance)
    acc: Dict[tuple, Dict[str, Any]] = {}
    for p in posts:
        key = _author_key(p.get("platform"), p.get("author"))
        if not key or key[0] not in PROFILABLE_PLATFORMS:
            continue
        a = acc.setdefault(key, {"platform": key[0], "handle": p["author"].lstrip("@"),
                                 "posts": 0, "engagement": 0, "unplaced": 0,
                                 "profiled": p.get("author_role_source") == "account_profile"})
        a["posts"] += 1
        a["engagement"] += int(p.get("engagement") or 0)
        if p.get("author_role") in ("unknown", "unclassified"):
            a["unplaced"] += 1
    if not refresh:
        try:
            rows = conn.execute(text("""
                SELECT LOWER(platform), LOWER(handle) FROM social_accounts
                 WHERE last_profiled_at IS NOT NULL
                   AND metadata->>'audience_role' IS NOT NULL
            """)).fetchall()
            done = {(r[0], r[1]) for r in rows}
        except Exception as exc:  # noqa: BLE001
            logger.debug("posters_to_profile: %s", exc)
            done = set()
        acc = {k: v for k, v in acc.items() if k not in done and not v["profiled"]}
    out = sorted(acc.values(), key=lambda a: (-a["unplaced"], -a["posts"], -a["engagement"]))
    return out[:limit]


def voices(conn, *, brand_id: int, display_name: str, days_back: int = 90,
           mention_read: bool = False, min_relevance: float = 0.4,
           per_role_limit: int = 60) -> Dict[str, Any]:
    """Per-role rollup of what was said about one brand in the window."""
    posts = _rows(conn, brand_id=brand_id, display_name=display_name,
                  days_back=days_back, mention_read=mention_read,
                  min_relevance=min_relevance)
    by_role: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in posts:
        by_role[p["author_role"]].append(p)

    roles = []
    for role, items in by_role.items():
        pos = sum(1 for p in items if p["sentiment"] == "positive")
        neg = sum(1 for p in items if p["sentiment"] == "negative")
        neu = sum(1 for p in items if p["sentiment"] == "neutral")
        platforms: Dict[str, int] = defaultdict(int)
        for p in items:
            platforms[p["platform"]] += 1
        meta = ROLE_LABELS.get(role, {"label": role.title(), "plural": role, "hint": ""})
        roles.append({
            "role": role,
            "label": meta["label"],
            "hint": meta["hint"],
            "n": len(items),
            "positive": pos, "neutral": neu, "negative": neg,
            "net": _net(pos, neu, neg),
            "by_platform": dict(platforms),
            "posts": items[:per_role_limit],
        })
    roles.sort(key=lambda r: (-r["n"], list(ROLE_LABELS).index(r["role"])
                              if r["role"] in ROLE_LABELS else 99))

    present = {r["role"] for r in roles if r["role"] not in ("brand", "unknown", "unclassified")}
    focus: List[str] = []
    for a, b in PREFERRED_PAIRS:
        if a in present and b in present:
            focus = [a, b]
            break
    if not focus:
        focus = [r["role"] for r in roles
                 if r["role"] not in ("brand", "unknown", "unclassified")][:2]

    unclassified = len(by_role.get("unclassified", []))
    notes: List[str] = []
    if not posts:
        notes.append("No on-brand social or community posts about this brand in "
                     "the window. That is a collection gap, not evidence that "
                     "nobody is talking.")
    if unclassified:
        notes.append(f"{unclassified} post(s) were scored before author roles existed "
                     "and are not yet classified.")
    return {
        "brand_id": brand_id,
        "brand": display_name,
        "days_back": days_back,
        "min_relevance": min_relevance,
        "total": len(posts),
        "classified": len(posts) - unclassified,
        "focus": focus,
        "roles": roles,
        "coverage_notes": notes,
        "read_path": "entity_mentions" if mention_read else "topic",
    }


# ---------------------------------------------------------------------------
# Digest: a model reads one audience's posts and says what they are saying
# ---------------------------------------------------------------------------

_DIGEST_TTL_S = 6 * 3600
# The one message a reader sees when no digest could be written. What went
# wrong goes to the log, not the page.
_DIGEST_UNAVAILABLE = "No digest could be written for this audience just now. Try again in a few minutes."
_digest_cache: Dict[str, tuple] = {}

_DIGEST_SYSTEM = (
    "You write for the company's own team. They will read this to understand what one audience "
    "is saying about them and what they could do about it. Report what the posts say; do not "
    "pass a verdict on the company or on the audience.\n"
    "Rules:\n"
    "- Attribute everything to the posts and count it: 'five of the seven posts, all from "
    "German GPs in one thread on X, say ...'. Never write what the audience thinks, feels, "
    "believes, distrusts, resents or demands; write what the posts say and how many say it.\n"
    "- Do not generalise from the sample to the whole audience. Say 'the clinicians in these "
    "posts', not 'clinicians'.\n"
    "- No verdict or severity words in your own voice: not aggressive, distrust, resent, "
    "undermined, demand, rip-off, failure, poor, crisis, alarming. Such words may appear only "
    "inside a verbatim quote.\n"
    "- Give the context the reader needs to weigh it: how many posts and accounts, which "
    "platforms and countries, whether they cluster in one thread or one event, and the date "
    "range. Use the CONTEXT facts you are given; do not invent any.\n"
    "- Group the posts into at most five themes, most common first. For each: a short neutral "
    "name, how many posts carry it, the sentiment those posts take toward the company "
    "(positive, negative, mixed or neutral), and one to three verbatim quotes copied exactly "
    "from the posts (each at most 200 characters, original language kept). When a theme is "
    "best named by the posts' own word, put that word in quotation marks: Advertising the "
    'posts call "aggressive", not Aggressive advertising.\n'
    "- Never cite post numbers or indices; name the count and, where useful, the account.\n"
    "- Then list what these posts ask for or would change, as concrete items the company "
    "could act on, each tied to the posts that raise it ('two posts ask to be contacted "
    "before a patient is sent to them for a prescription'). Only what the posts actually "
    "say; if they ask for nothing, say so.\n"
    "- Summary: at most 70 words, plain English, following the same rules.\n"
    'Respond with ONLY a JSON object: {"context": "<one sentence: posts, accounts, platforms, '
    'countries, clustering, dates>", "summary": "...", "themes": [{"theme": "...", '
    '"sentiment": "positive"|"negative"|"mixed"|"neutral", "post_count": <int>, '
    '"quotes": ["..."]}], "asks": ["..."]}. No prose outside the JSON.'
)

# Words that pass a verdict in the writer's own voice. A digest that uses one
# outside a quote is regenerated once with the rule restated; if it still
# does, the digest is returned with a tone warning rather than hidden.
# Only words that are a verdict whenever the writer uses them. "poor",
# "failure" and "demand" were on this list and flagged plain reporting
# ("outcomes reported as poor", "demand for GLP-1s"); with the rewrite
# instruction they cost a second model call and nothing else.
_VERDICT_WORDS = re.compile(
    r"\b(distrust\w*|resent\w*|undermin\w*|rip-?off|predatory|scam|dishonest|"
    r"misleading|exploit\w*)\b", re.I)
_QUOTED = re.compile(r'["\u201c\u201d][^"\u201c\u201d]*["\u201c\u201d]')


def _tone_problems(obj: Dict[str, Any]) -> List[str]:
    """Verdict words in the writer's own voice. Anything inside straight or
    curly double quotes is the posts' wording and exempt. This only steers a
    rewrite; the reader never sees it."""
    from app.services.report_style import find_severity_language
    texts = [str(obj.get("context") or ""), str(obj.get("summary") or "")]
    for t in obj.get("themes") or []:
        if isinstance(t, dict):
            texts.append(str(t.get("theme") or ""))
    texts += [str(a) for a in (obj.get("asks") or [])]
    unquoted = _QUOTED.sub("", "\n".join(texts))
    hits = {m.group(0).lower() for m in _VERDICT_WORDS.finditer(unquoted)}
    hits |= set(find_severity_language(unquoted))
    return sorted(hits)


def _parse_digest(raw: str) -> Dict[str, Any]:
    """The JSON object in a model reply, whatever surrounds it.

    A greedy first-brace-to-last-brace match broke on a reasoning model's
    reply, which puts braces in its thinking before the answer, so a good
    digest parsed as nothing. Try each opening brace and keep the first
    object that looks like a digest.
    """
    decoder = json.JSONDecoder()
    text_ = raw or ""
    for m in re.finditer(r"\{", text_):
        try:
            obj, _ = decoder.raw_decode(text_, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and ("summary" in obj or "themes" in obj):
            return obj
    return {}


def _digest_context(posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Facts the writer must not invent: size, platforms, accounts, dates."""
    authors = {(p.get("author") or "").lower() for p in posts if p.get("author")}
    platforms: Dict[str, int] = {}
    for p in posts:
        platforms[p["platform"]] = platforms.get(p["platform"], 0) + 1
    dates = sorted((p.get("publication_date") or "")[:10] for p in posts if p.get("publication_date"))
    return {"posts": len(posts), "accounts": len(authors) or None,
            "platforms": platforms,
            "from": dates[0] if dates else None, "to": dates[-1] if dates else None}


def _digest_model_name(conn) -> str:
    """The tenant's default enrichment model, falling back to a mid-tier alias."""
    env = os.getenv("VOICES_DIGEST_MODEL")
    if env:
        return env
    try:
        row = conn.execute(text(
            "SELECT default_llm_model FROM keyword_monitor_settings "
            "WHERE COALESCE(default_llm_model, '') <> '' LIMIT 1")).fetchone()
        if row and row[0]:
            return str(row[0])
    except Exception as e:  # noqa: BLE001 - settings table may not exist on old tenants
        logger.debug("voices digest: default model lookup failed: %s", e)
    return "gpt-5.4-mini"


async def digest(conn, *, brand_id: int, display_name: str, role: str,
                 days_back: int = 90, mention_read: bool = False,
                 min_relevance: float = 0.4, max_posts: int = 60) -> Dict[str, Any]:
    """Summarise what one audience says. Cached per post set for six hours."""
    if role not in AUTHOR_ROLES and role != "unclassified":
        return {"error": f"unknown role {role!r}", "role": role}
    posts = [p for p in _rows(conn, brand_id=brand_id, display_name=display_name,
                              days_back=days_back, mention_read=mention_read,
                              min_relevance=min_relevance)
             if p["author_role"] == role]
    posts.sort(key=lambda p: (-(p["engagement"] or 0), p["publication_date"] or ""))
    posts = posts[:max_posts]
    meta = ROLE_LABELS.get(role, {"label": role, "plural": role})
    base = {"brand_id": brand_id, "brand": display_name, "role": role,
            "label": meta["label"], "days_back": days_back, "post_count": len(posts)}
    if len(posts) < 2:
        return {**base, "summary": None, "themes": [],
                "note": "Fewer than two posts from this audience in the window; "
                        "nothing to summarise yet."}

    key = hashlib.sha1(("|".join(sorted(p["uri"] for p in posts))).encode()).hexdigest()
    cache_key = f"{brand_id}|{role}|{key}"
    hit = _digest_cache.get(cache_key)
    if hit and time.monotonic() - hit[0] < _DIGEST_TTL_S:
        return {**base, **hit[1], "cached": True}

    from app.ai_models import LiteLLMModel
    model_name = _digest_model_name(conn)
    model = LiteLLMModel.get_instance(model_name)
    if not model:
        logger.warning("voices digest: model %r not available", model_name)
        return {**base, "summary": None, "themes": [],
                "note": _DIGEST_UNAVAILABLE}

    from app.services.report_style import CLINICAL_STYLE
    lines = []
    for i, p in enumerate(posts, 1):
        when = (p["publication_date"] or "")[:10]
        who = f"@{p['author']}" if p.get("author") else "unknown account"
        lines.append(f"[{i}] ({p['platform']}, {who}, {when}, {p['sentiment'] or 'unrated'}) "
                     f"{p['text'][:500]}")
    ctx = _digest_context(posts)
    user = (f"BRAND: {display_name}\nAUDIENCE: {meta['plural']}\n"
            f"CONTEXT: {json.dumps(ctx)}\n"
            f"POSTS ({len(posts)}):\n" + "\n".join(lines))
    system = _DIGEST_SYSTEM + CLINICAL_STYLE
    obj: Dict[str, Any] = {}
    problems: List[str] = []
    rewrites = 0
    # Up to three calls: the draft, one retry if the reply had no usable
    # JSON, one rewrite if the draft passed verdicts in its own voice.
    for attempt in range(3):
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        if problems and obj:
            messages.append({"role": "assistant", "content": json.dumps(obj, ensure_ascii=False)})
            messages.append({"role": "user", "content":
                             "Rewrite this. It uses these words in your own voice, which the "
                             f"rules forbid outside a verbatim quote: {', '.join(problems)}. "
                             "Keep the same themes, counts and quotes; report what the posts "
                             "say and how many say it instead. Respond with ONLY the JSON object."})
        try:
            raw = await model.agenerate_response(messages)
        except Exception as e:  # noqa: BLE001
            logger.warning("voices digest failed for brand %s role %s: %s", brand_id, role, e)
            return {**base, "summary": None, "themes": [], "note": _DIGEST_UNAVAILABLE}
        parsed = _parse_digest(raw)
        if not parsed:
            logger.warning("voices digest: no JSON in reply for brand %s role %s (attempt %d, %d chars)",
                           brand_id, role, attempt + 1, len(raw or ""))
            if attempt == 0:
                continue
            break
        obj = parsed
        problems = _tone_problems(obj)
        if not problems:
            break
        if rewrites:
            # One rewrite is all the budget: the words are logged for us, the
            # reader gets the digest without a note about our own checks.
            logger.info("voices digest for brand %s role %s kept verdict words after a rewrite: %s",
                        brand_id, role, ", ".join(problems))
            break
        rewrites += 1
    themes = []
    for t in (obj.get("themes") or [])[:5]:
        if not isinstance(t, dict):
            continue
        quotes = [str(q).strip()[:220] for q in (t.get("quotes") or []) if str(q).strip()][:3]
        themes.append({"theme": str(t.get("theme") or "").strip()[:120],
                       "sentiment": str(t.get("sentiment") or "neutral").lower(),
                       "post_count": int(t.get("post_count") or 0) if str(t.get("post_count") or "0").isdigit() else 0,
                       "quotes": quotes})
    asks = [str(a).strip()[:300] for a in (obj.get("asks") or []) if str(a).strip()][:6]
    result = {"context": (str(obj.get("context") or "").strip() or None),
              "facts": ctx,
              "summary": (str(obj.get("summary") or "").strip() or None),
              "themes": themes, "asks": asks, "model": model_name,
              "generated_at": datetime.now().isoformat(timespec="seconds")}
    if result["summary"] or themes:
        _digest_cache[cache_key] = (time.monotonic(), result)
        if len(_digest_cache) > 200:
            oldest = min(_digest_cache, key=lambda k: _digest_cache[k][0])
            _digest_cache.pop(oldest, None)
    else:
        result["note"] = _DIGEST_UNAVAILABLE
    return {**base, **result}
