"""Analyst research for a market: the public trail of paywalled reports.

Gartner, Forrester, KuppingerCole and IDC keep the reports themselves
behind paywalls. Two things about them are public, and both are in the
corpus already or can be read as a feed:

1. **Citations.** A vendor named in a report says so — a press release
   ("named a Major Player in the 2026 IDC MarketScape for …") or a LinkedIn
   post ("Gartner just dropped the 2026 Hype Cycle for Security Operations").
   ``cite`` finds those in a corpus row and ``group_citations`` folds them by
   report, so the page can say which report and who got named. Rules, no
   model: a firm name, plus either a report family (Magic Quadrant, Hype
   Cycle, Wave, Leadership Compass, MarketScape …) or a recognition verb
   near the firm. A post about attending a Gartner summit has neither and
   is left out; a Peer Insights mention is customer reviews, not research,
   and is left out too.

2. **The firms' public pages.** Forrester's security blog and
   KuppingerCole's research listing are RSS feeds. ``sync_feeds`` registers
   them under the market's collection topic, so the RSS monitor reads them
   like the vendor blogs and the daily corpus scan attaches the items that
   mention the market. ``analyst_posts`` picks those rows out of the corpus
   by the firm's domain. Gartner's blogs answer this host with 403, so
   Gartner appears only through citations — which is where it dominates.

Every item links to its source; nothing is republished.
"""
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: The firms, with the name patterns (case-insensitive unless ``exact``)
#: and the domains their public pages live on.
FIRMS: List[Dict[str, Any]] = [
    {"name": "Gartner", "patterns": [r"\bgartner\b"], "domains": ("gartner.com",)},
    {"name": "Forrester", "patterns": [r"\bforrester\b"], "domains": ("forrester.com",)},
    {"name": "KuppingerCole", "patterns": [r"\bkuppinger\s?cole\b"],
     "domains": ("kuppingercole.com",)},
    {"name": "IDC", "patterns": [r"\bIDC\b"], "exact": True, "domains": ("idc.com",)},
    {"name": "Omdia", "patterns": [r"\bomdia\b"], "domains": ("omdia.tech.informa.com", "omdia.com")},
    {"name": "GigaOm", "patterns": [r"\bgigaom\b"], "domains": ("gigaom.com",)},
    {"name": "451 Research",
     "patterns": [r"\b451\s+research\b", r"\bs&(?:amp;)?p\s+global\s+market\s+intelligence\b"],
     "domains": ("451research.com",)},
    {"name": "Enterprise Strategy Group",
     "patterns": [r"\benterprise\s+strategy\s+group\b"], "exact_patterns": [r"\bESG\b"],
     "domains": ("esg-global.com",)},
    {"name": "Frost & Sullivan", "patterns": [r"\bfrost\s*&(?:amp;)?\s*sullivan\b"],
     "domains": ("frost.com",)},
    {"name": "ISG", "patterns": [], "exact_patterns": [r"\bISG\b"], "domains": ("isg-one.com",)},
]

#: Report families, most specific first: label, pattern, and the word that
#: joins the family to its topic in the firm's own naming ("Hype Cycle for
#: Security Operations", "Innovation Insight: AI SOC Agents", "Cool Vendors
#: in Identity-First Security"). The label is what the page prints.
REPORT_FAMILIES: List[Tuple[str, str, str]] = [
    ("Magic Quadrant", r"magic\s+quadrant", "for"),
    ("Critical Capabilities", r"critical\s+capabilities", "for"),
    ("Market Guide", r"market\s+guide", "for"),
    ("Hype Cycle", r"hype\s+cycle", "for"),
    ("Cool Vendors", r"cool\s+vendors?", "in"),
    ("Innovation Insight", r"innovation\s+insight", ":"),
    ("Emerging Tech Impact Radar", r"emerging\s+tech(?:nolog(?:y|ies))?\s+impact\s+radar", ":"),
    ("Emerging Tech", r"emerging\s+tech(?:nolog(?:y|ies))?(?=\s*:)", ":"),
    ("Forrester Wave", r"forrester\s+wave|forrester\s+new\s+wave|\bnew\s+wave\b", "for|on"),
    ("Tech Tide", r"tech\s+tide", ":"),
    ("Landscape", r"landscape\s*(?:™|®)?\s*(?:report|,\s*q[1-4])", "for"),
    ("Leadership Compass", r"leadership\s+compass", "for|on"),
    ("Rising Star", r"rising\s+star", ":"),
    ("Executive View", r"executive\s+view", ":"),
    ("Market Compass", r"market\s+compass", "for|on"),
    ("MarketScape", r"marketscape", "for"),
    ("IDC Innovators", r"idc\s+innovators", ":"),
    ("GigaOm Radar", r"gigaom\s+radar|\bradar\s+for\b", "for"),
]
#: Matched to reject: customer reviews, not research.
_PEER_INSIGHTS = re.compile(r"peer\s+insights", re.I)

