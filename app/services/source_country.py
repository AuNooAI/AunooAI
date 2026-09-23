"""Which country a news publisher is based in.

A market topic — "Oral Health & Whole-Body Health - France" — is supposed to
be French *press*. It never was. ``keyword_groups.country`` was passed only to
collectors whose function signature happens to use the name ``country``, and
the one collector that returns non-English press, TheNewsAPI, calls it
``locale`` and then ignores it anyway. Measured 21 Sep 2026: searching
"gum disease" on ``/v1/news/all`` returns the same 190 articles and the same
sources for locale=gb, locale=us, locale=in and no locale at all. The vendor's
own source directory ignores every filter too, and leaves its ``locale`` field
empty even for obviously German papers. So no collector can tell us where a
publisher is, and every market topic has really been a *language* filter.

This module makes country a property of the publisher that we resolve once and
own, which works for every collector including our own firehose and the social
ones. Publishers repeat heavily — on sunstar 50 domains carry 90% of 25,698
articles and 250 carry 96% — so a per-domain cache costs almost nothing after
the first pass.

Resolution ladder, most trustworthy first, recorded per row in ``method`` so a
wrong answer can be found and corrected rather than guessed at again:

``manual``     an operator wrote it; never overwritten.
``tld``        a country-code top-level domain. Exact, and free. Only reaches
               about 5% of articles here because news publishers overwhelmingly
               use .com.
``mediabias``  the ``mediabias`` table, seeded from MBFC, 4,435 domains. Its
               labels are dirty ("usa (44/180 press freedom)") so they are
               normalised through ``_LABEL_ISO2``.
``model``      a cheap model, asked about the domain alone. Measured on twelve
               deliberately awkward publishers: ten right, two honest "unclear",
               zero confident wrong answers.
``model+``     the same model given two headlines in the publisher's own
               language. That resolved both remaining cases, so the ladder
               reaches twelve of twelve.

``None`` with method ``unresolved`` is a real answer and is cached, so we do not
pay for the same unanswerable domain twice. Callers decide what an unresolved
publisher means; a strict market topic excludes it.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

RESOLVER_VERSION = 1

# Model used for the two model rungs. Cheap on purpose: this is a per-domain
# question asked once, not a per-article one.
_MODEL = os.getenv("SOURCE_COUNTRY_MODEL", "nova-lite")

# Compound country-code suffixes first so the longest match wins. Generic
# suffixes (.com/.net/.org/.info/.io/.news/.tv/.biz) are deliberately absent —
# they say nothing about where a publisher sits.
_TLD_ISO2: List[Tuple[str, str]] = [
    (".com.au", "au"), (".net.au", "au"), (".co.uk", "gb"), (".org.uk", "gb"),
    (".co.za", "za"), (".co.nz", "nz"), (".co.in", "in"), (".co.jp", "jp"),
    (".co.kr", "kr"), (".com.br", "br"), (".com.mx", "mx"), (".com.ar", "ar"),
    (".com.tr", "tr"), (".co.il", "il"), (".com.sg", "sg"), (".com.hk", "hk"),
    (".ru", "ru"), (".cn", "cn"), (".de", "de"), (".fr", "fr"), (".uk", "gb"),
    (".in", "in"), (".au", "au"), (".ca", "ca"), (".ir", "ir"), (".il", "il"),
    (".ua", "ua"), (".jp", "jp"), (".kr", "kr"), (".tr", "tr"), (".pk", "pk"),
    (".za", "za"), (".es", "es"), (".it", "it"), (".nl", "nl"), (".pl", "pl"),
    (".gr", "gr"), (".ie", "ie"), (".sg", "sg"), (".nz", "nz"), (".mx", "mx"),
    (".br", "br"), (".ar", "ar"), (".cl", "cl"), (".ng", "ng"), (".ke", "ke"),
    (".eg", "eg"), (".sa", "sa"), (".ae", "ae"), (".my", "my"), (".ph", "ph"),
    (".vn", "vn"), (".th", "th"), (".hk", "hk"), (".tw", "tw"), (".lk", "lk"),
    (".bd", "bd"), (".az", "az"), (".by", "by"), (".kz", "kz"), (".am", "am"),
    (".ge", "ge"), (".pt", "pt"), (".se", "se"), (".no", "no"), (".dk", "dk"),
    (".fi", "fi"), (".be", "be"), (".ch", "ch"), (".at", "at"), (".cz", "cz"),
    (".hu", "hu"), (".ro", "ro"), (".bg", "bg"), (".rs", "rs"), (".hr", "hr"),
    (".si", "si"), (".sk", "sk"), (".lt", "lt"), (".lv", "lv"), (".ee", "ee"),
    (".is", "is"), (".lu", "lu"), (".mt", "mt"), (".cy", "cy"), (".ma", "ma"),
    (".tn", "tn"), (".dz", "dz"), (".gh", "gh"), (".tz", "tz"), (".ug", "ug"),
    (".pe", "pe"), (".ve", "ve"), (".uy", "uy"), (".py", "py"), (".bo", "bo"),
    (".ec", "ec"), (".cr", "cr"), (".pa", "pa"), (".do", "do"), (".gt", "gt"),
    (".id", "id"), (".pk", "pk"), (".np", "np"), (".qa", "qa"), (".kw", "kw"),
    (".jo", "jo"), (".lb", "lb"), (".om", "om"), (".bh", "bh"),
]

# ``mediabias.country`` holds free text of varying case with trailing
# annotations. Map the labels that actually occur onto ISO 3166-1 alpha-2.
_LABEL_ISO2: Dict[str, str] = {
    "usa": "us", "us": "us", "united states": "us",
    "united states of america": "us",
    "uk": "gb", "united kingdom": "gb", "great britain": "gb", "england": "gb",
    "canada": "ca", "australia": "au", "germany": "de", "france": "fr",
    "india": "in", "russia": "ru", "russian federation": "ru", "china": "cn",
    "japan": "jp", "south korea": "kr", "korea, republic of": "kr",
    "iran": "ir", "israel": "il", "ukraine": "ua", "turkey": "tr",
    "pakistan": "pk", "south africa": "za", "spain": "es", "italy": "it",
    "netherlands": "nl", "poland": "pl", "greece": "gr", "ireland": "ie",
    "singapore": "sg", "new zealand": "nz", "mexico": "mx", "brazil": "br",
    "argentina": "ar", "chile": "cl", "colombia": "co", "peru": "pe",
    "venezuela": "ve", "uruguay": "uy", "switzerland": "ch", "austria": "at",
    "belgium": "be", "portugal": "pt", "sweden": "se", "norway": "no",
    "denmark": "dk", "finland": "fi", "czechia": "cz", "czech republic": "cz",
    "hungary": "hu", "romania": "ro", "bulgaria": "bg", "croatia": "hr",
    "serbia": "rs", "slovenia": "si", "slovakia": "sk", "lithuania": "lt",
    "latvia": "lv", "estonia": "ee", "iceland": "is", "luxembourg": "lu",
    "malta": "mt", "cyprus": "cy", "egypt": "eg", "morocco": "ma",
    "nigeria": "ng", "kenya": "ke", "saudi arabia": "sa", "qatar": "qa",
    "united arab emirates": "ae", "uae": "ae", "lebanon": "lb",
    "jordan": "jo", "kuwait": "kw", "malaysia": "my", "philippines": "ph",
    "indonesia": "id", "thailand": "th", "vietnam": "vn", "taiwan": "tw",
    "hong kong": "hk", "bangladesh": "bd", "sri lanka": "lk", "nepal": "np",
    "belarus": "by", "kazakhstan": "kz", "azerbaijan": "az", "armenia": "am",
    "georgia": "ge",
}

_GENERIC_SUFFIXES = (
    ".com", ".net", ".org", ".info", ".io", ".news", ".tv", ".biz", ".co",
    ".app", ".online", ".site", ".xyz", ".me", ".ai", ".edu", ".gov", ".int",
)


# ── domain handling ───────────────────────────────────────────────────────

def registered_domain(value: Optional[str]) -> Optional[str]:
    """Reduce a URL or host to a lower-case registrable domain, or None.

    ``news_source`` is NOT reliably a domain — collectors put publisher names
    in it ("The Guardian") as well as hosts — so callers should pass the
    article URI and fall back to ``news_source`` only when it looks like a
    host. See :func:`domain_for_article`.
    """
    if not value:
        return None
    v = value.strip().lower()
    if not v:
        return None
    if "://" in v:
        v = urlparse(v).netloc or ""
    v = v.split("/")[0].split("?")[0].split("@")[-1].split(":")[0]
    if v.startswith("www."):
        v = v[4:]
    if "." not in v or " " in v:
        return None
    return v or None


def domain_for_article(uri: Optional[str], news_source: Optional[str] = None) -> Optional[str]:
    """The publisher domain for an article. Prefers the URI host."""
    return registered_domain(uri) or registered_domain(news_source)


def country_from_tld(domain: Optional[str]) -> Optional[str]:
    """ISO2 from a country-code suffix, or None for a generic one."""
    d = registered_domain(domain) if domain else None
    if not d:
        return None
    for suffix in _GENERIC_SUFFIXES:
        if d.endswith(suffix):
            # ``.co.uk`` ends with ``.uk`` not ``.co``; only bail when the
            # generic suffix really is the last label.
            if d.endswith(".co.uk") or d.endswith(".co.za") or d.endswith(".co.nz") \
               or d.endswith(".co.in") or d.endswith(".co.jp") or d.endswith(".co.kr") \
               or d.endswith(".co.il"):
                break
            return None
    for suffix, iso2 in _TLD_ISO2:
        if d.endswith(suffix):
            return iso2
    return None


def normalize_label(raw: Optional[str]) -> Optional[str]:
    """ISO2 from a free-text country label, dropping annotations and unknowns."""
    if not raw:
        return None
    s = raw.strip().lower()
    if not s or s == "unknown":
        return None
    paren = s.find("(")
    if paren > 0:
        s = s[:paren].strip()
    s = s.strip(" .,")
    if len(s) == 2 and s.isalpha():
        return s
    return _LABEL_ISO2.get(s)


# ── the registry ──────────────────────────────────────────────────────────

def _fetch_cached(db, domains: Sequence[str]) -> Dict[str, Tuple[Optional[str], str]]:
    if not domains:
        return {}
    try:
        from sqlalchemy import text as sa_text
        rows = db.facade._execute_with_rollback(sa_text(
            "SELECT domain, country, method FROM news_source_countries "
            "WHERE domain = ANY(:doms)"
        ), {"doms": list(domains)}).fetchall()
    except Exception as e:
        logger.warning("source_country: cache read failed: %s", e)
        return {}
    out = {}
    for r in rows:
        d = dict(r._mapping)
        out[d["domain"]] = (d.get("country"), d.get("method") or "unresolved")
    return out


def _store(db, domain: str, country: Optional[str], method: str) -> None:
    try:
        from sqlalchemy import text as sa_text
        db.facade._execute_with_rollback(sa_text("""
            INSERT INTO news_source_countries (domain, country, method, resolver_version, resolved_at)
            VALUES (:d, :c, :m, :v, NOW())
            ON CONFLICT (domain) DO UPDATE
               SET country = EXCLUDED.country,
                   method = EXCLUDED.method,
                   resolver_version = EXCLUDED.resolver_version,
                   resolved_at = NOW()
             WHERE news_source_countries.method <> 'manual'
        """), {"d": domain, "c": country, "m": method, "v": RESOLVER_VERSION})
    except Exception as e:
        logger.warning("source_country: cache write failed for %s: %s", domain, e)


def _from_mediabias(db, domains: Sequence[str]) -> Dict[str, str]:
    """ISO2 per domain from the MBFC-seeded ``mediabias`` table."""
    if not domains:
        return {}
    try:
        from sqlalchemy import text as sa_text
        rows = db.facade._execute_with_rollback(sa_text(
            "SELECT source, country FROM mediabias WHERE source = ANY(:doms)"
        ), {"doms": list(domains)}).fetchall()
    except Exception as e:
        logger.debug("source_country: mediabias lookup failed: %s", e)
        return {}
    out = {}
    for r in rows:
        d = dict(r._mapping)
        iso2 = normalize_label(d.get("country"))
        if iso2:
            out[d["source"]] = iso2
    return out


def _sample_titles(db, domain: str, limit: int = 2) -> List[str]:
    """A couple of headlines in the publisher's own language."""
    try:
        from sqlalchemy import text as sa_text
        rows = db.facade._execute_with_rollback(sa_text("""
            SELECT COALESCE(original_title, title) AS ti
            FROM articles
            WHERE lower(news_source) = :d OR uri ILIKE :like
            LIMIT :n
        """), {"d": domain, "like": "%//" + domain + "%", "n": limit}).fetchall()
        return [dict(r._mapping)["ti"][:110] for r in rows
                if dict(r._mapping).get("ti")]
    except Exception:
        return []


