"""Incident tracking over a whole window, read one topic-day at a time.

The Highlights page used to send the model the newest 100 articles of the
window. On wileytest a 30-day window over 16 topics holds about 15,400
articles, so a "30 day" analysis read the last four hours (13 Oct 2026).

Now every article in the window is read, and read once:

1. The window is split into slices of (topic, publication day). A slice's
   fingerprint is its article count plus an md5 of its sorted URIs.
2. A slice whose stored fingerprint matches is reused. Changed or new slices
   are packed, per topic, into batches of up to 100 articles. The daily
   reading asks for a short record per development (headline, type,
   significance, date, one line, cited article numbers), about 70 output
   tokens each. The full write-up with leads and credibility is ~310 tokens a
   item, and doing it for every article cost about $1 per 1,000 articles
   (bugfixing test, 13 Oct 2026). Each record is filed under the day of its
   earliest cited article, and every slice in the batch is saved, including
   slices that produced nothing.
3. One merge call sees every record in the window as a one-line summary,
   groups the ones that report the same development, and ranks the groups.
4. Only the top groups get the full write-up (vector_routes
   _write_up_incidents), with the page's custom prompt settings.

Slices are stored in article_analysis_cache (analysis_type 'incident_day').
The key covers what shapes the daily reading (DAY_MODEL, organisation profile,
SLICE_VERSION), so a changed setting rereads; the page's model does not.
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import time
import uuid
from datetime import date, datetime, timedelta
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Bump when the extraction prompt or the slice rules change: every slice rereads.
SLICE_VERSION = "3"
# The daily reading and the merge are bulk work over every article, so they run
# on the cheap bulk model whatever the page's model is; the page's model writes
# up the final incidents. wileytest's page runs claude-sonnet-4-5, which for the
# reading would cost about five times as much (13 Oct 2026).
DAY_MODEL = os.getenv("INCIDENT_DAY_MODEL", "bedrock-kimi-k2-5")
BATCH_SIZE = 100
DAY_MAX_TOKENS = 12000
CONCURRENCY = 8
MERGE_LIMIT_DEFAULT = 40
# Places every topic with findings is guaranteed on top of the open ranking.
PER_TOPIC_DEFAULT = 3

_SIG_RANK = {"high": 3, "medium": 2, "low": 1}

_ARTICLE_COLS = ("uri, title, summary, news_source, publication_date, category, sentiment, topic, "
                 "bias, factual_reporting, mbfc_credibility_rating, bias_source")


def config_hash(req) -> str:
    parts = [SLICE_VERSION, DAY_MODEL, str(req.profile_id or "")]
    return hashlib.sha1("\x1f".join(parts).encode()).hexdigest()[:12]


def profile_line(db, profile_id: Optional[int]) -> str:
    """One line on whose priorities set significance, or '' without a profile."""
    if not profile_id:
        return ""
    try:
        from app.database_query_facade import DatabaseQueryFacade
        row = DatabaseQueryFacade(db, logger).get_organisational_profile(profile_id)
        if not row:
            return ""

        def _list(v):
            try:
                return [str(x) for x in (json.loads(v) if isinstance(v, str) else (v or []))]
            except (TypeError, ValueError):
                return []
        focus = _list(row.get("key_concerns")) + _list(row.get("strategic_priorities"))
        return (f"The reader is {row.get('name')} ({row.get('industry') or 'organisation'}). "
                f"Rate significance for them; their concerns: {', '.join(focus[:8]) or 'not stated'}.")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"incident day reading: profile {profile_id} unavailable: {e}")
        return ""


_DAY_SYSTEM = """You read a batch of news articles about {topic} and list the developments worth tracking for a strategic intelligence analyst.
{profile}
Types: incident (needs response: layoffs, breaches, regulatory action, lawsuits, failures), event (launches, funding, partnerships, pilots, milestones), entity (an organisation, person or product newly worth tracking), expertise (expert analysis or warnings), informed_insider (leaks, internal memos), trend_signal (adoption or market shifts), strategic_shift (policy pivots, strategic realignment).