_RECOGNITION = re.compile(
    r"\b(?:named|recogni[sz]ed|positioned|included|mentioned|featured|listed|cited"
    r"|highlighted|identified|examines|explores|representative\s+vendor|sample\s+vendor"
    r"|honou?rable\s+mention)\b",
    re.I)
#: "a Leader", "a Major Player" — the article keeps "security leaders" out.
_POSITION = re.compile(
    r"\b(?:a|an|as\s+a|as\s+an)\s+(leader|overall\s+leader|product\s+leader|major\s+player"
    r"|representative\s+vendor|sample\s+vendor|cool\s+vendor|challenger|visionary"
    r"|niche\s+player|strong\s+performer|contender|rising\s+star)\b", re.I)
#: "new Gartner research", "IDC report", "a Forrester note" — within reach of the firm.
_RESEARCH_WORD = re.compile(r"\b(?:research|report|note|study|analysis|brief)\b", re.I)
_NEAR = 60
_YEAR = re.compile(r"\b(20\d\d)\b")
#: A title-case run: words starting with a capital or a digit, joined by
#: connectors, on one line. Stops at punctuation, quotes, a line break and
#: lower-case words.
_WORD = r"[A-Z0-9][\w&/\-]*(?:\.[\w&/\-]+)*"
_TITLE_RUN = (r"(?:" + _WORD + r"|and|of|for|the|in|to|on|&|/)"
              r"(?:[ \t]+(?:" + _WORD + r"|and|of|for|the|in|to|on|&|/))*")


def _topic_pattern(joiner: str) -> re.Pattern:
    """"Hype Cycle for Security Operations", "Innovation Insight: AI SOC
    Agents". A family is read with its own joiner only, so a vendor's blog
    title "Hype Cycle 2026: Our Take" does not become a report topic."""
    join = r"(?:" + joiner + r")" if joiner != ":" else ":"
    return re.compile(r"[ \t]*(?:™|®|\(tm\))?[ \t]*(?:,?[ \t]*20\d\d[ \t]*)?" + join
                      + r"[ \t]+(" + _TITLE_RUN + ")")
_QUOTED = re.compile(r"[\"“]([^\"”]{12,90})[\"”]")
#: A press release leads with the company and the verb: "LMNTRIX Positioned
#: as a Major Player…", "Acme Named a Leader…".
_LEAD_NAME = re.compile(
    r"^[ \t]*(" + _WORD + r"(?:[ \t]+" + _WORD + r"){0,3}?)[ \t]*,?[ \t]*(?:was|is|has\s+been|were)?[ \t]*"
    r"(?:named|recogni[sz]ed|positioned|included|mentioned|featured|listed|cited|highlighted)\b", re.I)
_AFTER_RESEARCH_WORD = re.compile(
    r"(?:research|report|note|study)[ \t]*[,:]?[ \t]*[\"“]?(" + _TITLE_RUN + ")")
_TRIM_TOPIC = re.compile(r"\s*(?:™|®|report|reports?\b|20\d\d)\s*$", re.I)
_NOISE_TOPIC_TAIL = re.compile(r"\s+(?:came|goes|is|was|has|have|and|the|for|on|of|in|to|&|/)$", re.I)

_COMPILED: List[Tuple[Dict[str, Any], List[re.Pattern]]] = [
    (firm, [re.compile(p, re.I) for p in firm.get("patterns", [])]
     + [re.compile(p) for p in firm.get("exact_patterns", [])])
    for firm in FIRMS
]
_FAMILIES: List[Tuple[str, re.Pattern, re.Pattern, str]] = [
    (label, re.compile(p, re.I), _topic_pattern(joiner), joiner) for label, p, joiner in REPORT_FAMILIES]