def _ask_model(entries: List[Tuple[str, List[str]]]) -> Dict[str, Optional[str]]:
    """Ask the model for ISO2 per domain. ``entries`` is (domain, headlines).

    Returns only codes the model was willing to commit to; ``XX`` and anything
    unparseable come back as None, which is the behaviour we want — the
    measured failure mode is abstention, not a confident wrong country.
    """
    if not entries:
        return {}
    lines = []
    for dom, titles in entries:
        if titles:
            lines.append("%s\n   headlines: %s" % (dom, " | ".join(titles)))
        else:
            lines.append(dom)
    prompt = (
        "For each news publisher domain below, give the ISO 3166-1 alpha-2 code "
        "of the country the publication is BASED IN and primarily serves. Where "
        "sample headlines are given they are in the publisher's own language and "
        "should help. Answer XX only if it is genuinely unclear — a wrong country "
        "is far worse than XX.\n"
        "Return ONLY a JSON object mapping each domain to its code.\n\n"
        + "\n".join(lines)
    )
    try:
        from app.ai_models import get_ai_model
        model = get_ai_model(_MODEL)
        raw = model.generate_response([{"role": "user", "content": prompt}])
        if not isinstance(raw, str):
            raw = str(raw)
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return {}
        data = json.loads(raw[start:end + 1])
    except Exception as e:
        logger.warning("source_country: model call failed: %s", e)
        return {}
    out: Dict[str, Optional[str]] = {}
    for dom, _ in entries:
        code = str(data.get(dom) or "").strip().lower()
        out[dom] = code if (len(code) == 2 and code.isalpha() and code != "xx") else None
    return out


