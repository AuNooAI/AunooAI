"""Brand Watcher Five Signals — remote article screening via saas.aunoo.ai.

Composes two saas.aunoo.ai engines, called over its MCP JSON-RPC endpoint
(POST {AUNOO_SAAS_MCP_URL}, Bearer workspace Skills key), into a per-article
five-signal screen stored in ``bw_article_signals``:

  1. veracity                 claim-validation verdict + per-claim checks
  2. source_credibility       MBFC reputation of the outlet (+ satire)
  3. corroboration            cross-outlet corroborators + open-web evidence
  4. propagation              Bluesky spread / follower-weighted exposure
  5. amplification_integrity  concentration, fresh-account surge, cohorts

Both engines run as saas background jobs (start_*_job → poll get_*_job); the
inline tool variants have a 25s cap that cold runs exceed. Either job may fail
independently — the composer marks the affected signals 'nodata' rather than
failing the whole screen.

Score semantics: all signals are 0-100 where higher = healthier, EXCEPT
propagation, which measures spread magnitude (higher = wider). The composite
score therefore folds propagation in inverted (100 - spread), so composite is
uniformly "screen health".

Caveats baked in:
  - saas corpus corroboration is topic-scoped; Brand Watcher articles are
    usually outside the saas corpus, so open-web evidence (Tavily) is read
    alongside the corroborator count instead of treating an empty corpus as
    "uncorroborated".
  - reach depends on Bluesky search on the saas deployment; when the payload
    says search_available=false the social signals are 'nodata', not zero.

Requires env: AUNOO_SAAS_MCP_KEY (saas workspace key, 'aunoo_…');
AUNOO_SAAS_MCP_URL defaults to https://saas.aunoo.ai/mcp. Absent key →
``signals_available()`` is False, the UI hides the feature, and the run
endpoint refuses politely. Fresh validations cost LLM + web-search calls on
the saas side and count against its monthly quota; completed rows are never
recomputed unless force=True.
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import text

logger = logging.getLogger(__name__)

MCP_URL_DEFAULT = "https://saas.aunoo.ai/mcp"
HTTP_TIMEOUT = 60.0
VALIDATION_POLL_SECONDS = 25       # cadence advertised by start_validation_job
REACH_POLL_SECONDS = 20            # cadence advertised by start_social_reach_job
JOB_CEILING_SECONDS = 600          # per-job wall-clock ceiling
REACH_WINDOW_DAYS = 90
LIST_CAP = 15                      # stored evidence lists are trimmed to this
STR_CAP = 2000                     # and long strings to this many chars

SIGNAL_KEYS = [
    "veracity",
    "source_credibility",
    "corroboration",
    "propagation",
    "amplification_integrity",
]

SIGNAL_LABELS = {
    "veracity": "Claim veracity",
    "source_credibility": "Source credibility",
    "corroboration": "Corroboration & independence",
    "propagation": "Propagation & reach",
    "amplification_integrity": "Amplification integrity",
}


def signals_available() -> bool:
    """True when the saas MCP key is configured (UI gate)."""
    return bool(os.getenv("AUNOO_SAAS_MCP_KEY"))


# ─── MCP JSON-RPC client ─────────────────────────────────────────────────────

class SaasMcpError(RuntimeError):
    pass


async def _mcp_call(client: httpx.AsyncClient, tool: str,
                    arguments: Dict[str, Any]) -> Dict[str, Any]:
    """One tools/call against the saas MCP endpoint; returns the tool payload.

    The dispatcher wraps every payload as {"truncated": bool, "data": ...}
    inside MCP text content — unwrap both layers here.
    """
    api_key = os.getenv("AUNOO_SAAS_MCP_KEY")
    if not api_key:
        raise SaasMcpError("AUNOO_SAAS_MCP_KEY not configured")
    url = os.getenv("AUNOO_SAAS_MCP_URL", MCP_URL_DEFAULT)
    body = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000) % 1_000_000,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }
    resp = await client.post(
        url, json=body,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    if resp.status_code != 200:
        raise SaasMcpError(f"{tool}: HTTP {resp.status_code} from saas MCP")
    rpc = resp.json()
    if rpc.get("error"):
        err = rpc["error"]
        raise SaasMcpError(f"{tool}: {err.get('code')} {err.get('message')}")
    try:
        content = rpc["result"]["content"][0]["text"]
        wrapper = json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        raise SaasMcpError(f"{tool}: unparseable MCP result ({e})")
    if isinstance(wrapper, dict) and "data" in wrapper:
        if wrapper.get("truncated"):
            logger.warning("Five Signals: %s payload truncated by saas cap", tool)
        payload = wrapper["data"]
    else:
        payload = wrapper
    if isinstance(payload, dict) and payload.get("error"):
        raise SaasMcpError(f"{tool}: {payload.get('error')}: {payload.get('message')}")
    return payload


async def _start_and_poll(client: httpx.AsyncClient, start_tool: str,
                          start_args: Dict[str, Any], poll_tool: str,
                          poll_seconds: int) -> Dict[str, Any]:
    """start_*_job → poll get_*_job until succeeded/failed/ceiling.

    saas dedupes validations by content hash server-side: an article that was
    already validated completes its job near-instantly from cache. The first
    polls are therefore fast (3s/5s/8s) so cached results return in seconds
    instead of waiting a full poll interval; fresh runs fall back to the
    normal cadence."""
    started = await _mcp_call(client, start_tool, start_args)
    job_id = started.get("job_id")
    if job_id is None:
        raise SaasMcpError(f"{start_tool}: no job_id in response")
    deadline = time.monotonic() + JOB_CEILING_SECONDS
    fast_polls = [3, 5, 8]
    while time.monotonic() < deadline:
        await asyncio.sleep(fast_polls.pop(0) if fast_polls else poll_seconds)
        job = await _mcp_call(client, poll_tool, {"job_id": job_id})
        status = job.get("status")
        if status == "succeeded":
            return job.get("result") or {}
        if status == "failed":
            raise SaasMcpError(f"{poll_tool}: job {job_id} failed: {job.get('error')}")
    raise SaasMcpError(f"{poll_tool}: job {job_id} exceeded {JOB_CEILING_SECONDS}s ceiling")


# ─── Payload trimming (storage hygiene) ──────────────────────────────────────

def _trim(obj: Any, depth: int = 0) -> Any:
    """Cap list lengths and string sizes recursively before JSONB storage."""
    if depth > 6:
        return None
    if isinstance(obj, str):
        return obj[:STR_CAP]
    if isinstance(obj, list):
        return [_trim(v, depth + 1) for v in obj[:LIST_CAP]]
    if isinstance(obj, dict):
        return {k: _trim(v, depth + 1) for k, v in obj.items()}
    return obj


# ─── Cross-network propagation (xnet) ────────────────────────────────────────
#
# The saas reach engine covers Bluesky. xnet adds the other networks two ways:
#   corpus — free match over the tenant's own xpoz-collected posts (keyword
#            monitoring already stored them; a URL/headline hit is a genuine
#            share, but coverage is only what monitoring happened to catch)
#   live   — optional paid xpoz query (Twitter/X, Reddit, TikTok, Instagram)
#            by article URL and headline; capped per platform. xpoz serves a
#            rolling ~60-day window.

XNET_LIVE_LIMIT = 10          # posts per platform per query term (cost control)
XNET_SAMPLE_CAP = 10          # stored sample posts per platform
_HEADLINE_MIN = 25            # don't headline-match on short/generic titles


def _url_needle(url: str) -> str:
    """Scheme/www/query-stripped form of the URL for substring matching."""
    u = (url or "").strip()
    u = re.sub(r"^https?://", "", u, flags=re.I)
    u = re.sub(r"^www\.", "", u, flags=re.I)
    return u.split("?")[0].rstrip("/")


def _headline_needle(title: str) -> Optional[str]:
    """A distinctive headline snippet for share-matching, or None.

    Cut at a word boundary — a mid-word tail turns exact-phrase matching into
    prefix soup on keyword-search backends.
    """
    t = re.sub(r"\s+", " ", (title or "")).strip()
    if len(t) < _HEADLINE_MIN:
        return None
    if len(t) <= 60:
        return t
    return t[:60].rsplit(" ", 1)[0]


def _post_matches(text_: str, url_needle: str, headline: Optional[str]) -> bool:
    """True when a post genuinely shares the article (URL or headline quote).

    xpoz search is keyword-based and returns loosely-related posts; without
    this gate a story with one real share 'propagates' to 80 posts of noise
    (same lesson as the official-sources term gate).
    """
    tl = (text_ or "").lower()
    if url_needle and url_needle.lower() in tl:
        return True
    if headline and headline.lower() in tl:
        return True
    return False


def _post_engagement(meta: Dict[str, Any]) -> int:
    try:
        return int(
            float(meta.get("likes") or 0)
            + 2 * float(meta.get("reposts") or 0)
            + float(meta.get("comments") or 0)
            + float(meta.get("plays") or 0) / 100
        )
    except (TypeError, ValueError):
        return 0


def _corpus_pickup(article_uri: str, article_url: str,
                   article_title: str, days: int) -> List[Dict[str, Any]]:
    """Stored xpoz posts that share the article's URL or quote its headline.

    Opens its own short-lived connection — the gather runs for minutes and a
    connection held across it gets reaped by pgbouncer.
    """
    needle = _url_needle(article_url)
    headline = _headline_needle(article_title)
    clauses, params = [], {"self": article_uri, "days": f"{days} days"}
    if needle:
        params["u"] = f"%{needle}%"
        clauses.append("(a.summary ILIKE :u OR a.title ILIKE :u)")
    if headline:
        params["h"] = f"%{headline}%"
        clauses.append("(a.summary ILIKE :h OR a.title ILIKE :h)")
    if not clauses:
        return []
    from app.database import get_database_instance
    conn = get_database_instance()._temp_get_connection()
    try:
        rows = conn.execute(text(f"""
            SELECT a.uri, a.title, a.summary, a.news_source, a.publication_date, a.social_meta
            FROM articles a
            WHERE a.news_source LIKE 'xpoz:%'
              AND a.uri <> :self
              AND a.publication_date >= (now() - (:days)::interval)::text
              AND ({" OR ".join(clauses)})
            LIMIT 200
        """), params).fetchall()
    finally:
        conn.close()
    out = []
    for uri, title, summary, news_source, pub, meta in rows:
        m = meta if isinstance(meta, dict) else (json.loads(meta) if meta else {})
        out.append({
            "platform": (m.get("platform") or news_source.split(":", 1)[-1] or "unknown").lower(),
            "author": m.get("author"),
            "url": uri,
            "text": (summary or title or "")[:300],
            "date": (pub or "")[:19],
            "engagement": _post_engagement(m),
            "origin": "corpus",
        })
    return out


async def _xpoz_live(article_url: str, article_title: str,
                     days: int) -> Optional[List[Dict[str, Any]]]:
    """Live xpoz query by URL + headline; None when xpoz isn't provisioned."""
    if not os.getenv("XPOZ_API_KEY"):
        return None
    try:
        from app.collectors.xpoz_collector import XpozCollector
        collector = XpozCollector()
    except Exception as e:
        logger.info("xnet live query unavailable (%s)", e)
        return None
    start = datetime.now(timezone.utc) - timedelta(days=min(days, 60))
    terms = [_url_needle(article_url)]
    headline = _headline_needle(article_title)
    if headline:
        terms.append(headline)
    url_needle = _url_needle(article_url)
    headline = _headline_needle(article_title)
    seen, out, fetched = set(), [], 0
    for term in terms:
        try:
            posts = await collector.search_articles(
                term, topic="__propagation__", max_results=XNET_LIVE_LIMIT,
                start_date=start,
            )
        except Exception as e:
            logger.warning("xnet live query failed for %r: %s", term[:50], e)
            continue
        fetched += len(posts)
        for p in posts:
            url = p.get("url")
            if not url or url in seen:
                continue
            body = f"{p.get('title') or ''} {p.get('summary') or ''}"
            # Share gate: xpoz keyword search returns loosely-related posts;
            # only keep ones that actually carry the URL or quote the headline.
            if not _post_matches(body, url_needle, headline):
                continue
            seen.add(url)
            m = p.get("social_meta") or {}
            out.append({
                "platform": (m.get("platform") or "unknown").lower(),
                "author": m.get("author"),
                "url": url,
                "text": (p.get("summary") or p.get("title") or "")[:300],
                "date": (p.get("published_date") or "")[:19],
                "engagement": _post_engagement(m),
                "origin": "live",
            })
    if fetched:
        logger.info("xnet live: kept %d of %d fetched posts after share gate", len(out), fetched)
    return out