For each distinct development output one JSON object with short keys:
{{"n": "factual headline", "t": "type", "st": "subtype, e.g. regulatory_action, mna, product_launch, funding_round, expert_warning, adoption_trend", "s": "high|medium|low", "a": [numbers of the articles that report it], "d": "YYYY-MM-DD when the articles state the event date, else null", "x": "one factual sentence: who did what"}}

Rules:
- Several articles about the same development go in one object.
- Be inclusive: anything newsworthy gets an object. Skip only items with no news in them (how-to guides, listicles, ads, event listings).
- "d" is the date the event happened as an article states it. Never use a publication date there; never guess a year.
- Lower significance for low-credibility or fringe sources and for self-reported extraordinary claims.
Output a JSON array only."""


def _compact_articles(articles: List[Dict]) -> str:
    out = []
    for i, a in enumerate(articles, 1):
        cred = a.get("factual_reporting") or a.get("mbfc_credibility_rating") or "unknown"
        out.append(f"[{i}] {a.get('title') or ''} | {a.get('news_source') or ''} | "
                   f"{str(a.get('publication_date') or '')[:10]} | credibility: {cred}\n"
                   f"{(a.get('summary') or '').strip()}")
    return "\n\n".join(out)


async def _read_batch(req, topic: str, articles: List[Dict], prof: str) -> List[Dict]:
    """The daily reading of one batch: short records, mapped back to URIs."""
    from app.ai_models import LiteLLMModel, extract_content
    model = LiteLLMModel.get_instance(DAY_MODEL)
    if not model:
        raise RuntimeError(f"model {DAY_MODEL} unavailable")
    response = await model.agenerate_response(
        [{"role": "system", "content": _DAY_SYSTEM.format(topic=topic, profile=prof)},
         {"role": "user", "content": _compact_articles(articles)}],
        max_tokens=DAY_MAX_TOKENS, temperature=0.0)
    raw = extract_content(response).strip()
    start_i = raw.find("[")
    if start_i < 0:
        raise ValueError(f"no JSON array in answer: {raw[:200]!r}")
    try:
        data, _ = json.JSONDecoder().raw_decode(raw[start_i:])
    except ValueError as e:
        import json_repair
        data = json_repair.loads(raw[start_i:])
        if not isinstance(data, list):
            raise ValueError(f"unparseable answer: {e}")
        logger.warning(f"incident day reading: JSON repaired ({e}); {len(data)} records kept")
    out = []
    for r in data if isinstance(data, list) else []:
        if not isinstance(r, dict) or not r.get("n"):
            continue
        idx = [int(i) for i in (r.get("a") or []) if str(i).strip().isdigit()]
        cited = [articles[i - 1] for i in idx if 1 <= i <= len(articles)]
        if not cited:
            continue
        pubs = sorted(str(a.get("publication_date") or "")[:10] for a in cited)
        d = r.get("d")
        out.append({
            "name": str(r["n"])[:300],
            "type": r.get("t") or "event",
            "subtype": r.get("st") or "",
            "significance": str(r.get("s") or "medium").lower(),
            "description": str(r.get("x") or "")[:600],
            "article_uris": [a["uri"] for a in cited],
            "event_date": d if isinstance(d, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", d) else None,
            "published": pubs[0] if pubs else None,
        })
    return out


def _slice_key(cfg: str, topic: str, day: str) -> str:
    return f"incident_day|{cfg}|{topic}|{day}"


def window_days(start: date, end: date) -> List[str]:
    out, d = [], start
    while d <= end:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _base_filter() -> str:
    """The rows the old incident query read: analysed (or, where the site has the
    rule, relevant social posts), with a sentiment, and readable."""
    from app.services import article_visibility as av
    evidence = (av.agent_evidence_sql() if hasattr(av, "agent_evidence_sql")
                else "category IS NOT NULL")
    return f"{evidence} AND NULLIF(TRIM(sentiment), '') IS NOT NULL AND {av.readable_sql()}"


def _fingerprints(db, topics: List[str], start: date, end: date) -> Dict[Tuple[str, str], Tuple[int, str]]:
    conn = db._temp_get_connection()
    try:
        rows = conn.execute(text(f"""
            SELECT topic, substr(publication_date, 1, 10) AS d, count(*),
                   md5(string_agg(uri, '|' ORDER BY uri))
            FROM articles
            WHERE publication_date >= :s AND publication_date <= :e
              AND topic = ANY(:topics) AND {_base_filter()}
            GROUP BY 1, 2
        """), {"s": start.isoformat(), "e": end.isoformat() + " 23:59:59", "topics": topics}).fetchall()
        return {(r[0], r[1]): (int(r[2]), r[3]) for r in rows if r[1]}
    finally:
        conn.close()


def _load_slices(db, keys: List[str]) -> Dict[str, Dict]:
    if not keys:
        return {}
    conn = db._temp_get_connection()
    try:
        rows = conn.execute(text("""
            SELECT article_uri, content FROM article_analysis_cache
            WHERE analysis_type = 'incident_day' AND model_used = 'incident_day'
              AND article_uri = ANY(:keys)
        """), {"keys": keys}).fetchall()
        out = {}
        for k, c in rows:
            try:
                out[k] = json.loads(c)
            except (TypeError, ValueError):
                pass
        return out
    finally:
        conn.close()


def _save_slice(db, key: str, payload: Dict) -> None:
    conn = db._temp_get_connection()
    try:
        conn.execute(text("""
            INSERT INTO article_analysis_cache
                (article_uri, analysis_type, content, model_used, generated_at, expires_at)
            VALUES (:k, 'incident_day', :c, 'incident_day', NOW(), NULL)
            ON CONFLICT (article_uri, analysis_type, model_used)
            DO UPDATE SET content = EXCLUDED.content, generated_at = NOW()
        """), {"k": key, "c": json.dumps(payload, ensure_ascii=False, default=str)})
        conn.commit()
    finally:
        conn.close()


def _slice_articles(db, topic: str, days: List[str]) -> List[Dict]:
    conn = db._temp_get_connection()
    try:
        rows = conn.execute(text(f"""
            SELECT {_ARTICLE_COLS} FROM articles
            WHERE topic = :t AND substr(publication_date, 1, 10) = ANY(:days)
              AND {_base_filter()}
            ORDER BY publication_date, uri
        """), {"t": topic, "days": days}).mappings().all()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _pack(topic: str, days: List[str], articles: List[Dict]) -> List[Dict]:
    """Batches of up to BATCH_SIZE articles, in day order. A day larger than a
    batch is split; small days share a batch."""
    by_day: Dict[str, List[Dict]] = {d: [] for d in days}
    for a in articles:
        d = str(a.get("publication_date") or "")[:10]
        if d in by_day:
            by_day[d].append(a)
    batches, cur, cur_days = [], [], []
    for d in days:
        items = by_day[d]
        if not items:
            continue
        if len(items) > BATCH_SIZE:
            if cur:
                batches.append({"topic": topic, "days": cur_days, "articles": cur})
                cur, cur_days = [], []
            for i in range(0, len(items), BATCH_SIZE):
                batches.append({"topic": topic, "days": [d], "articles": items[i:i + BATCH_SIZE]})
            continue
        if len(cur) + len(items) > BATCH_SIZE:
            batches.append({"topic": topic, "days": cur_days, "articles": cur})
            cur, cur_days = [], []
        cur.extend(items)
        cur_days.append(d)
    if cur:
        batches.append({"topic": topic, "days": cur_days, "articles": cur})
    return batches


def _sig(inc: Dict) -> int:
    return _SIG_RANK.get(str(inc.get("significance") or "").lower(), 0)


async def read_window(req, db, topics: List[str], start: date, end: date,
                      progress: Optional[Callable[[Dict], None]] = None) -> Dict:
    """Bring every (topic, day) slice of the window up to date and return all
    candidate incidents plus counts."""
    cfg = config_hash(req)
    fps = await asyncio.to_thread(_fingerprints, db, topics, start, end)
    keys = {sk: _slice_key(cfg, sk[0], sk[1]) for sk in fps}
    stored = await asyncio.to_thread(_load_slices, db, list(keys.values()))

    fresh: Dict[Tuple[str, str], Dict] = {}
    stale_by_topic: Dict[str, List[str]] = {}
    for sk, (n, h) in fps.items():
        s = stored.get(keys[sk])
        if s and s.get("fingerprint") == h:
            fresh[sk] = s
        else:
            stale_by_topic.setdefault(sk[0], []).append(sk[1])

    # A changed slice reads only the articles it has not read before. Records
    # citing articles that have since left the slice lose those citations, and
    # go when none are left. Today's slice changes all day; rereading all of it
    # on every Generate would repeat most of the work.
    batches: List[Dict] = []
    base: Dict[Tuple[str, str], List[Dict]] = {}
    current_uris: Dict[Tuple[str, str], List[str]] = {}
    for topic, days in stale_by_topic.items():
        days.sort()
        arts = await asyncio.to_thread(_slice_articles, db, topic, days)
        by_day: Dict[str, List[Dict]] = {}
        for a in arts:
            by_day.setdefault(str(a.get("publication_date") or "")[:10], []).append(a)
        to_read = []
        for d in days:
            sk = (topic, d)
            cur = {a["uri"] for a in by_day.get(d, [])}
            current_uris[sk] = sorted(cur)
            prev = stored.get(keys[sk]) or {}
            seen = set(prev.get("uris") or [])
            kept = []
            if seen:
                for inc in prev.get("incidents") or []:
                    uris = [u for u in (inc.get("article_uris") or []) if u in cur]
                    if uris:
                        kept.append({**inc, "article_uris": uris})
            base[sk] = kept
            to_read += [a for a in by_day.get(d, []) if a["uri"] not in seen]
        batches.extend(_pack(topic, days, to_read))

    state = {"phase": "reading", "batches_total": len(batches), "batches_done": 0,
             "batches_failed": 0, "slices_total": len(fps), "slices_reused": len(fresh),
             "articles_total": sum(n for n, _ in fps.values())}
    if progress:
        progress(dict(state))

    # One batch's incidents per slice it covered; a slice only counts as read
    # when every batch that touched it succeeded.
    found: Dict[Tuple[str, str], List[Dict]] = {}
    failed_slices = set()
    sem = asyncio.Semaphore(CONCURRENCY)
    prof = await asyncio.to_thread(profile_line, db, req.profile_id) if batches else ""

    async def run(batch: Dict):
        topic = batch["topic"]
        day_of = {a["uri"]: str(a.get("publication_date") or "")[:10] for a in batch["articles"]}
        async with sem:
            try:
                incs = await _read_batch(req, topic, batch["articles"], prof)
            except Exception as e:  # noqa: BLE001 — one bad batch must not sink the window
                logger.warning(f"incident batch failed ({topic}, {batch['days'][0]}..{batch['days'][-1]}, "
                               f"{len(batch['articles'])} articles): {e}")
                for d in batch["days"]:
                    failed_slices.add((topic, d))
                state["batches_failed"] += 1
                incs = None
        if incs is not None:
            for d in batch["days"]:
                found.setdefault((topic, d), [])
            for inc in incs:
                if not isinstance(inc, dict):
                    continue
                cited = sorted(day_of[u] for u in (inc.get("article_uris") or [])
                               if isinstance(u, str) and u in day_of)
                d = cited[0] if cited else batch["days"][0]
                inc["topic"] = topic
                inc["slice_day"] = d
                found[(topic, d)].append(inc)
        state["batches_done"] += 1
        if progress:
            progress(dict(state))

    await asyncio.gather(*(run(b) for b in batches))

    # A slice with a failed batch is not saved, so the next run reads it again;
    # this run still uses what its other batches found.
    partial: Dict[Tuple[str, str], List[Dict]] = {}
    for sk in base:
        incs = base[sk] + found.get(sk, [])
        if sk in failed_slices:
            partial[sk] = incs
            continue
        n, h = fps[sk]
        payload = {"fingerprint": h, "articles": n, "uris": current_uris[sk], "incidents": incs,
                   "read_at": datetime.utcnow().isoformat()}
        await asyncio.to_thread(_save_slice, db, keys[sk], payload)
        fresh[sk] = payload

    candidates = [inc for sk in sorted(fresh) for inc in (fresh[sk].get("incidents") or [])
                  if isinstance(inc, dict)]
    candidates += [inc for sk in sorted(partial) for inc in partial[sk] if isinstance(inc, dict)]
    state.update({"phase": "merging", "candidates": len(candidates),
                  "slices_incomplete": len(failed_slices)})
    if progress:
        progress(dict(state))
    return {"candidates": candidates, "stats": state}


def _combine(group: List[Dict]) -> Dict:
    """One incident from a group of candidates reporting the same development.
    The strongest member (significance, then articles cited) keeps its wording;
    the others contribute their articles and dates. Members may themselves be
    groups from an earlier merge round."""
    group = sorted(group, key=lambda i: (-_sig(i), -len(i.get("article_uris") or [])))
    base = dict(group[0])
    if len(group) == 1:
        return base
    uris, seen = [], set()
    for inc in sorted(group, key=lambda i: str(i.get("slice_day") or "")):
        for u in inc.get("article_uris") or []:
            if isinstance(u, str) and u not in seen:
                seen.add(u)
                uris.append(u)
    base["article_uris"] = uris
    pubs = sorted(p for p in (str(i.get("published") or "")[:10] for i in group) if p)
    if pubs:
        base["published"] = pubs[0]
    days = set()
    for i in group:
        days.update(i.get("days_seen") or ([i["slice_day"]] if i.get("slice_day") else []))
    base["days_seen"] = sorted(str(d) for d in days)
    base["slice_day"] = base["days_seen"][0] if base["days_seen"] else base.get("slice_day")
    base["merged_from"] = sum(int(i.get("merged_from") or 1) for i in group)
    return base


def _rank_key(inc: Dict):
    return (-_sig(inc), -len(inc.get("article_uris") or []), str(inc.get("slice_day") or ""))


# One merge call sees at most MERGE_CHUNK one-line findings. A single call over
# 4,000 of them (wileytest, 13 Oct 2026) put 1,688 unrelated findings in one
# group; chunks of a few hundred group correctly. Larger windows merge in
# rounds: each chunk keeps its top MERGE_KEEP groups for the next round.
MERGE_CHUNK = 250
MERGE_KEEP = 30
# A group this large is the model lumping, not one story: its members stay apart.
MERGE_MAX_GROUP = 25


def _groups_array(raw: str) -> List:
    """The [{"ids": [...]}, ...] array in a merge answer, wherever it sits."""
    fence = re.findall(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
    starts = [raw.rfind(f) for f in ('[{"ids"', "[\n  {", "[\n{", "[{")]
    candidates = fence + [raw[i:] for i in sorted({i for i in starts if i >= 0})]
    if raw.find("[") >= 0:
        candidates.append(raw[raw.find("["):])   # last resort: a bare list of ids
    for c in candidates:
        try:
            data, _ = json.JSONDecoder().raw_decode(c)
        except ValueError:
            try:
                import json_repair
                data = json_repair.loads(c)
            except Exception:  # noqa: BLE001
                continue
        if isinstance(data, list) and data:
            return data
    raise ValueError(f"no groups array in merge answer: {raw[:120]!r}")


async def _merge_chunk(items: List[Dict], keep: int, topics: List[str], start: date, end: date,
                       model_name: str) -> Tuple[List[Dict], bool]:
    """Group duplicates in one chunk and return its top `keep`, best first.
    Returns (items, used_llm); falls back to a plain ranking on failure."""
    lines = []
    for i, c in enumerate(items):
        name = re.sub(r"\s+", " ", str(c.get("name") or ""))[:160]
        lines.append(f"{i}|{c.get('slice_day') or ''}|{c.get('topic') or ''}|"
                     f"{(c.get('significance') or '').lower()}|{len(c.get('article_uris') or [])}|{name}")
    prompt = (
        f"Below are {len(items)} findings an analyst extracted, day by day, from articles collected "
        f"between {start.isoformat()} and {end.isoformat()} for these topics: {', '.join(topics)}.\n"
        "Each line is: id|day|topic|significance|articles cited|headline.\n\n"
        "1. Most findings are about different events. Group findings only when they report the same "
        "specific development (the same actors and the same event), for example the same deal "
        "reported on several days. Never group findings just because they share a theme, a company "
        "or a country.\n"
        f"2. Return the {keep} most important groups for a strategic intelligence analyst, most "
        "important first; a finding that matches nothing else is a group of one. Weigh significance, "
        "how many articles and days carry the story, and material impact. Do not invent items.\n\n"
        "Answer with JSON only: [{\"ids\": [3, 17, 42]}, ...]\n\n" + "\n".join(lines))
    try:
        from app.ai_models import LiteLLMModel, extract_content
        model = LiteLLMModel.get_instance(model_name)
        # Kimi tends to write an analysis before the JSON: ask for JSON only,
        # leave room for the prose when it comes anyway, and parse the groups
        # array rather than the first bracket (the prose has "(37, 40, ...)"
        # lists and "[1]"-style notes).
        response = await model.agenerate_response(
            [{"role": "system", "content": "You answer with a JSON array only. No commentary, no markdown."},
             {"role": "user", "content": prompt}], max_tokens=8000, temperature=0.0)
        raw = extract_content(response).strip()
        data = _groups_array(raw)
        out, used = [], set()
        for g in data:
            ids = g.get("ids") if isinstance(g, dict) else g
            if isinstance(ids, int):
                ids = [ids]
            ids = [i for i in (ids if isinstance(ids, list) else []) if isinstance(i, int)
                   and 0 <= i < len(items) and i not in used]
            if not ids:
                continue
            if len(ids) > MERGE_MAX_GROUP:
                logger.warning(f"incident merge: ignored a {len(ids)}-finding group as implausible")
                continue
            used.update(ids)
            out.append(_combine([items[i] for i in ids]))
            if len(out) >= keep:
                break
        if not out:
            raise ValueError("merge answer had no usable groups")
        return out, True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"incident merge call failed for {len(items)} findings, ranking without grouping: {e}")
        uniq, seen = [], set()
        for c in sorted(items, key=_rank_key):
            k = re.sub(r"\W+", " ", str(c.get("name") or "").lower()).strip()
            if k in seen:
                continue
            seen.add(k)
            uniq.append(c)
        return uniq[:keep], False


async def _merge_rounds(items: List[Dict], keep: int, topics: List[str], start: date, end: date,
                        model_name: str, sem: asyncio.Semaphore) -> Tuple[List[Dict], bool, int]:
    """Merge `items` in rounds of MERGE_CHUNK until one call can rank them, and
    return (its top `keep`, every call used the model, rounds run)."""
    def order(xs):
        return sorted(xs, key=lambda c: (str(c.get("topic") or ""), str(c.get("slice_day") or "")))
    items, llm_ok, rounds = order(items), True, 1
    while len(items) > MERGE_CHUNK:
        rounds += 1
        chunks = [items[k:k + MERGE_CHUNK] for k in range(0, len(items), MERGE_CHUNK)]

        async def one(chunk):
            async with sem:
                return await _merge_chunk(chunk, MERGE_KEEP, topics, start, end, model_name)
        results = await asyncio.gather(*(one(c) for c in chunks))
        llm_ok = llm_ok and all(ok for _, ok in results)
        items = order(x for r, _ in results for x in r)
    async with sem:
        final, ok = await _merge_chunk(items, keep, topics, start, end, model_name)
    return final, llm_ok and ok, rounds


def _same_story(a: Dict, b: Dict) -> bool:
    ua = {u for u in a.get("article_uris") or [] if isinstance(u, str)}
    return bool(ua & {u for u in b.get("article_uris") or [] if isinstance(u, str)})


async def merge_and_rank(candidates: List[Dict], topics: List[str], start: date, end: date,
                         model_name: str, limit: int = MERGE_LIMIT_DEFAULT,
                         per_topic: int = PER_TOPIC_DEFAULT) -> Tuple[List[Dict], str]:
    """Group duplicates across the window and keep the `limit` most significant,
    plus up to `per_topic` places for every topic that has findings.

    Each topic is merged and ranked on its own first, so a small topic never
    competes with a large one for a chunk's places (wileytest, 13 Oct 2026: the
    brand and publishing topics hold 3% of the articles and got none of the top
    40). The open `limit` places are then ranked across topics; a topic with
    fewer than `per_topic` of them is topped up with its own best, after them.
    Every finding is considered. Returns (incidents, method)."""
    if not candidates:
        return [], "none"
    sem = asyncio.Semaphore(CONCURRENCY)
    by_topic: Dict[str, List[Dict]] = {}
    for c in candidates:
        by_topic.setdefault(str(c.get("topic") or ""), []).append(c)
    keep_t = max(MERGE_KEEP, per_topic)
    results = await asyncio.gather(*(
        _merge_rounds(items, keep_t, [t] if t else topics, start, end, model_name, sem)
        for t, items in sorted(by_topic.items())))
    ranked = {t: r for t, (r, _, _) in zip(sorted(by_topic), results)}
    llm_ok = all(ok for _, ok, _ in results)
    rounds = max(n for _, _, n in results)

    pooled = [x for r in ranked.values() for x in r]
    if len(by_topic) == 1:
        final = pooled[:limit]
    else:
        final, ok, n = await _merge_rounds(pooled, limit, topics, start, end, model_name, sem)
        llm_ok, rounds = llm_ok and ok, rounds + n

    if per_topic > 0:
        for t in sorted(ranked):
            have = sum(1 for f in final if str(f.get("topic") or "") == t)
            for item in ranked[t]:
                if have >= per_topic:
                    break
                if any(_same_story(item, f) for f in final):
                    continue
                final.append({**item, "topic_place": True})
                have += 1
    return final, ("llm" if llm_ok else "ranked") + f", {rounds} rounds"



# --- background jobs (one process per site, so memory is enough) ---

_JOBS: Dict[str, Dict] = {}
_JOB_TTL = 3600


def start_job(make: Callable[[Callable[[Dict], None]], Awaitable[Dict]]) -> str:
    now = time.time()
    for k in [k for k, v in _JOBS.items() if now - v["started"] > _JOB_TTL and v["status"] != "running"]:
        _JOBS.pop(k, None)
    job_id = uuid.uuid4().hex[:16]
    job = {"status": "running", "started": now, "progress": {"phase": "starting"},
           "result": None, "error": None}
    _JOBS[job_id] = job

    def progress(p: Dict):
        job["progress"] = p

    async def runner():
        try:
            job["result"] = await make(progress)
            job["status"] = "done"
        except Exception as e:  # noqa: BLE001
            logger.error(f"incident tracking job {job_id} failed: {e}", exc_info=True)
            job["error"] = getattr(e, "detail", None) or str(e)
            job["status"] = "error"

    job["task"] = asyncio.create_task(runner())
    return job_id


def get_job(job_id: str) -> Optional[Dict]:
    job = _JOBS.get(job_id)
    if not job:
        return None
    return {k: v for k, v in job.items() if k != "task"}