def countries_for_domains(db, domains: Iterable[str], *,
                          use_model: bool = True,
                          batch: int = 20) -> Dict[str, Optional[str]]:
    """Resolve many domains at once, reading and filling the registry.

    Returns ``{domain: iso2 or None}``. A None is a cached, deliberate
    "we could not tell", not a transient miss.
    """
    wanted = []
    for d in domains:
        rd = registered_domain(d)
        if rd and rd not in wanted:
            wanted.append(rd)
    if not wanted:
        return {}

    resolved: Dict[str, Optional[str]] = {}
    cached = _fetch_cached(db, wanted)
    todo = []
    for d in wanted:
        if d in cached:
            resolved[d] = cached[d][0]
        else:
            todo.append(d)

    # Rung 1: the country-code suffix. Free and exact.
    still = []
    for d in todo:
        iso2 = country_from_tld(d)
        if iso2:
            resolved[d] = iso2
            _store(db, d, iso2, "tld")
        else:
            still.append(d)

    # Rung 2: the MBFC-seeded table we already ship.
    if still:
        mb = _from_mediabias(db, still)
        rest = []
        for d in still:
            if d in mb:
                resolved[d] = mb[d]
                _store(db, d, mb[d], "mediabias")
            else:
                rest.append(d)
        still = rest

    if not still or not use_model:
        for d in still:
            resolved[d] = None
        return resolved

    # Rung 3: the model on the domain alone.
    unclear = []
    for i in range(0, len(still), batch):
        chunk = still[i:i + batch]
        got = _ask_model([(d, []) for d in chunk])
        for d in chunk:
            iso2 = got.get(d)
            if iso2:
                resolved[d] = iso2
                _store(db, d, iso2, "model")
            else:
                unclear.append(d)

    # Rung 4: the model again, with headlines in the publisher's own language.
    for i in range(0, len(unclear), batch):
        chunk = unclear[i:i + batch]
        entries = [(d, _sample_titles(db, d)) for d in chunk]
        got = _ask_model([e for e in entries if e[1]])
        for d in chunk:
            iso2 = got.get(d)
            resolved[d] = iso2
            _store(db, d, iso2, "model+" if iso2 else "unresolved")

    return resolved