async def _gather_xnet(article_uri: str, article_url: str,
                       article_title: str, days: int) -> Dict[str, Any]:
    """Corpus + live cross-network pickup, grouped per platform."""
    corpus = _corpus_pickup(article_uri, article_url, article_title, days)
    live = await _xpoz_live(article_url, article_title, days)
    posts = list(corpus)
    if live:
        have = {p["url"] for p in posts}
        posts += [p for p in live if p["url"] not in have]
    platforms: Dict[str, Dict[str, Any]] = {}
    for p in sorted(posts, key=lambda x: -(x["engagement"] or 0)):
        plat = platforms.setdefault(p["platform"], {
            "posts": 0, "engagement": 0, "first_seen": None, "last_seen": None,
            "sample": [],
        })
        plat["posts"] += 1
        plat["engagement"] += p["engagement"] or 0
        d = p.get("date") or None
        if d:
            plat["first_seen"] = min(plat["first_seen"], d) if plat["first_seen"] else d
            plat["last_seen"] = max(plat["last_seen"], d) if plat["last_seen"] else d
        if len(plat["sample"]) < XNET_SAMPLE_CAP:
            plat["sample"].append(p)
    return {
        "gathered_at": datetime.now(timezone.utc).isoformat(),
        "window_days": days,
        "corpus_matches": len(corpus),
        "live_matches": len(live) if live is not None else None,
        "live_available": live is not None,
        "platforms": platforms,
    }