_JOIN_WORD = {label: (": " if joiner == ":" else f" {joiner.split('|')[0]} ")
              for label, _, joiner in REPORT_FAMILIES}


def _norm(value: str) -> str:
    # Posts dressed in mathematical-bold letters (𝗧𝗵𝗶𝗻𝗸𝗶𝗻𝗴) read as plain ASCII
    # after NFKC; the trademark signs survive and are handled by the patterns.
    return unicodedata.normalize("NFKC", value or "").replace("\xa0", " ")


def _firm_of(hay: str) -> Optional[Tuple[str, int]]:
    """The first firm named in the text, and where."""
    best = None
    for firm, patterns in _COMPILED:
        for pat in patterns:
            m = pat.search(hay)
            if m and (best is None or m.start() < best[1]):
                best = (firm["name"], m.start())
    return best


def _clean_topic(topic: str, vendor: Optional[str]) -> str:
    topic = topic.strip()
    if vendor:
        # A press release runs the report title straight into the vendor's
        # own name; the title ends where the vendor begins.
        cut = re.search(r"\s+" + re.escape(vendor) + r"\b", topic, re.I)
        if cut:
            topic = topic[:cut.start()]
    for _ in range(3):
        topic = _TRIM_TOPIC.sub("", topic)
        topic = _NOISE_TOPIC_TAIL.sub("", topic)
    return topic.strip(" ,.:;-")[:80]


def _vendor_of(row: Dict[str, Any], domain_names: Optional[Dict[str, str]] = None) -> str:
    vendors = [v.get("vendor") for v in (row.get("vendors") or []) if v.get("vendor")]
    if vendors:
        return vendors[0]
    host = _domain(row.get("uri") or "")
    for d, name in (domain_names or {}).items():
        if host == d or host.endswith("." + d):
            return name
    author = (row.get("social_meta") or {}).get("author")
    if author:
        return f"@{author}"
    # A press release from a vendor outside the registry: the company is
    # the first name in the title, before the verb.
    if row.get("article_class") == "news":
        lead = _LEAD_NAME.match(_norm(row.get("title") or ""))
        if lead and 2 <= len(lead.group(1).strip()) <= 40:
            return lead.group(1).strip(" ,:-")
    host = (urlparse(row.get("uri") or "").netloc or "").lower()
    return re.sub(r"^www\.", "", host) or "unknown"


