"""Brand topics: does the article name the brand, in the brand's sense?

The relevance scorer asks whether an article is *about* its topic. For a
brand topic that is the wrong question for most earned media: a dietitian
quoted in a Focus piece on eggs, a CEO booked for a TV panel, a reader stuck
on the company's NHS waiting list. None of those is about Oviva, all of them
are coverage of Oviva, and the scorer gave every one of them 0.0 to 0.1
(oviva, 1 Oct 2026: 19 press articles naming Oviva dropped in 90 days, 31
for WeightWatchers, 10 for Noom).

Three per-brand settings live in ``bw_brands.config``:

``mention_context``
    Words that must appear near a mention for it to count (``app``, ``NHS``,
    ``Adipositas`` ...). Keeps "Uncle Fred Oviva" in an ABC museum story out.
    A brand without this list is never lifted by the mention floor: for a
    common-word name ("Second Nature") a match is usually not the brand.
``exclude_context``
    Words that mark a mention as a different subject with the same name. OVIVA
    is also a well-known antibiotics trial in bone and joint infection;
    ``antibiot``, ``osteomyel``, ``ortho-ID`` beside it mean the trial.
``non_press_domains``
    Sites whose pages never count as this brand's press. ww-recipes.net was 37
    of WeightWatchers' 48 kept press items: a fan site publishing points
    recipes, not coverage of the company.

The mention floor (``BW_BRAND_MENTION_FLOOR``, off when unset) is per site;
the three lists are per brand. ``judge`` is pure and testable; ``apply`` rewrites
a relevance result in place.
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_BRAND_TOPIC_RE = re.compile(r"^Brand Monitoring\s+(.+)$", re.I)
_WINDOW = 200      # characters either side of a mention that count as its context
# Start of the explanation written when a mention is kept. The Brand Watcher
# classification selects on it (kept_mentions_sql), so keep the two in step.
KEPT_MARK = "Kept as a mention of "
_SNIPPET = 110
_TTL_S = 300
_cache: Dict[str, Any] = {"at": 0.0, "brands": None}


def mention_floor() -> float:
    """Relevance given to a brand-topic article that names the brand. 0 = off."""
    try:
        return max(0.0, float(os.getenv("BW_BRAND_MENTION_FLOOR", "") or 0))
    except ValueError:
        return 0.0


def _terms_regex(terms: Iterable[str]) -> Optional[re.Pattern]:
    """Case-insensitive alternation of terms, each a whole word.

    A term ending in ``*`` is a stem and matches the start of a word
    ("antibiot*" matches "antibiotics"). Plain terms never match inside a
    word, so "app" does not fire on "happens".
    """
    parts = []
    for t in terms or ():
        t = (t or "").strip()
        if not t:
            continue
        stem = t.endswith("*")
        esc = re.escape(t.rstrip("*"))
        parts.append(rf"(?<!\w){esc}" if stem else rf"(?<!\w){esc}(?!\w)")
    if not parts:
        return None
    # Longest first, so "Oviva NHS" wins over "Oviva" in the snippet.
    parts.sort(key=len, reverse=True)
    return re.compile("|".join(parts), re.I)


def _as_list(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x) for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        import json
        try:
            parsed = json.loads(v)
            return _as_list(parsed)
        except ValueError:
            return [v]
    return []


def build_brand(display_name: str, keywords: Iterable[str], products: Iterable[str],
                config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """One brand's matchers, from its row. Separate so tests need no database."""
    cfg = config or {}
    names = [display_name, *(keywords or ()), *(products or ())]
    return {
        "display_name": display_name,
        "names": _terms_regex(names),
        "single_names": _terms_regex([n for n in names if n and " " not in n.strip()]),
        "context": _terms_regex(_as_list(cfg.get("mention_context"))),
        "exclude": _terms_regex(_as_list(cfg.get("exclude_context"))),
        "non_press": {d.lower().lstrip(".").removeprefix("www.")
                      for d in _as_list(cfg.get("non_press_domains"))},
    }