# ─── Signal composition ──────────────────────────────────────────────────────

def _band(score: Optional[float], warn: float = 40, good: float = 65) -> str:
    if score is None:
        return "nodata"
    if score >= good:
        return "good"
    if score >= warn:
        return "warn"
    return "bad"

_VERACITY_BASE = {
    "corroborated": 85, "partial": 60, "single_source": 50,
    "unverifiable_input": 40, "non_independent": 35,
    "likely_coordinated": 30, "contested": 25, "satire": 5,
}


def _claim_status_counts(validation: Dict[str, Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for cv in validation.get("claim_verifications") or []:
        st = (cv.get("status") or "uncertain").strip().lower()
        counts[st] = counts.get(st, 0) + 1
    return counts


def _sig_veracity(validation: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    key, label = "veracity", SIGNAL_LABELS["veracity"]
    if not validation:
        return {"key": key, "label": label, "score": None, "band": "nodata",
                "summary": "Claim validation unavailable for this run.", "evidence": {}}
    verdict = (validation.get("verdict") or "").strip().lower()
    conf = validation.get("confidence")
    base = _VERACITY_BASE.get(verdict)
    if base is None:
        score = None
    else:
        # Confidence scales the deviation from neutral 50 — a low-confidence
        # 'corroborated' and a low-confidence 'contested' both sit near 50.
        c = conf if isinstance(conf, (int, float)) else 0.5
        score = round(50 + (base - 50) * max(0.0, min(1.0, c)))
    counts = _claim_status_counts(validation)
    claim_bits = ", ".join(f"{n} {st}" for st, n in sorted(counts.items(), key=lambda kv: -kv[1]))
    conf_txt = f" (confidence {conf:.2f})" if isinstance(conf, (int, float)) else ""
    summary = f"Verdict: {verdict or 'unknown'}{conf_txt}."
    if claim_bits:
        summary += f" Claims: {claim_bits}."
    return {"key": key, "label": label, "score": score, "band": _band(score),
            "summary": summary,
            "evidence": {"verdict": verdict, "confidence": conf,
                         "claims": validation.get("extracted_claims") or [],
                         "claim_verifications": validation.get("claim_verifications") or []}}


def _sig_source(validation: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    key, label = "source_credibility", SIGNAL_LABELS["source_credibility"]
    rep = (validation or {}).get("source_reputation") or {}
    verdict = ((validation or {}).get("verdict") or "").strip().lower()
    domain = rep.get("domain") or "unknown source"
    if verdict == "satire":
        return {"key": key, "label": label, "score": 5, "band": "bad",
                "summary": f"{domain} is a satire outlet — content is not factual reporting.",
                "evidence": rep}
    rscore = rep.get("reputation_score")
    tier = (rep.get("reputation_tier") or "unknown").lower()
    if rscore is None and tier == "unknown":
        return {"key": key, "label": label, "score": None, "band": "nodata",
                "summary": f"No media-bias/factuality record for {domain}.",
                "evidence": rep}
    score = round(float(rscore) * 100) if isinstance(rscore, (int, float)) else \
        {"high": 80, "medium": 55, "low": 25}.get(tier)
    parts = []
    if rep.get("mbfc_factual_reporting"):
        parts.append(f"factual reporting {rep['mbfc_factual_reporting']}")
    if rep.get("mbfc_credibility"):
        parts.append(f"credibility {rep['mbfc_credibility']}")
    if rep.get("mbfc_bias"):
        parts.append(f"bias {rep['mbfc_bias']}")
    detail = "; ".join(parts) if parts else f"reputation tier {tier}"
    return {"key": key, "label": label, "score": score, "band": _band(score),
            "summary": f"{domain}: {detail}.", "evidence": rep}


def _sig_corroboration(validation: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    key, label = "corroboration", SIGNAL_LABELS["corroboration"]
    if not validation:
        return {"key": key, "label": label, "score": None, "band": "nodata",
                "summary": "Claim validation unavailable for this run.", "evidence": {}}
    corr = validation.get("corroboration") or {}
    corroborators = corr.get("corroborators") or []
    n_corr = len(corroborators)
    web = validation.get("web_evidence") or {}
    web_verdicts = web.get("verdicts") or []
    web_supported = sum(1 for v in web_verdicts
                        if (v.get("verdict") or "").lower() == "supported")
    fc = validation.get("external_fact_check") or {}
    fc_matches = fc.get("matched_reviews") or []
    verdict = (validation.get("verdict") or "").strip().lower()

    if n_corr >= 3:
        score = min(95, 80 + 3 * n_corr)
    elif n_corr >= 1:
        score = 60
    else:
        score = 35
    if verdict == "non_independent":
        # The corroborators exist but look like the same ownership/wire copy.
        score = min(score, 40)
    if n_corr == 0 and web_supported > 0:
        score = max(score, 55)

    bits = [f"{n_corr} corpus corroborator{'s' if n_corr != 1 else ''}"]
    if web_verdicts:
        bits.append(f"open-web evidence supports {web_supported} of {len(web_verdicts)} claims")
    elif n_corr == 0:
        bits.append("no open-web evidence graded")
    if fc_matches:
        bits.append(f"{len(fc_matches)} external fact-check match{'es' if len(fc_matches) != 1 else ''}")
    if verdict == "non_independent":
        bits.append("corroborators are not independent (shared ownership or wire copy)")
    elif n_corr == 0 and web_supported > 0:
        bits.append("story is outside the saas corpus — web evidence is the meaningful check here")
    return {"key": key, "label": label, "score": score, "band": _band(score),
            "summary": (". ".join([bits[0].capitalize()] + bits[1:]) + "."),
            "evidence": {"corroborators": corroborators,
                         "web_verdicts": web_verdicts,
                         "fact_check_matches": fc_matches}}


def _sig_propagation(reach: Optional[Dict[str, Any]],
                     xnet: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    key, label = "propagation", SIGNAL_LABELS["propagation"]
    xplats = (xnet or {}).get("platforms") or {}
    xposts = sum(int(p.get("posts") or 0) for p in xplats.values())
    xeng = sum(int(p.get("engagement") or 0) for p in xplats.values())
    xnet_txt = ""
    if xplats:
        xnet_txt = " Other networks: " + ", ".join(
            f"{plat} {p['posts']}" for plat, p in
            sorted(xplats.items(), key=lambda kv: -kv[1]["posts"])) + "."
    has_bsky = bool(reach and reach.get("search_available", False))
    if not has_bsky and not xplats:
        if xnet is not None:
            return {"key": key, "label": label, "score": 0, "band": "good",
                    "summary": "No pickup found: Bluesky lookup unavailable and no cross-network shares in the monitoring corpus"
                               + ("/live query." if xnet.get("live_available") else " (live query not provisioned)."),
                    "evidence": {"networks": xplats}}
        return {"key": key, "label": label, "score": None, "band": "nodata",
                "summary": "Social propagation lookup unavailable (Bluesky search not configured or job failed).",
                "evidence": {}}
    totals = (reach or {}).get("totals") or {}
    posts = int(totals.get("posts") or 0)
    accounts = int(totals.get("unique_accounts") or 0)
    engagement = sum(int(totals.get(k) or 0) for k in ("likes", "reposts", "replies", "quotes"))
    exposure = (reach or {}).get("total_followers") or (reach or {}).get("exposure") or 0
    if posts == 0 and xposts == 0:
        return {"key": key, "label": label, "score": 0, "band": "good",
                "summary": "No social pickup found in the window (Bluesky + other networks).",
                "evidence": {"totals": totals, "networks": xplats,
                             "window_days": (reach or {}).get("window_days")}}
    import math
    # Spread magnitude 0-100: log-scaled Bluesky posts/accounts/exposure plus
    # cross-network posts + engagement.
    score = min(100, round(
        28 * math.log10(1 + posts)
        + 22 * math.log10(1 + accounts)
        + 10 * math.log10(1 + (float(exposure) if exposure else 0) / 1000.0)
        + 14 * math.log10(1 + xposts)
        + 6 * math.log10(1 + xeng / 10.0)
    ))
    span = ""
    if (reach or {}).get("first_seen"):
        span = f" First seen on Bluesky {str(reach['first_seen'])[:10]}."
    bsky_txt = (f"Bluesky: {posts} post{'s' if posts != 1 else ''} by {accounts} account"
                f"{'s' if accounts != 1 else ''}, {engagement} engagements"
                + (f", est. follower reach {int(exposure):,}" if exposure else "")
                + "." if has_bsky else "Bluesky lookup unavailable.")
    band = "good" if score < 20 else ("warn" if score < 60 else "bad")
    return {"key": key, "label": label, "score": score, "band": band,
            "summary": (bsky_txt + xnet_txt + span),
            "evidence": {"totals": totals, "timeline": (reach or {}).get("timeline") or [],
                         "exposure": exposure, "first_seen": (reach or {}).get("first_seen"),
                         "last_seen": (reach or {}).get("last_seen"),
                         "window_days": (reach or {}).get("window_days"),
                         "networks": {k: {kk: vv for kk, vv in v.items() if kk != "sample"}
                                      for k, v in xplats.items()}}}


def _sig_amplification(reach: Optional[Dict[str, Any]],
                       validation: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    key, label = "amplification_integrity", SIGNAL_LABELS["amplification_integrity"]
    coord = (validation or {}).get("coordination_context") or {}
    has_reach = bool(reach and reach.get("search_available", False)
                     and (reach.get("totals") or {}).get("posts"))
    if not has_reach and not coord.get("has_coordination_signal"):
        if reach and reach.get("search_available") and not (reach.get("totals") or {}).get("posts"):
            return {"key": key, "label": label, "score": None, "band": "nodata",
                    "summary": "No social pickup to assess for coordinated amplification.",
                    "evidence": {}}
        return {"key": key, "label": label, "score": None, "band": "nodata",
                "summary": "No propagation data available to assess amplification.",
                "evidence": {}}
    score = 100
    deductions: List[str] = []
    conc = (reach or {}).get("concentration") or {}
    if conc.get("label") == "concentrated":
        score -= 25
        gini = conc.get("account_gini")
        deductions.append("engagement concentrated in a few accounts"
                          + (f" (gini {gini:.2f})" if isinstance(gini, (int, float)) else ""))
    fresh = (reach or {}).get("fresh_accounts") or {}
    if fresh.get("surge"):
        score -= 30
        deductions.append(f"fresh-account surge ({fresh.get('fresh_count')} accounts "
                          f"younger than {fresh.get('cutoff_days')} days)")
    cohorts = ((reach or {}).get("cohorts") or {}).get("cohorts") or []
    if cohorts:
        score -= 30
        deductions.append(f"{len(cohorts)} coordination cohort{'s' if len(cohorts) != 1 else ''} detected")
    if coord.get("has_coordination_signal"):
        score -= 20
        deductions.append("validation flagged a coordination signal in coverage")
    score = max(0, score)
    summary = ("No amplification anomalies: pickup looks organic."
               if not deductions else
               "Anomalies: " + "; ".join(deductions) + ".")
    return {"key": key, "label": label, "score": score, "band": _band(score),
            "summary": summary,
            "evidence": {"concentration": conc, "fresh_accounts": fresh,
                         "cohorts": cohorts,
                         "top_amplifiers": ((reach or {}).get("posts") or [])[:10],
                         "coordination_context": coord,
                         "reception": (reach or {}).get("reception") or {}}}


def _compose_signals(validation: Optional[Dict[str, Any]],
                     reach: Optional[Dict[str, Any]],
                     xnet: Optional[Dict[str, Any]] = None
                     ) -> Tuple[Dict[str, Any], Optional[str], Optional[float]]:
    """Build the five signal entries + headline verdict + composite score."""
    signals = {
        "veracity": _sig_veracity(validation),
        "source_credibility": _sig_source(validation),
        "corroboration": _sig_corroboration(validation),
        "propagation": _sig_propagation(reach, xnet),
        "amplification_integrity": _sig_amplification(reach, validation),
    }
    verdict = (validation or {}).get("verdict")
    # Composite = screen health; propagation is a magnitude, so it enters
    # inverted (wide spread of the story drags health down).
    vals: List[float] = []
    for k, s in signals.items():
        if s["score"] is None:
            continue
        vals.append(100 - s["score"] if k == "propagation" else s["score"])
    composite = round(sum(vals) / len(vals), 1) if vals else None
    return signals, verdict, composite


# ─── Persistence + orchestration ─────────────────────────────────────────────

def _upsert_row(article_uri: str, brand_id: int, *, status: str,
                signals: Optional[Dict] = None, verdict: Optional[str] = None,
                composite: Optional[float] = None, validation: Optional[Dict] = None,
                reach: Optional[Dict] = None, xnet: Optional[Dict] = None,
                error: Optional[str] = None,
                requested_by: Optional[str] = None) -> None:
    """Upsert on a fresh connection — the run holds no connection across the
    minutes-long saas polls/xnet gather (pgbouncer reaps idle ones)."""
    from app.database import get_database_instance
    conn = get_database_instance()._temp_get_connection()
    try:
        _upsert_row_on(conn, article_uri, brand_id, status=status, signals=signals,
                       verdict=verdict, composite=composite, validation=validation,
                       reach=reach, xnet=xnet, error=error, requested_by=requested_by)
    finally:
        conn.close()


def _upsert_row_on(conn, article_uri: str, brand_id: int, *, status: str,
                   signals: Optional[Dict] = None, verdict: Optional[str] = None,
                   composite: Optional[float] = None, validation: Optional[Dict] = None,
                   reach: Optional[Dict] = None, xnet: Optional[Dict] = None,
                   error: Optional[str] = None,
                   requested_by: Optional[str] = None) -> None:
    conn.execute(text("""
        INSERT INTO bw_article_signals
            (article_uri, brand_id, status, signals, verdict, composite_score,
             validation, reach, xnet, error, requested_by, updated_at)
        VALUES (:uri, :bid, :status, :signals, :verdict, :composite,
                :validation, :reach, :xnet, :error, :rby, NOW())
        ON CONFLICT (article_uri, brand_id) DO UPDATE SET
            status = EXCLUDED.status,
            signals = COALESCE(EXCLUDED.signals, bw_article_signals.signals),
            verdict = COALESCE(EXCLUDED.verdict, bw_article_signals.verdict),
            composite_score = COALESCE(EXCLUDED.composite_score, bw_article_signals.composite_score),
            validation = COALESCE(EXCLUDED.validation, bw_article_signals.validation),
            reach = COALESCE(EXCLUDED.reach, bw_article_signals.reach),
            xnet = COALESCE(EXCLUDED.xnet, bw_article_signals.xnet),
            error = EXCLUDED.error,
            requested_by = COALESCE(EXCLUDED.requested_by, bw_article_signals.requested_by),
            updated_at = NOW()
    """), {
        "uri": article_uri, "bid": brand_id, "status": status,
        "signals": json.dumps(signals) if signals is not None else None,
        "verdict": verdict, "composite": composite,
        "validation": json.dumps(_trim(validation)) if validation is not None else None,
        "reach": json.dumps(_trim(reach)) if reach is not None else None,
        "xnet": json.dumps(_trim(xnet)) if xnet is not None else None,
        "error": error, "rby": requested_by,
    })
    conn.commit()


async def run_five_signals(article_uri: str, brand_id: int, article_url: str,
                           days: int = REACH_WINDOW_DAYS, force: bool = False,
                           requested_by: str = "user", mode: str = "full") -> None:
    """Screen one article: start the saas job(s), poll, compose, store.

    mode selects the engine(s): 'full' runs both, 'validation' only claim
    validation, 'reach' only the Bluesky story-reach lookup. Partial runs
    merge with whatever the row already holds — run reach today, claims
    tomorrow, and the five signals recompose over both payloads.

    Designed as a BackgroundTasks / monitor-loop target — never raises; the
    outcome (completed or failed) lands on the bw_article_signals row.

    Connection discipline: the run spans minutes of saas polling — no DB
    connection is held across it. Reads/writes each use a fresh short-lived
    connection (pgbouncer reaps ones left idle that long).
    """
    from app.database import get_database_instance
    db = get_database_instance()
    try:
        run_validation = mode in ("full", "validation")
        run_reach = mode in ("full", "reach")
        # Prior payloads: a partial run recomposes signals over the union.
        conn = db._temp_get_connection()
        try:
            prior = conn.execute(text(
                "SELECT validation, reach, xnet FROM bw_article_signals"
                " WHERE article_uri = :u AND brand_id = :b"
            ), {"u": article_uri, "b": brand_id}).fetchone()
            title_row = conn.execute(text(
                "SELECT title FROM articles WHERE uri = :u"), {"u": article_uri}).fetchone()
        finally:
            conn.close()
        def _pj(v):
            return v if isinstance(v, dict) or v is None else json.loads(v)
        prior_validation = _pj(prior[0]) if prior else None
        prior_reach = _pj(prior[1]) if prior else None
        prior_xnet = _pj(prior[2]) if prior else None
        article_title = (title_row[0] if title_row else "") or ""

        _upsert_row(article_uri, brand_id, status="running",
                    requested_by=requested_by)
        new_validation: Optional[Dict[str, Any]] = None
        new_reach: Optional[Dict[str, Any]] = None
        errors: List[str] = []
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            jobs = []
            if run_validation:
                jobs.append(_start_and_poll(client, "start_validation_job",
                                            {"url": article_url, "force": force},
                                            "get_validation_job", VALIDATION_POLL_SECONDS))
            if run_reach:
                jobs.append(_start_and_poll(client, "start_social_reach_job",
                                            {"url": article_url, "deep": True, "days": days},
                                            "get_social_reach_job", REACH_POLL_SECONDS))
            results = await asyncio.gather(*jobs, return_exceptions=True)
        idx = 0
        if run_validation:
            if isinstance(results[idx], Exception):
                errors.append(f"validation: {results[idx]}")
                logger.warning("Five Signals validation failed for %s: %s", article_url, results[idx])
            else:
                new_validation = results[idx]
            idx += 1
        if run_reach:
            if isinstance(results[idx], Exception):
                errors.append(f"reach: {results[idx]}")
                logger.warning("Five Signals reach failed for %s: %s", article_url, results[idx])
            else:
                new_reach = results[idx]

        # Cross-network pickup runs with the reach engine (corpus match is free;
        # the live xpoz query degrades to None when unprovisioned).
        new_xnet: Optional[Dict[str, Any]] = None
        if run_reach:
            try:
                new_xnet = await _gather_xnet(article_uri, article_url,
                                              article_title, days)
            except Exception as e:
                errors.append(f"xnet: {e}")
                logger.warning("Five Signals xnet gather failed for %s: %s", article_url, e)

        validation = new_validation or prior_validation
        reach = new_reach or prior_reach
        xnet = new_xnet or prior_xnet
        if validation is None and reach is None and xnet is None:
            _upsert_row(article_uri, brand_id, status="failed",
                        error=" | ".join(errors)[:1000], requested_by=requested_by)
            return

        signals, verdict, composite = _compose_signals(validation, reach, xnet)
        # Only fresh payloads are written; COALESCE in the upsert keeps the
        # other engine's stored payload intact on partial runs.
        _upsert_row(article_uri, brand_id, status="completed",
                    signals=signals, verdict=verdict, composite=composite,
                    validation=new_validation, reach=new_reach, xnet=new_xnet,
                    error=(" | ".join(errors)[:1000] or None),
                    requested_by=requested_by)
        logger.info("Five Signals completed for %s (brand %s, mode %s): verdict=%s composite=%s",
                    article_url, brand_id, mode, verdict, composite)
    except Exception as e:
        logger.error("Five Signals run crashed for %s: %s", article_url, e, exc_info=True)
        try:
            _upsert_row(article_uri, brand_id, status="failed",
                        error=str(e)[:1000], requested_by=requested_by)
        except Exception:
            pass