def countries_with_method(db, domains: Iterable[str], *,
                          use_model: bool = True) -> Dict[str, Tuple[Optional[str], str]]:
    """Resolve many domains and say which rung of the ladder answered.

    Returns ``{domain: (iso2 or None, method)}``. ``countries_for_domains``
    writes every domain it touches into the registry, so the method comes back
    from one cache read rather than being threaded back through each rung. A
    caller that stamps the answer on a row wants the method stored with it,
    because that is what makes a wrong code findable later.
    """
    resolved = countries_for_domains(db, domains, use_model=use_model)
    if not resolved:
        return {}
    cached = _fetch_cached(db, list(resolved))
    out = {}
    for d, c in resolved.items():
        if d in cached:
            out[d] = (c, cached[d][1])
        else:
            # The registry write or this re-read failed quietly. "unresolved"
            # would mislabel a real answer, so say only that we do not know
            # which rung produced it.
            out[d] = (c, "unknown" if c else "unresolved")
    return out


def country_for_domain(db, domain: Optional[str], *, use_model: bool = True) -> Optional[str]:
    """ISO2 for one publisher domain, or None if we could not tell."""
    rd = registered_domain(domain)
    if not rd:
        return None
    return countries_for_domains(db, [rd], use_model=use_model).get(rd)