def _load(conn=None) -> Dict[str, Dict[str, Any]]:
    now = time.monotonic()
    if _cache["brands"] is not None and now - _cache["at"] < _TTL_S:
        return _cache["brands"]
    brands: Dict[str, Dict[str, Any]] = {}
    own = conn is None
    try:
        from sqlalchemy import text
        if own:
            from app.database import get_database_instance
            conn = get_database_instance()._temp_get_connection()
        rows = conn.execute(text("""
            SELECT display_name, brand_keywords, product_keywords, config
              FROM bw_brands WHERE enabled
        """)).mappings().all()
        for r in rows:
            cfg = r["config"]
            if isinstance(cfg, str):
                import json
                try:
                    cfg = json.loads(cfg)
                except ValueError:
                    cfg = {}
            b = build_brand(r["display_name"] or "", _as_list(r["brand_keywords"]),
                            _as_list(r["product_keywords"]), cfg if isinstance(cfg, dict) else {})
            brands[(r["display_name"] or "").strip().lower()] = b
    except Exception as e:  # noqa: BLE001 - a lookup failure must never block ingest
        logger.debug("brand_mention_gate: brand load failed: %s", e)
        return _cache["brands"] or {}
    finally:
        if own and conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
    _cache.update(at=now, brands=brands)
    return brands


def brand_for_topic(topic: str, conn=None) -> Optional[Dict[str, Any]]:
    m = _BRAND_TOPIC_RE.match((topic or "").strip())
    if not m:
        return None
    return _load(conn).get(m.group(1).strip().lower())


def host_of(url: str) -> str:
    try:
        h = urlparse(url or "").netloc.lower()
    except ValueError:
        return ""
    return h.split("@")[-1].split(":")[0].removeprefix("www.")


