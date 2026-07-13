"""Async Wikidata client (monolith port).

Ported from saasmvp-app/app/entities/wikidata_client.py with two changes:

- Redis caching replaced by a process-local in-memory TTL cache (the tenant
  venvs don't ship the redis module).
- Claim qualifiers (P580 start time / P582 end time) are extracted so callers
  can filter out former officeholders (e.g. ex-CEOs on P169).

Wraps two endpoints of the MediaWiki Action API:

- ``wbsearchentities`` — fuzzy search for entities by name.
- ``wbgetentities`` — fetch full claims for a QID.

Empty / errored responses return ``None`` (or ``[]``) rather than raising.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
USER_AGENT = "AunooAI/1.0 (brand-entity-verification; https://aunoo.ai)"
DEFAULT_TIMEOUT = 15.0
CACHE_TTL_SECONDS = 7 * 24 * 3600  # 7 days
_MAX_CACHE_ENTRIES = 4000

# Wikidata fair-use target: 5 req/sec with a well-identified User-Agent.
RATE_LIMIT_INTERVAL_SEC = 0.2

# Claims we actually read from wbgetentities:
#   P17   = country
#   P31   = instance of
#   P112  = founder
#   P127  = owner
#   P159  = headquarters location
#   P169  = chief executive officer
#   P488  = chairperson
#   P749  = parent organization
#   P856  = official website
#   P1830 = owner of (inverse of P127)
_CLAIMS_FILTER = ["P17", "P31", "P112", "P127", "P159", "P169", "P488", "P749", "P856", "P1830"]

# Qualifier properties extracted per-claim (needed to tell current vs former
# officeholders: a P169 claim with a P582 end time is an ex-CEO).
_QUALIFIERS_FILTER = ["P580", "P582"]  # start time / end time


# ─── DTOs ────────────────────────────────────────────────────────────────────


@dataclass
class WikidataClaim:
    """A single claim extracted from a wbgetentities response."""

    property_id: str          # "P17", "P856", etc.
    value: Any                # QID string, URL, date, etc.
    qualifiers: dict[str, Any] = field(default_factory=dict)


@dataclass
class WikidataEntity:
    """The subset of a Wikidata entity record we actually use."""

    qid: str
    label: str
    description: Optional[str] = None
    aliases: list[str] = field(default_factory=list)
    claims: dict[str, list[WikidataClaim]] = field(default_factory=dict)
    sitelinks_count: int = 0
    wikipedia_url: Optional[str] = None

    def claim_values(self, property_id: str) -> list[Any]:
        return [c.value for c in self.claims.get(property_id, [])]

    def first_claim_value(self, property_id: str) -> Optional[Any]:
        claims = self.claims.get(property_id, [])
        return claims[0].value if claims else None


# ─── Rate limiter ────────────────────────────────────────────────────────────


class _AsyncRateLimiter:
    """Simple token-bucket style limiter. One global instance per process."""

    def __init__(self, interval_sec: float):
        self.interval = interval_sec
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            if elapsed < self.interval:
                await asyncio.sleep(self.interval - elapsed)
            self._last = time.monotonic()


_rate_limiter = _AsyncRateLimiter(RATE_LIMIT_INTERVAL_SEC)


# ─── In-memory TTL cache ─────────────────────────────────────────────────────


_mem_cache: dict[str, tuple[float, dict]] = {}


def _cache_get(key: str) -> Optional[dict]:
    entry = _mem_cache.get(key)
    if entry is None:
        return None
    expiry, value = entry
    if time.monotonic() > expiry:
        _mem_cache.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: dict) -> None:
    if len(_mem_cache) >= _MAX_CACHE_ENTRIES:
        # Evict the soonest-to-expire quarter of the cache.
        by_expiry = sorted(_mem_cache.items(), key=lambda kv: kv[1][0])
        for k, _ in by_expiry[: _MAX_CACHE_ENTRIES // 4]:
            _mem_cache.pop(k, None)
    _mem_cache[key] = (time.monotonic() + CACHE_TTL_SECONDS, value)


# ─── Public client ───────────────────────────────────────────────────────────


class WikidataClient:
    """Async Wikidata client.

    Usage:

        async with WikidataClient() as client:
            candidates = await client.search("Wiley")
            entity = await client.get_entity("Q1479654")
    """

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self._external_client = http_client is not None
        self._http = http_client

    async def __aenter__(self) -> "WikidataClient":
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=DEFAULT_TIMEOUT,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                follow_redirects=True,
            )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._http is not None and not self._external_client:
            await self._http.aclose()
            self._http = None

    # ── Candidate generation ────────────────────────────────────────────────

    async def search(
        self,
        name: str,
        *,
        limit: int = 10,
        language: str = "en",
    ) -> list[dict]:
        """Fuzzy-search Wikidata for entities matching ``name``.

        Returns candidate stubs with ``qid`` / ``label`` / ``description``.
        """
        if not name or not name.strip():
            return []

        cache_key = f"wd:search:{language}:{name.strip().lower()}:{limit}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached.get("hits", [])

        await _rate_limiter.wait()
        params = {
            "action": "wbsearchentities",
            "format": "json",
            "language": language,
            "uselang": language,
            "type": "item",
            "search": name.strip(),
            "limit": limit,
        }
        try:
            resp = await self._http.get(WIKIDATA_API_URL, params=params)  # type: ignore[union-attr]
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Wikidata search failed for %r: %s", name, e)
            return []

        data = resp.json()
        hits = [
            {
                "qid": r.get("id"),
                "label": r.get("label") or r.get("match", {}).get("text") or "",
                "description": r.get("description"),
                "aliases": r.get("aliases") or [],
            }
            for r in data.get("search", [])
            if r.get("id")
        ]
        _cache_set(cache_key, {"hits": hits})
        return hits

    # ── Claim fetching ──────────────────────────────────────────────────────

    async def get_entity(self, qid: str, *, language: str = "en") -> Optional[WikidataEntity]:
        """Fetch a full Wikidata entity by QID. Returns None on errors."""
        if not qid or not qid.startswith("Q"):
            return None

        cache_key = f"wd:entity:{qid}:{language}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return _parse_entity(cached, qid, language)

        await _rate_limiter.wait()
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": qid,
            "props": "labels|descriptions|aliases|claims|sitelinks/urls",
            "languages": language,
        }
        try:
            resp = await self._http.get(WIKIDATA_API_URL, params=params)  # type: ignore[union-attr]
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Wikidata get_entity failed for %s: %s", qid, e)
            return None

        data = resp.json()
        raw_entity = (data.get("entities") or {}).get(qid)
        if not raw_entity:
            return None

        _cache_set(cache_key, raw_entity)
        return _parse_entity(raw_entity, qid, language)

    # ── Convenience ─────────────────────────────────────────────────────────

    async def get_entities_batch(
        self,
        qids: list[str],
        *,
        language: str = "en",
        concurrency: int = 4,
    ) -> dict[str, Optional[WikidataEntity]]:
        """Fetch multiple QIDs in parallel, respecting the rate limiter."""
        sem = asyncio.Semaphore(concurrency)

        async def _one(qid: str) -> tuple[str, Optional[WikidataEntity]]:
            async with sem:
                return qid, await self.get_entity(qid, language=language)

        results = await asyncio.gather(*[_one(q) for q in qids])
        return dict(results)


# ─── Parsing helpers ─────────────────────────────────────────────────────────


def _parse_entity(raw: dict, qid: str, language: str) -> WikidataEntity:
    """Pull the bits we actually use out of a raw wbgetentities response."""
    labels = raw.get("labels") or {}
    label = (labels.get(language) or {}).get("value") or qid

    descriptions = raw.get("descriptions") or {}
    description = (descriptions.get(language) or {}).get("value")

    aliases_field = raw.get("aliases") or {}
    aliases = [a.get("value") for a in (aliases_field.get(language) or []) if a.get("value")]

    claims_raw = raw.get("claims") or {}
    claims: dict[str, list[WikidataClaim]] = {}
    for pid in _CLAIMS_FILTER:
        stmts = claims_raw.get(pid) or []
        for stmt in stmts:
            mainsnak = stmt.get("mainsnak") or {}
            value = _extract_snak_value(mainsnak)
            if value is None:
                continue
            qualifiers: dict[str, Any] = {}
            for qpid in _QUALIFIERS_FILTER:
                qsnaks = (stmt.get("qualifiers") or {}).get(qpid) or []
                for qsnak in qsnaks:
                    qval = _extract_snak_value(qsnak)
                    if qval is not None:
                        qualifiers[qpid] = qval
                        break
            claims.setdefault(pid, []).append(
                WikidataClaim(property_id=pid, value=value, qualifiers=qualifiers)
            )

    sitelinks = raw.get("sitelinks") or {}
    sitelinks_count = len(sitelinks)
    wikipedia_url: Optional[str] = None
    sl_key = f"{language}wiki"
    if sl_key in sitelinks:
        wikipedia_url = sitelinks[sl_key].get("url")

    return WikidataEntity(
        qid=qid,
        label=label,
        description=description,
        aliases=aliases,
        claims=claims,
        sitelinks_count=sitelinks_count,
        wikipedia_url=wikipedia_url,
    )


def _extract_snak_value(snak: dict):
    """Pull a usable Python value out of a Wikidata snak block."""
    if snak.get("snaktype") != "value":
        return None
    datavalue = snak.get("datavalue") or {}
    dv_type = datavalue.get("type")
    value = datavalue.get("value")
    if value is None:
        return None
    if dv_type == "wikibase-entityid":
        return value.get("id")  # e.g. "Q145"
    if dv_type == "string":
        return value
    if dv_type == "monolingualtext":
        return value.get("text")
    if dv_type == "time":
        return value.get("time")
    if dv_type == "globecoordinate":
        return {"lat": value.get("latitude"), "lon": value.get("longitude")}
    return value


# ─── Convenience context-manager for one-off use ─────────────────────────────


@asynccontextmanager
async def wikidata_client():
    """One-off helper: `async with wikidata_client() as c: ...`."""
    async with WikidataClient() as c:
        yield c
