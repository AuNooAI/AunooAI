"""The effective brand profile, and the deterministic checks that read it.

One profile per enabled ``bw_brands`` row drives collection, mention detection
and every model route for that brand (docs/BRAND_RELEVANCE_SPEC.md, "Brand
identity and collection"). It is built from fields the row already carries:

``display_name``, ``brand_keywords``, ``product_keywords``    names and products
``config.aliases``, ``config.original_names``                  extra and original-language names
``config.mention_context``                                     words that must sit near a mention
``config.ambiguous_aliases``                                   names that always need that context
``config.exclude_context``                                     words that mark a same-name subject
``config.news_keyword_excludes``                               phrases for other entities of the same name
``config.owned_domains`` + ``bw_vendor_identifiers`` domains   the brand's own publishing
``config.non_press_domains``                                   sites whose pages are never this brand's press
``config.group_ids``                                           explicit topic-group scope (optional)

Nothing here calls a model or writes to the database. Each function is pure
apart from the two loaders, so tests need no database.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

POLICY_VERSION = "brand-coverage-1"
_WINDOW = 200          # characters either side of a mention that count as its context
_EXTRACT = 140         # characters of evidence kept with a decision
_SHORT_ALIAS = 4       # a Latin alias this short needs company context
_LEGACY_OWNED_PREFIXES = ("owned:", "vendor:")


# ---------------------------------------------------------------------------
# Text normalisation and matching
# ---------------------------------------------------------------------------

def nfkc(text: Any) -> str:
    return unicodedata.normalize("NFKC", str(text or ""))


def norm(text: Any) -> str:
    """NFKC then lower case, the same for aliases and article text, so
    full-width Latin, ligatures and case differences compare equal."""
    return nfkc(text).lower()


def _is_spaced_script(alias: str) -> bool:
    """True when an alias is written in a script that separates words with
    spaces (Latin, Cyrillic, Greek...). Japanese, Chinese and Thai do not, so
    word boundaries mean nothing there and the alias matches as a substring."""
    for ch in alias:
        if ch.isalpha() and not ch.isascii():
            name = unicodedata.name(ch, "")
            if any(s in name for s in ("CJK", "HIRAGANA", "KATAKANA", "HANGUL", "THAI", "LAO",
                                       "KHMER", "MYANMAR", "TIBETAN")):
                return False
    return True


# Letters and digits of the scripts that separate words with spaces. A Latin
# name is part of a longer word only when one of these touches it: "app"
# inside "happens" is not the name, but "Haleon" in "Haleonジャパン" is, because
# Japanese runs words together.
_WORDCHAR = r"0-9A-Za-z\u00C0-\u024F\u0370-\u03FF\u0400-\u04FF"
_LB, _RB = rf"(?<![{_WORDCHAR}])", rf"(?![{_WORDCHAR}])"


def _alias_pattern(alias: str) -> Optional[re.Pattern]:
    a = norm(alias).strip()
    if not a:
        return None
    esc = re.escape(a)
    if _is_spaced_script(a):
        return re.compile(rf"{_LB}{esc}{_RB}")
    return re.compile(esc)


def _terms_pattern(terms: Iterable[str]) -> Optional[re.Pattern]:
    """Alternation of context or exclusion words. A trailing ``*`` is a stem."""
    parts = []
    for t in terms or ():
        t = norm(t).strip()
        if not t:
            continue
        stem = t.endswith("*")
        esc = re.escape(t.rstrip("*"))
        if not _is_spaced_script(t):
            parts.append(esc)
        elif stem:
            parts.append(rf"{_LB}{esc}")
        else:
            parts.append(rf"{_LB}{esc}{_RB}")
    if not parts:
        return None
    parts.sort(key=len, reverse=True)
    return re.compile("|".join(parts))


def _as_list(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        try:
            return _as_list(json.loads(v))
        except ValueError:
            return [v.strip()]
    return []


def host_of(url: str) -> str:
    try:
        h = urlparse(url or "").netloc.lower()
    except ValueError:
        return ""
    return h.split("@")[-1].split(":")[0].strip(".").removeprefix("www.")


def _domain_of(value: str) -> str:
    v = (value or "").strip().lower()
    if "://" in v:
        return host_of(v)
    v = v.split("/")[0].strip(".").removeprefix("www.")
    return v if "." in v and " " not in v else ""


def host_in(host: str, domains: Iterable[str]) -> bool:
    """Domain-boundary match: example.com covers news.example.com, never
    badexample.com or example.com.evil.net."""
    host = (host or "").lower().strip(".")
    if not host:
        return False
    for d in domains or ():
        d = (d or "").lower().strip(".").removeprefix("www.")
        if d and (host == d or host.endswith("." + d)):
            return True
    return False


# ---------------------------------------------------------------------------
# The profile
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BrandProfile:
    brand_id: int
    slug: str
    display_name: str
    names: Tuple[str, ...]
    products: Tuple[str, ...]
    context: Tuple[str, ...]
    ambiguous: Tuple[str, ...]
    exclude_context: Tuple[str, ...]
    collision_phrases: Tuple[str, ...]
    owned_domains: Tuple[str, ...]
    non_press_domains: Tuple[str, ...]
    group_ids: Tuple[int, ...] = ()
    version: str = ""
    _patterns: Dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def aliases(self) -> Tuple[str, ...]:
        return tuple(dict.fromkeys((*self.names, *self.products)))

    def collection_terms(self) -> List[str]:
        """Names and products a collector can search for safely: every alias
        except short or ambiguous ones, which pull unrelated pages unless the
        search engine can apply company context."""
        out = []
        amb = {norm(a) for a in self.ambiguous}
        for a in self.aliases:
            n = norm(a)
            if n in amb or (_is_spaced_script(n) and len(n.replace(" ", "")) <= _SHORT_ALIAS):
                continue
            out.append(a)
        return out

    def needs_context(self, alias: str) -> bool:
        n = norm(alias)
        if self.context:
            return True
        if n in {norm(a) for a in self.ambiguous}:
            return True
        return _is_spaced_script(n) and len(n.replace(" ", "")) <= _SHORT_ALIAS

    def patterns(self) -> Dict[str, Any]:
        if not self._patterns:
            self._patterns["aliases"] = [(a, p) for a in sorted(self.aliases, key=len, reverse=True)
                                         if (p := _alias_pattern(a)) is not None]
            self._patterns["context"] = _terms_pattern(self.context)
            self._patterns["exclude"] = _terms_pattern(self.exclude_context)
        return self._patterns


def _version(payload: Dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def build_profile(row: Dict[str, Any], registry_domains: Sequence[str] = ()) -> BrandProfile:
    """A profile from a ``bw_brands`` row (as a dict) and the brand's registry
    domains. Explicit config wins; nothing here overwrites a tenant rule."""
    cfg = row.get("config") or {}
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except ValueError:
            cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    display = (row.get("display_name") or row.get("name") or "").strip()
    names = [display, *_as_list(row.get("brand_keywords")), *_as_list(cfg.get("aliases")),
             *_as_list(cfg.get("original_names"))]
    products = _as_list(row.get("product_keywords"))
    owned = [d for d in (_domain_of(x) for x in [*_as_list(cfg.get("owned_domains")), *registry_domains]) if d]
    non_press = [d for d in (_domain_of(x) for x in _as_list(cfg.get("non_press_domains"))) if d]
    groups = []
    for g in _as_list(cfg.get("group_ids")):
        try:
            groups.append(int(g))
        except ValueError:
            pass

    def uniq(xs):
        seen, out = set(), []
        for x in xs:
            k = norm(x).strip()
            if k and k not in seen:
                seen.add(k)
                out.append(x.strip())
        return tuple(out)

    payload = {
        "policy": POLICY_VERSION,
        "id": int(row.get("id") or 0),
        "names": sorted(norm(x) for x in uniq(names)),
        "products": sorted(norm(x) for x in uniq(products)),
        "context": sorted(norm(x) for x in uniq(_as_list(cfg.get("mention_context")))),
        "ambiguous": sorted(norm(x) for x in uniq(_as_list(cfg.get("ambiguous_aliases")))),
        "exclude": sorted(norm(x) for x in uniq(_as_list(cfg.get("exclude_context")))),
        "collisions": sorted(norm(x) for x in uniq(_as_list(cfg.get("news_keyword_excludes")))),
        "owned": sorted(set(owned)),
        "non_press": sorted(set(non_press)),
        "groups": sorted(set(groups)),
    }
    return BrandProfile(
        brand_id=int(row.get("id") or 0),
        slug=(row.get("name") or "").strip(),
        display_name=display,
        names=uniq(names),
        products=uniq(products),
        context=uniq(_as_list(cfg.get("mention_context"))),
        ambiguous=uniq(_as_list(cfg.get("ambiguous_aliases"))),
        exclude_context=uniq(_as_list(cfg.get("exclude_context"))),
        collision_phrases=uniq(_as_list(cfg.get("news_keyword_excludes"))),
        owned_domains=tuple(sorted(set(owned))),
        non_press_domains=tuple(sorted(set(non_press))),
        group_ids=tuple(sorted(set(groups))),
        version=_version(payload),
    )


# ---------------------------------------------------------------------------
# Resolving a topic to one profile
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProfileResolution:
    profile: Optional[BrandProfile]
    brand_topic: bool          # the topic is a brand topic by name
    error: Optional[str] = None  # visible configuration error; the candidate defers


def brand_name_for_topic(topic: Optional[str]) -> Optional[str]:
    try:
        from app.services.hybrid_relevance_service import brand_name_from_topic
        return brand_name_from_topic(topic)
    except Exception:  # noqa: BLE001 - keep this module importable on its own
        t = (topic or "").strip()
        m = re.match(r"^Brand Monitoring\s+(.+)$", t, re.I) or re.match(r"^(.+?)\s+-\s+Brand Watch$", t, re.I)
        return m.group(1).strip() if m else None


def resolve(rows: Sequence[Dict[str, Any]], topic: str, group_id: Optional[int] = None,
            registry: Optional[Dict[int, List[str]]] = None) -> ProfileResolution:
    """Pick the one enabled profile a brand topic means.

    An explicit ``config.group_ids`` naming the group wins. Otherwise the
    topic's brand name must equal exactly one enabled row's display name or
    slug. Two matches are a configuration error: the candidate stays
    undecided and nothing is merged or picked first.
    """
    name = brand_name_for_topic(topic)
    if not name:
        return ProfileResolution(None, False)
    enabled = [r for r in rows if r.get("enabled", True)]
    if group_id is not None:
        pinned = []
        for r in enabled:
            cfg = r.get("config") or {}
            if isinstance(cfg, str):
                try:
                    cfg = json.loads(cfg)
                except ValueError:
                    cfg = {}
            if isinstance(cfg, dict) and str(group_id) in {str(g) for g in _as_list(cfg.get("group_ids"))}:
                pinned.append(r)
        if len(pinned) == 1:
            r = pinned[0]
            return ProfileResolution(build_profile(r, (registry or {}).get(int(r["id"]), ())), True)
        if len(pinned) > 1:
            return ProfileResolution(None, True, f"group {group_id} is pinned to {len(pinned)} enabled brands")
    key = norm(name).strip()
    hits = [r for r in enabled
            if norm(r.get("display_name")).strip() == key or norm(r.get("name")).strip() == key]
    if len(hits) == 1:
        r = hits[0]
        return ProfileResolution(build_profile(r, (registry or {}).get(int(r["id"]), ())), True)
    if len(hits) > 1:
        ids = ", ".join(str(r.get("id")) for r in hits)
        return ProfileResolution(None, True, f"topic '{topic}' matches {len(hits)} enabled brands (ids {ids})")
    return ProfileResolution(None, True)


def load_rows(conn) -> Tuple[List[Dict[str, Any]], Dict[int, List[str]]]:
    """Enabled brand rows and each brand's registry domains. The registry
    table exists only on sites with Entity Intelligence; its absence is fine."""
    from sqlalchemy import text
    rows = [dict(r) for r in conn.execute(text("""
        SELECT id, name, display_name, brand_keywords, product_keywords, config, enabled
          FROM bw_brands WHERE enabled
    """)).mappings().all()]
    registry: Dict[int, List[str]] = {}
    try:
        with conn.begin_nested():
            for r in conn.execute(text("""
                SELECT brand_id, normalized_value FROM bw_vendor_identifiers
                 WHERE kind = 'domain' AND valid_to IS NULL
            """)).mappings():
                registry.setdefault(int(r["brand_id"]), []).append(r["normalized_value"])
    except Exception as e:  # noqa: BLE001 - table absent on most sites
        logger.debug("brand_profile: no vendor registry (%s)", e)
    return rows, registry


def resolve_for_topic(conn, topic: str, group_id: Optional[int] = None) -> ProfileResolution:
    rows, registry = load_rows(conn)
    return resolve(rows, topic, group_id, registry)


# ---------------------------------------------------------------------------
# Deterministic checks
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Mention:
    """Where and how the brand is named.

    status:
      ``title``      a verified mention in a headline field
      ``body``       verified only in the summary or text
      ``same_name``  every mention sits beside a same-name subject (or a listed collision phrase)
      ``ambiguous``  a mention has both company context and same-name evidence: identity unresolved
      ``weak``       named, but without the company context this alias needs
      ``none``       not named
    """
    status: str
    alias: str = ""
    field: str = ""
    extract: str = ""

    @property
    def verified(self) -> bool:
        return self.status in ("title", "body")


_FIELDS = (("original_title", "title"), ("title", "title"),
           ("original_summary", "summary"), ("summary", "summary"),
           ("content", "text"), ("raw", "text"))


def detect_mention(profile: BrandProfile, article: Dict[str, Any]) -> Mention:
    """Verified company or product mention in the article's own text.

    A provider's claimed match is not evidence: only the stored title,
    summary and text are read. Context and exclusion words are looked for in a
    window around each mention across the whole text, so a headline mention is
    confirmed by the paragraph under it.
    """
    raw_parts: List[str] = []
    low_parts: List[str] = []
    spans: List[Tuple[int, int, str]] = []
    seen_text = set()
    pos = 0
    for key, label in _FIELDS:
        v = article.get(key)
        if not v:
            continue
        raw = nfkc(v)
        low = raw.lower()
        if len(low) != len(raw):          # rare characters whose lower case changes length
            raw = low
        if low in seen_text:
            continue
        seen_text.add(low)
        spans.append((pos, pos + len(low), label))
        raw_parts.append(raw + "\n")
        low_parts.append(low + "\n")
        pos += len(low) + 1
    if not spans:
        return Mention("none")
    raw_blob, blob = "".join(raw_parts), "".join(low_parts)

    def field_at(i: int) -> str:
        for a, b, label in spans:
            if a <= i < b:
                return label
        return "text"

    pats = profile.patterns()
    excl, ctx = pats["exclude"], pats["context"]
    collisions = [norm(c).strip() for c in profile.collision_phrases if norm(c).strip()]
    best: Optional[Mention] = None
    seen_same = seen_amb = seen_weak = None
    for alias, pat in pats["aliases"]:
        multiword_latin = " " in alias.strip() and _is_spaced_script(alias)
        for m in pat.finditer(blob):
            # A multi-word Latin name written all in lower case is the phrase,
            # not the company ("for weight watchers" = dieters). A one-word
            # name counts in any case, as people write it in posts.
            if multiword_latin and raw_blob[m.start():m.end()].islower():
                continue
            f = field_at(m.start())
            lo, hi = max(0, m.start() - _WINDOW), min(len(blob), m.end() + _WINDOW)
            window = blob[lo:hi]
            s_lo, s_hi = max(0, m.start() - _EXTRACT // 2), min(len(blob), m.end() + _EXTRACT // 2)
            extract = re.sub(r"\s+", " ", raw_blob[s_lo:s_hi]).strip()
            in_collision = any(c in window for c in collisions)
            has_excl = in_collision or (excl is not None and excl.search(window) is not None)
            has_ctx = ctx is not None and ctx.search(window) is not None
            if has_excl and has_ctx and not in_collision:
                seen_amb = seen_amb or Mention("ambiguous", alias, f, extract)
                continue
            if has_excl:
                seen_same = seen_same or Mention("same_name", alias, f, extract)
                continue
            if profile.needs_context(alias) and not has_ctx:
                seen_weak = seen_weak or Mention("weak", alias, f, extract)
                continue
            cand = Mention("title" if f == "title" else "body", alias, f, extract)
            if cand.status == "title":
                return cand
            best = best or cand
    if best:
        return best
    return seen_amb or seen_same or seen_weak or Mention("none")


def source_relation(profile: BrandProfile, article: Dict[str, Any]) -> Tuple[str, str]:
    """('owned' | 'independent' | 'unknown', why) relative to this brand.

    The brand's own domains and registry identifiers decide. A legacy owned
    tag (``owned:<domain>`` / ``vendor:<name>`` in ``bias_source``) counts for
    this brand only when its domain is one of this brand's; a page another
    company owns is independent coverage of this one. A page with no readable
    host is unknown.
    """
    url = article.get("uri") or article.get("url") or ""
    host = host_of(url)
    src_dom = _domain_of(article.get("news_source") or "")
    if host_in(host, profile.owned_domains) or host_in(src_dom, profile.owned_domains):
        return "owned", f"published on {host or src_dom}, one of {profile.display_name}'s own sites"
    tag = (article.get("bias_source") or "").strip().lower()
    for pfx in _LEGACY_OWNED_PREFIXES:
        if tag.startswith(pfx):
            tagged = _domain_of(tag[len(pfx):])
            if tagged and host_in(tagged, profile.owned_domains):
                return "owned", f"tagged {tag}, one of {profile.display_name}'s own sites"
            if pfx == "vendor:" and norm(tag[len(pfx):]).strip() in {norm(n) for n in profile.names}:
                return "owned", f"tagged {tag}"
    if host or src_dom:
        return "independent", ""
    return "unknown", "no publisher domain to classify"


# Automated valuation pages ("CL DCF Analysis: Intrinsic Value $44 vs Price $88",
# "CL Looks 8.5% Undervalued on GF Value"): generated per ticker, never reporting.
_VALUATION_TITLE = re.compile(
    r"(\bDCF Analysis\b|\bIntrinsic Value\b.*\bvs\.? Price\b|\b(?:Under|Over)valued on GF Value\b"
    r"|\bGF Value\b.*\b(?:Under|Over)valued\b|\bFair Value Estimate\b.*\bTicker\b)",
    re.I,
)


def valuation_page_reason(url: str, title: str) -> Optional[str]:
    t = title or ""
    if _VALUATION_TITLE.search(t):
        return "automated valuation page"
    return None


def exclusion(profile: BrandProfile, article: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """(kind, why) when an existing source or content rule takes the article
    out of brand coverage, else None. Kinds: non_press, deal_listing,
    valuation_page."""
    url = article.get("uri") or article.get("url") or ""
    host = host_of(url)
    src = _domain_of(article.get("news_source") or "")
    if profile.non_press_domains and (host_in(host, profile.non_press_domains)
                                      or host_in(src, profile.non_press_domains)):
        return "non_press", f"{host or src} is listed as a site whose pages are not {profile.display_name}'s press"
    title = article.get("original_title") or article.get("title") or ""
    try:
        from app.services.deal_listing import deal_listing_reason
        deal = deal_listing_reason(url, title) or deal_listing_reason(url, article.get("title") or "")
    except Exception:  # noqa: BLE001 - the rule module is optional on older sites
        deal = None
    if deal:
        return "deal_listing", f"retail deal listing ({deal})"
    val = valuation_page_reason(url, article.get("title") or title)
    if val:
        return "valuation_page", val
    return None


def evidence_quality(article: Dict[str, Any]) -> str:
    """'full' (body text), 'summary' or 'title_only' (no text beyond the title)."""
    if (article.get("content") or article.get("raw") or "").strip():
        return "full"
    summ = (article.get("summary") or article.get("original_summary") or "").strip()
    title = (article.get("title") or "").strip()
    if summ and norm(summ).strip() != norm(title).strip():
        return "summary"
    return "title_only"