def _listed(host: str, domains: Iterable[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains if d)


def judge(brand: Dict[str, Any], text_: str, url: str = "", source: str = "") -> Dict[str, Any]:
    """Verdict for one article or post against one brand.

    ``non_press``  the page is on a site listed as not this brand's press.
    ``named``      a mention with brand context nearby (or no context list set).
    ``excluded``   every mention sits beside a different-subject term.
    ``weak``       named, but no mention has brand context nearby.
    ``not_named``  the brand is not named at all.
    """
    host = host_of(url)
    src = (source or "").strip().lower().removeprefix("www.")
    if brand["non_press"] and (_listed(host, brand["non_press"]) or _listed(src, brand["non_press"])):
        return {"verdict": "non_press", "snippet": host or src}
    pat = brand["names"]
    body = text_ or ""
    if pat is None:
        return {"verdict": "not_named", "snippet": ""}
    seen_excluded = seen_weak = None
    for m in pat.finditer(body):
        # "for weight watchers" in lower case means dieters, not the company
        # (Economic Times on McDonald's, Sep 2026). A multi-word name counts
        # only with a capital somewhere; a one-word name ("oviva app") counts
        # in any case, because that is how people write it in posts.
        if " " in m.group(0) and m.group(0).islower():
            single = brand.get("single_names")
            if not (single is not None and single.match(body, m.start())):
                continue
        lo, hi = max(0, m.start() - _WINDOW), min(len(body), m.end() + _WINDOW)
        window = body[lo:hi]
        snip_lo, snip_hi = max(0, m.start() - _SNIPPET // 2), min(len(body), m.end() + _SNIPPET // 2)
        snippet = re.sub(r"\s+", " ", body[snip_lo:snip_hi]).strip()
        if brand["exclude"] is not None and brand["exclude"].search(window):
            seen_excluded = seen_excluded or snippet
            continue
        if brand["context"] is not None and not brand["context"].search(window):
            seen_weak = seen_weak or snippet
            continue
        return {"verdict": "named", "snippet": snippet}
    if seen_excluded:
        return {"verdict": "excluded", "snippet": seen_excluded}
    if seen_weak:
        return {"verdict": "weak", "snippet": seen_weak}
    return {"verdict": "not_named", "snippet": ""}


def article_text(article: Dict[str, Any]) -> str:
    return "\n".join(str(article.get(k) or "") for k in ("title", "summary", "content", "raw"))


def apply(result: Dict[str, Any], topic: str, article: Dict[str, Any]) -> Dict[str, Any]:
    """Adjust a relevance result for a brand topic. Returns the same dict.

    Non-press pages and wrong-subject mentions go to 0. A real mention is
    lifted to the site's floor when the subject scorer put it below. Every
    change says why in ``overall_match_explanation``.
    """
    brand = brand_for_topic(topic)
    if not brand:
        return result
    v = judge(brand, article_text(article), article.get("uri") or article.get("url") or "",
              article.get("news_source") or "")
    name = brand["display_name"]
    before = float(result.get("relevance_score") or 0.0)
    if v["verdict"] == "non_press":
        _set(result, 0.0, f"Not press for {name}: {v['snippet']} is listed as a site whose "
                          f"pages do not count as this brand's coverage.")
        result["_brand_gate"] = "non_press"
    elif v["verdict"] == "excluded":
        _set(result, 0.0, f"Names {name} only beside a different subject with the same name: "
                          f"\"{v['snippet']}\"")
        result["_brand_gate"] = "excluded"
    elif (v["verdict"] in ("not_named", "weak") and brand["context"] is not None
          and mention_floor() and before < mention_floor()):
        # Collectors often hand over a snippet that stops before the paragraph
        # naming the brand, and every collection cycle re-scores the same URL
        # from that snippet. On oviva that turned approved mentions back into
        # rejections minutes after they were recovered (1 Oct 2026). The page
        # we already stored is the better text, so read it before giving up.
        page = _stored_page(article.get("uri") or article.get("url") or "")
        if page:
            v2 = judge(brand, page)
            if v2["verdict"] == "named":
                _set(result, mention_floor(),
                     f"{KEPT_MARK}{name} (subject score {before:.2f}): \"{v2['snippet']}\"")
                result["_brand_gate"] = "mention_floor"
    elif v["verdict"] == "named" and brand["context"] is not None:
        # Only a brand with a mention_context list is lifted. Without one a
        # "mention" of Second Nature is the phrase, of Numan a surname, of Voy
        # a Spanish verb (oviva audit, 1 Oct 2026: 42, 7 and 5 such rows).
        floor = mention_floor()
        if floor and before < floor:
            _set(result, floor, f"{KEPT_MARK}{name} (subject score {before:.2f}): "
                                f"\"{v['snippet']}\"")
            result["_brand_gate"] = "mention_floor"
    return result


def kept_mentions_sql(brand_filter: str, params: Dict[str, Any], display_name: str,
                      alias: str = "a") -> tuple:
    """Widen a brand-name SQL filter to take the mentions this module kept.

    The Brand Watcher classification picks articles whose title, summary,
    tags or keywords name the brand. A kept mention usually names it only in
    the body (a quoted dietitian, a CEO on a panel), so without this the
    category table, and every stat read from it, never sees it: on oviva 28
    of 29 recovered articles (1 Oct 2026). Takes the ``"AND (...)"`` fragment
    ``_build_brand_filter_sql`` returns and adds rows in the brand's own topic
    whose explanation starts with KEPT_MARK.
    """
    if not brand_filter.startswith("AND "):
        return brand_filter, params
    p = dict(params)
    p["_bmg_topic"] = f"Brand Monitoring {display_name}"
    p["_bmg_mark"] = f"{KEPT_MARK}{display_name}%"
    return (f"AND ({brand_filter[4:]} OR ({alias}.topic = :_bmg_topic"
            f" AND {alias}.overall_match_explanation LIKE :_bmg_mark))"), p


def kept_mention_evidence(conn, uris: List[str]) -> Dict[str, Dict[str, str]]:
    """For kept mentions among ``uris``: {uri: {"brand": name, "snippet": text}}.

    A kept mention names the brand in the body, so a keyword match on the
    title and summary comes back empty. A reader, human or model, then
    concludes the article does not mention the brand at all: an MCP report
    on oviva (1 Oct 2026) said "none of the 13 earned articles contain an
    Oviva keyword". The explanation written at ingest carries the sentence.
    """
    if not uris:
        return {}
    from sqlalchemy import text
    out: Dict[str, Dict[str, str]] = {}
    rows = conn.execute(text("""
        SELECT uri, overall_match_explanation FROM articles
         WHERE uri = ANY(:u) AND overall_match_explanation LIKE :m
    """), {"u": list(uris), "m": KEPT_MARK + "%"}).fetchall()
    pat = re.compile(re.escape(KEPT_MARK) + r'(.+?) \(subject score [0-9.]+\): "(.*)"\s*$', re.S)
    for uri, expl in rows:
        m = pat.match(expl or "")
        if m:
            out[uri] = {"brand": m.group(1), "snippet": m.group(2)}
    return out


def _stored_page(uri: str) -> str:
    """The page text stored for this URL in raw_articles, or ''."""
    if not uri:
        return ""
    conn = None
    try:
        from sqlalchemy import text
        from app.database import get_database_instance
        conn = get_database_instance()._temp_get_connection()
        row = conn.execute(text("SELECT raw_markdown FROM raw_articles WHERE uri = :u"),
                           {"u": uri}).scalar()
        return (row or "")[:30000]
    except Exception as e:  # noqa: BLE001 - never block scoring
        logger.debug("brand_mention_gate: stored page lookup failed: %s", e)
        return ""
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def _set(result: Dict[str, Any], score: float, why: str) -> None:
    for k in ("relevance_score", "topic_alignment_score", "confidence_score"):
        result[k] = score
    result["overall_match_explanation"] = why
