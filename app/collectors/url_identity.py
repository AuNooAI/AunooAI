"""Article identity: which URL variants are the same page, and which record
types must not be matched by URL at all.

Two things live here.

1. A tracking-parameter registry (work package 30). A global list of
   parameters that never identify a page (``utm_*``, ``fbclid`` and the
   other ad and email click ids) plus per-host additions that are only
   tracking on that publisher: Seeking Alpha's ``feed_item_type``, the
   BBC's ``at_medium`` and ``at_campaign``. Anything not in the registry is
   kept, so two streamingmedia articles that differ only in ``ArticleID``
   stay two articles. The registry is data with a version; the version is
   written next to every alias so a later registry change is visible on the
   rows it did not apply to.

2. Identity selection by record type (work package 4). A social post is
   identified by platform and post id, a scholarly record by its DOI, a feed
   entry by feed and GUID, and only ordinary news by its canonical URL.
   Calendar occurrences and social posts legitimately share a landing URL,
   so URL equality must never override those keys.

Normalisation is deliberately conservative: lower-case the scheme and host,
drop a default port and the fragment, strip registry parameters. It does not
drop arbitrary parameters, force ``http`` and ``https`` together, or strip
a trailing slash.

Identical in both repositories; import nothing from either application.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

#: Bump when the built-in lists change. A file loaded from
#: ``URL_TRACKING_REGISTRY_PATH`` carries its own version and wins.
BUILTIN_REGISTRY: Dict[str, Any] = {
    "version": "2026.10.01-1",
    # Exact names, any host.
    "global": [
        "fbclid", "gclid", "dclid", "gbraid", "wbraid", "msclkid", "yclid",
        "twclid", "ttclid", "igshid", "mc_cid", "mc_eid", "mkt_tok",
        "_hsenc", "_hsmi", "hsctatracking", "vero_id", "vero_conv",
        "oly_anon_id", "oly_enc_id", "rb_clickid", "s_cid", "_openstat",
        "ito", "ocid", "taid", "ncid", "cmpid", "sr_share", "ref_src",
        "guccounter", "guce_referrer", "guce_referrer_sig",
    ],
    # Name prefixes, any host.
    "global_prefixes": ["utm_", "itm_", "pk_", "piwik_", "matomo_", "mtm_"],
    # Per publisher. Host matching includes subdomains.
    "hosts": {
        "seekingalpha.com": ["feed_item_type", "source", "utm_source"],
        "bbc.co.uk": ["at_medium", "at_campaign", "at_bbc_team", "at_link_origin",
                      "at_link_type", "at_link_id", "at_format", "at_ptr_name",
                      "at_campaign_type", "xtor"],
        "bbc.com": ["at_medium", "at_campaign", "at_bbc_team", "at_link_origin",
                    "at_link_type", "at_link_id", "at_format", "at_ptr_name",
                    "at_campaign_type", "xtor"],
        "zacks.com": ["cid"],
        "reuters.com": ["taid"],
        "theguardian.com": ["cmp"],
        "nytimes.com": ["smid", "smtyp", "partner", "emc"],
        "youtube.com": ["feature", "si"],
        "youtu.be": ["si"],
    },
}


@dataclass(frozen=True)
class Registry:
    version: str
    global_params: frozenset
    global_prefixes: Tuple[str, ...]
    hosts: Dict[str, frozenset]

    def is_tracking(self, host: str, name: str) -> bool:
        n = name.lower()
        if n in self.global_params:
            return True
        if any(n.startswith(p) for p in self.global_prefixes):
            return True
        h = (host or "").lower()
        if h.startswith("www."):
            h = h[4:]
        # Walk the host and its parent domains: news.bbc.co.uk → bbc.co.uk.
        parts = h.split(".")
        for i in range(len(parts) - 1):
            candidate = ".".join(parts[i:])
            params = self.hosts.get(candidate)
            if params and n in params:
                return True
        return False


def _build(data: Dict[str, Any]) -> Registry:
    return Registry(
        version=str(data.get("version") or "unversioned"),
        global_params=frozenset(p.lower() for p in data.get("global", [])),
        global_prefixes=tuple(p.lower() for p in data.get("global_prefixes", [])),
        hosts={h.lower(): frozenset(p.lower() for p in ps)
               for h, ps in (data.get("hosts") or {}).items()},
    )


_registry_cache: Optional[Tuple[str, float, Registry]] = None


def load_registry() -> Registry:
    """The active registry: the file named by ``URL_TRACKING_REGISTRY_PATH``
    when it exists and parses, otherwise the built-in one. The file is
    re-read when its mtime changes, so a registry change needs no restart."""
    global _registry_cache
    path = os.getenv("URL_TRACKING_REGISTRY_PATH", "").strip()
    if path and os.path.isfile(path):
        try:
            mtime = os.path.getmtime(path)
            if _registry_cache and _registry_cache[0] == path and _registry_cache[1] == mtime:
                return _registry_cache[2]
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            merged = {
                "version": data.get("version") or BUILTIN_REGISTRY["version"],
                "global": list(BUILTIN_REGISTRY["global"]) + list(data.get("global", [])),
                "global_prefixes": list(BUILTIN_REGISTRY["global_prefixes"]) + list(data.get("global_prefixes", [])),
                "hosts": {**BUILTIN_REGISTRY["hosts"]},
            }
            for host, params in (data.get("hosts") or {}).items():
                merged["hosts"][host] = list(merged["hosts"].get(host, [])) + list(params)
            reg = _build(merged)
            _registry_cache = (path, mtime, reg)
            return reg
        except (OSError, ValueError):
            pass
    if _registry_cache and _registry_cache[0] == "":
        return _registry_cache[2]
    reg = _build(BUILTIN_REGISTRY)
    _registry_cache = ("", 0.0, reg)
    return reg


def registry_version() -> str:
    return load_registry().version


# ---------------------------------------------------------------------------
# Canonical URL
# ---------------------------------------------------------------------------

_DEFAULT_PORTS = {"http": "80", "https": "443"}


@dataclass
class NormalizedUrl:
    original: str
    canonical: str
    host: Optional[str]
    stripped: List[str] = field(default_factory=list)
    registry_version: str = ""
    valid: bool = True

    @property
    def changed(self) -> bool:
        return self.original != self.canonical


def normalize_url(url: Optional[str], *, registry: Optional[Registry] = None) -> NormalizedUrl:
    """Canonical form of ``url`` under the registry. Never raises."""
    reg = registry or load_registry()
    raw = (url or "").strip()
    if not raw:
        return NormalizedUrl(original=raw, canonical="", host=None, registry_version=reg.version, valid=False)
    try:
        parts = urlsplit(raw)
    except ValueError:
        return NormalizedUrl(original=raw, canonical=raw, host=None, registry_version=reg.version, valid=False)
    scheme = (parts.scheme or "").lower()
    if scheme not in ("http", "https"):
        return NormalizedUrl(original=raw, canonical=raw, host=None, registry_version=reg.version, valid=False)
    host = (parts.hostname or "").lower()
    if not host:
        return NormalizedUrl(original=raw, canonical=raw, host=None, registry_version=reg.version, valid=False)
    netloc = host
    if parts.port is not None and str(parts.port) != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{parts.port}"
    if parts.username:
        cred = parts.username + (f":{parts.password}" if parts.password else "")
        netloc = f"{cred}@{netloc}"
    stripped: List[str] = []
    kept: List[Tuple[str, str]] = []
    if parts.query:
        for name, value in parse_qsl(parts.query, keep_blank_values=True):
            if reg.is_tracking(host, name):
                stripped.append(name)
            else:
                kept.append((name, value))
    query = urlencode(kept, doseq=False) if kept else ""
    path = parts.path or "/"
    canonical = urlunsplit((scheme, netloc, path, query, ""))
    return NormalizedUrl(original=raw, canonical=canonical, host=host, stripped=stripped,
                         registry_version=reg.version, valid=True)


def canonical_url(url: Optional[str]) -> str:
    return normalize_url(url).canonical


def strip_tracking_query(host: str, query: str, *, registry: Optional[Registry] = None) -> str:
    """Only the query-string half of ``normalize_url``, for callers that keep
    their own host and path handling (the monolith's ``story_url_key``)."""
    if not query:
        return ""
    reg = registry or load_registry()
    kept = [(n, v) for n, v in parse_qsl(query, keep_blank_values=True) if not reg.is_tracking(host, n)]
    return urlencode(kept) if kept else ""


# ---------------------------------------------------------------------------
# Redirect wrappers (work package 27)
# ---------------------------------------------------------------------------

_GOOGLE_NEWS_HOSTS = ("news.google.com",)


def is_redirect_wrapper(url: Optional[str]) -> bool:
    """A URL that is a redirect to the real page, not the page. Google News
    RSS links are the documented case: a full-text provider rejects them."""
    host = (normalize_url(url).host or "")
    if host in _GOOGLE_NEWS_HOSTS and "/rss/articles/" in (url or ""):
        return True
    if host in ("www.google.com", "google.com") and "/url?" in (url or ""):
        return True
    return False


def unwrap_redirect(url: str) -> Optional[str]:
    """The target of a redirect wrapper when it is carried in the URL itself
    (``google.com/url?url=...``). Google News ``/rss/articles/`` links encode
    the target and need an HTTP resolve; this returns None for them."""
    parts = urlsplit(url)
    if parts.hostname in ("www.google.com", "google.com") and parts.path == "/url":
        for name, value in parse_qsl(parts.query):
            if name in ("url", "q") and value.startswith(("http://", "https://")):
                return value
    return None


# ---------------------------------------------------------------------------
# Identity by record type (work package 4)
# ---------------------------------------------------------------------------

RT_NEWS = "news"
RT_SOCIAL = "social_post"
RT_SCHOLARLY = "scholarly"
RT_FEED_ENTRY = "feed_entry"
RT_CALENDAR = "calendar_event"

ID_PROVIDER = "provider_id"
ID_SOCIAL = "platform_post_id"
ID_DOI = "doi"
ID_CANONICAL_URL = "canonical_url"
ID_FEED_GUID = "feed_guid"
ID_CALENDAR = "calendar_occurrence"
ID_CONTENT_HASH = "content_hash"

_DOI_RE = re.compile(r"(10\.\d{4,9}/[^\s\"'<>]+)", re.IGNORECASE)


def normalize_doi(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    m = _DOI_RE.search(str(value))
    if not m:
        return None
    return m.group(1).rstrip(".,;)").lower()


@dataclass(frozen=True)
class Identity:
    method: str
    key: str
    #: True when the key is a document identity (merge candidates with the
    #: same key); False for observation identities that only dedupe one
    #: feed's replays (feed GUID).
    document_level: bool = True

    def as_tuple(self) -> Tuple[str, str]:
        return (self.method, self.key)


def content_fingerprint(title: Optional[str], content: Optional[str]) -> str:
    seed = f"{(title or '').strip().lower()}|{(content or '')[:500].strip().lower()}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


def choose_identity(*, record_type: str = RT_NEWS, provider: Optional[str] = None,
                    external_id: Optional[str] = None, url: Optional[str] = None,
                    platform: Optional[str] = None, post_id: Optional[str] = None,
                    doi: Optional[str] = None, feed_scope: Optional[str] = None,
                    guid: Optional[str] = None, occurrence_key: Optional[str] = None,
                    title: Optional[str] = None, content: Optional[str] = None) -> Identity:
    """The one identity this record is resolved by.

    Order: calendar occurrence, social post, DOI, canonical URL, feed GUID
    (scoped to its feed), then a deterministic content hash. Each is
    explicit so the stored ``identity_method`` says how a row was matched.
    """
    if record_type == RT_CALENDAR and occurrence_key:
        return Identity(ID_CALENDAR, f"{feed_scope or ''}|{occurrence_key}")
    if record_type == RT_SOCIAL or (platform and post_id):
        if platform and post_id:
            return Identity(ID_SOCIAL, f"{platform.lower()}:{post_id}")
        if external_id and provider:
            return Identity(ID_PROVIDER, f"{provider.lower()}:{external_id}")
        # A social post with no stable id is not identified by its URL: a
        # profile URL stands in for many posts (work package 5).
        return Identity(ID_CONTENT_HASH, content_fingerprint(title, content))
    d = normalize_doi(doi) or (normalize_doi(external_id) if record_type == RT_SCHOLARLY else None)
    if d:
        return Identity(ID_DOI, d)
    if record_type == RT_SCHOLARLY and external_id and provider:
        return Identity(ID_PROVIDER, f"{provider.lower()}:{external_id}")
    norm = normalize_url(url)
    if norm.valid:
        return Identity(ID_CANONICAL_URL, norm.canonical)
    if guid and feed_scope:
        return Identity(ID_FEED_GUID, f"{feed_scope}|{guid}", document_level=False)
    if external_id and provider:
        return Identity(ID_PROVIDER, f"{provider.lower()}:{external_id}")
    return Identity(ID_CONTENT_HASH, content_fingerprint(title, content))


def observation_identity(*, provider: str, external_id: Optional[str], feed_scope: Optional[str] = None,
                         guid: Optional[str] = None, url: Optional[str] = None) -> Optional[Identity]:
    """How one provider's copy of a record is told apart from its replays.
    Feed GUIDs are scoped to the feed: unrelated feeds reuse GUIDs."""
    if feed_scope and guid:
        return Identity(ID_FEED_GUID, f"{feed_scope}|{guid}", document_level=False)
    if external_id:
        return Identity(ID_PROVIDER, f"{provider.lower()}:{external_id}", document_level=False)
    norm = normalize_url(url)
    if norm.valid:
        return Identity(ID_CANONICAL_URL, f"{provider.lower()}|{norm.canonical}", document_level=False)
    return None


def variant_groups(urls: Iterable[str]) -> Dict[str, List[str]]:
    """Group URLs that share a canonical form. Used by the repair script
    that proposes registry additions from URL-variant groups."""
    out: Dict[str, List[str]] = {}
    for u in urls:
        out.setdefault(canonical_url(u), []).append(u)
    return {k: v for k, v in out.items() if len(v) > 1}