def cite(row: Dict[str, Any], domain_names: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
    """The analyst report a record cites, or None.

    Requires a firm name and, near it, either a report family or a
    recognition verb. Returns firm, family, topic (the "for …" part),
    year, title (a quoted title when there is no family), the position
    the vendor was given, and the record's vendor, uri, date and headline.
    """
    # Title and summary on separate lines, so a report title in the headline
    # does not run into the summary's first words.
    hay = _norm(f"{row.get('title') or ''}\n{row.get('summary') or ''}")
    found = _firm_of(hay)
    if not found:
        return None
    firm, at = found
    family = None
    fam_match = topic_pat = None
    for label, pat, tpat, _ in _FAMILIES:
        # The family may be named more than once ("…in Gartner's Hype Cycle:
        # Key Insights", then "the 2025 Hype Cycle for Security Operations");
        # the mention that carries a topic is the one to read.
        found_here = list(pat.finditer(hay))
        if found_here:
            with_topic = next((m for m in found_here if tpat.match(hay, m.end())), None)
            family, fam_match, topic_pat = label, with_topic or found_here[0], tpat
            break
    if family is None and _PEER_INSIGHTS.search(hay):
        return None
    window = hay[max(0, at - _NEAR): at + _NEAR + 20]
    position = _POSITION.search(hay)
    recognised = bool(_RECOGNITION.search(window) or position or _RESEARCH_WORD.search(window))
    if family is None and not recognised:
        return None
    vendor = _vendor_of(row, domain_names)
    topic = year = title = None
    if fam_match:
        m = topic_pat.match(hay, fam_match.end())
        if m:
            topic = _clean_topic(m.group(1), vendor) or None
        around = hay[max(0, fam_match.start() - 40): fam_match.end() + 40]
        years = _YEAR.findall(around)
        year = years[0] if years else None
    else:
        after = hay[at: at + 160]
        q = _QUOTED.search(after) or _AFTER_RESEARCH_WORD.search(after)
        if q:
            title = _clean_topic(q.group(1), vendor) or None
            if title and len(title) < 12:
                title = None
        years = _YEAR.findall(hay[max(0, at - 40): at + 80])
        year = years[0] if years else None
    return {
        "firm": firm, "family": family, "topic": topic, "year": year, "title": title,
        "position": (position.group(1).title() if position else None),
        "vendor": vendor, "uri": row.get("uri"),
        "date": str(row.get("published") or "")[:10],
        "headline": row.get("title") or "",
    }


def _key(c: Dict[str, Any]) -> Optional[Tuple[str, str, str]]:
    if c["family"] and c["topic"]:
        return (c["firm"], c["family"], c["topic"].lower())
    if c["title"]:
        return (c["firm"], "", c["title"].lower())
    return None


def label_of(group: Dict[str, Any]) -> str:
    """"Gartner Hype Cycle for Security Operations, 2026"; a quoted title
    when the report has no family; the firm and family when neither is
    known."""
    firm, family, topic = group["firm"], group.get("family"), group.get("topic")
    year = f", {group['year']}" if group.get("year") else ""
    # "GigaOm Radar", "Forrester Wave": the family already names the firm.
    head = family if (family and family.lower().startswith(firm.lower())) else f"{firm} {family}"
    if family and topic:
        return f"{head}{_JOIN_WORD.get(family, ' for ')}{topic}{year}"
    if group.get("title"):
        return f"{firm}: “{group['title']}”{year}"
    return f"{head}{year}" if family else f"{firm} research{year}"


def group_citations(rows: List[Dict[str, Any]],
                    domain_names: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Citations folded by report: one group per (firm, family, topic) or
    quoted title, year-insensitive; a citation with neither is a group of
    its own. Each vendor appears once per group, with its newest record.
    Most-cited first, then newest. ``domain_names`` (domain → vendor) names
    a vendor's own blog post the way its LinkedIn posts are named."""
    groups: Dict[Any, Dict[str, Any]] = {}
    loose = 0
    for row in rows or []:
        c = cite(row, domain_names)
        if not c:
            continue
        key = _key(c)
        if key is None:
            loose += 1
            key = ("__loose__", loose)
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"item": "group", "firm": c["firm"], "family": c["family"],
                               "topic": c["topic"], "title": c["title"], "year": c["year"],
                               "headline": c["headline"], "vendors": {}, "latest": ""}
        if c["year"] and (not g["year"] or c["year"] > g["year"]):
            g["year"] = c["year"]
        prev = g["vendors"].get(c["vendor"])
        if prev is None or c["date"] > prev["date"]:
            g["vendors"][c["vendor"]] = {"vendor": c["vendor"], "position": c["position"] or
                                         (prev or {}).get("position"),
                                         "uri": c["uri"], "date": c["date"]}
        elif c["position"] and not prev.get("position"):
            prev["position"] = c["position"]
        g["latest"] = max(g["latest"], c["date"])
    # "The 2026 Hype Cycle" with no topic is read as the one 2026 Hype Cycle
    # the corpus knows, when there is exactly one; otherwise it stays apart.
    for key in [k for k in groups if k[0] == "__loose__"]:
        g = groups[key]
        if not g["family"]:
            continue
        matches = [o for k2, o in groups.items() if k2[0] != "__loose__" and k2[1] == g["family"]
                   and o["firm"] == g["firm"]
                   and (not o["year"] or not g["year"] or o["year"] == g["year"])]
        if len(matches) != 1:
            continue
        target = matches[0]
        target["year"] = target["year"] or g["year"]
        for name, v in g["vendors"].items():
            prev = target["vendors"].get(name)
            if prev is None or v["date"] > prev["date"]:
                target["vendors"][name] = v
        target["latest"] = max(target["latest"], g["latest"])
        del groups[key]
    out = []
    for g in groups.values():
        g["vendors"] = sorted(g["vendors"].values(), key=lambda v: v["date"], reverse=True)
        g["label"] = label_of(g)
        g["uri"] = g["vendors"][0]["uri"]
        out.append(g)
    out.sort(key=lambda g: (len(g["vendors"]), g["latest"]), reverse=True)
    return out


# ---------------------------------------------------------------------------
# The firms' own public pages, as feeds
# ---------------------------------------------------------------------------

DEFAULT_FEEDS: List[Dict[str, str]] = [
    {"firm": "Forrester", "url": "https://www.forrester.com/blogs/category/security-risk/feed/"},
    {"firm": "KuppingerCole", "url": "https://www.kuppingercole.com/rss"},
]
_FEED_MARK = "Analyst feed for market {id}"


def _domain(url: str) -> str:
    host = (urlparse(url or "").netloc or "").lower()
    return re.sub(r"^www\.", "", host)


def feeds(market: Dict[str, Any]) -> List[Dict[str, str]]:
    """The market's analyst feeds (``config.analyst_feeds``), or the
    defaults when none were set. Each has firm, url and domain."""
    cfg = (market.get("config") or {}).get("analyst_feeds")
    chosen = cfg if isinstance(cfg, list) else DEFAULT_FEEDS
    out = []
    for f in chosen:
        url = str((f or {}).get("url") or "").strip()
        firm = str((f or {}).get("firm") or "").strip()
        if url and firm:
            out.append({"firm": firm, "url": url, "domain": _domain(url)})
    return out


def uses_defaults(market: Dict[str, Any]) -> bool:
    return not isinstance((market.get("config") or {}).get("analyst_feeds"), list)


def analyst_domains(market: Dict[str, Any]) -> Dict[str, str]:
    """Domain → firm, for the feeds set plus every firm's home domain."""
    out = {}
    for firm in FIRMS:
        for d in firm.get("domains", ()):
            out[d] = firm["name"]
    for f in feeds(market):
        if f["domain"]:
            out[f["domain"]] = f["firm"]
    return out


def _kind_of(uri: str) -> Optional[str]:
    path = (urlparse(uri or "").path or "").lower()
    if "/events/" in path or "/event/" in path:
        return None
    if "/research/" in path or "/report/" in path:
        return "Research"
    if "/watch/" in path or "/webinar" in path or "/webcast" in path:
        return "Webinar"
    return "Blog"


def analyst_posts(rows: List[Dict[str, Any]], market: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Corpus rows from the analyst firms' own pages, newest first, each
    with ``firm`` and ``research_kind``; event listings are dropped."""
    domains = analyst_domains(market)
    out = []
    for row in rows or []:
        host = _domain(row.get("uri") or "")
        firm = next((f for d, f in domains.items() if host == d or host.endswith("." + d)), None)
        if not firm:
            continue
        kind = _kind_of(row.get("uri") or "")
        if kind is None:
            continue
        item = dict(row)
        item.update(item="post", firm=firm, research_kind=kind)
        out.append(item)
    out.sort(key=lambda r: str(r.get("published") or ""), reverse=True)
    return out


def sync_feeds(conn, market: Dict[str, Any]) -> Dict[str, int]:
    """Register the market's analyst feeds with the RSS monitor under the
    market's collection topic (the vendor blogs' path), and switch off the
    ones no longer listed. Returns counts. Commits."""
    topic = conn.execute(text(
        "SELECT config->'collection'->>'topic_name' FROM bw_markets WHERE id = :m"),
        {"m": market["id"]}).scalar() or f"Market Monitoring {market['name']}"
    mark = _FEED_MARK.format(id=market["id"])
    wanted = feeds(market)
    added = 0
    for f in wanted:
        added += conn.execute(text("""
            INSERT INTO rss_feeds (name, url, topic, description, is_active)
            SELECT :n, :u, :t, :d, TRUE
            WHERE NOT EXISTS (SELECT 1 FROM rss_feeds WHERE url = :u)
        """), {"n": f"{f['firm']} (analyst)"[:255], "u": f["url"], "t": topic[:255],
               "d": mark}).rowcount
        conn.execute(text("UPDATE rss_feeds SET is_active = TRUE WHERE url = :u AND description = :d"),
                     {"u": f["url"], "d": mark})
    dropped = conn.execute(text("""
        UPDATE rss_feeds SET is_active = FALSE
         WHERE description = :d AND is_active AND NOT (url = ANY(:urls))
    """), {"d": mark, "urls": [f["url"] for f in wanted] or [""]}).rowcount
    conn.commit()
    return {"added": int(added), "deactivated": int(dropped), "feeds": len(wanted)}
