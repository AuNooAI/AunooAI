"""Bright Data LinkedIn Scraper API client.

Monolith port. Identical transport and mapping to the SaaS build; the only
difference is configuration, which comes from the environment here rather than
a pydantic Settings object.

Two collection surfaces, both public LinkedIn company data:

- **Company profiles** — employee count, followers, description, specialties,
  locations. These are *measurements*, so they land in ``bm_vendor_snapshots``.
  A profile rendered as a news article would be a fabricated story with a real
  company's name on it.
- **Company posts** — what the vendor published. These are coverage, so they go
  through ``normalize_article`` and ``CollectionPipeline`` like everything else,
  under the source ``linkedin_company_post``.

Sync ``/scrape`` is for manual refreshes of at most ``SYNC_MAX_URLS`` URLs.
Scheduled production batches use ``/trigger`` plus a signed webhook, because an
82-vendor batch outlives any request we could hold open.

Nothing here talks to the database. The caller owns runs, snapshots and
transactions, so this module stays testable against fixtures and the mapping
functions can be exercised with no network at all.

Reference:
- https://docs.brightdata.com/datasets/scrapers/linkedin/introduction
- https://docs.brightdata.com/datasets/scrapers/linkedin/send-first-request
- https://docs.brightdata.com/api-reference/scrapers/social-media-apis/linkedin-posts-discover-by-company-url
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


# Dataset ids are configuration, not business logic: Bright Data rotates them
# and a repoint must not need a deploy. Defaults are the currently documented
# ones.
def api_base() -> str:
    return _env("BRIGHTDATA_API_BASE_URL", "https://api.brightdata.com")


def profile_dataset() -> str:
    return _env("BRIGHTDATA_LINKEDIN_PROFILE_DATASET_ID", "gd_l1vikfnt1wgvvqz95w")


def posts_dataset() -> str:
    return _env("BRIGHTDATA_LINKEDIN_POSTS_DATASET_ID", "gd_lyy3tktm25m4avu764")


def jobs_dataset() -> str:
    """LinkedIn job listings — hiring velocity and role mix."""
    return _env("BRIGHTDATA_LINKEDIN_JOBS_DATASET_ID", "gd_lpfll7v5hcqtkxl6l")


def crunchbase_dataset() -> str:
    """Crunchbase companies — rounds, investors, acquisitions, IPO status."""
    return _env("BRIGHTDATA_CRUNCHBASE_DATASET_ID", "gd_l1vijqt9jfj7olije")


def indeed_dataset() -> str:
    """Indeed job listings — discovered by employer name, not URL."""
    return _env("BRIGHTDATA_INDEED_DATASET_ID", "gd_l4dx9j9sscpvs7no2")


def pitchbook_dataset() -> str:
    """PitchBook companies — funding and ownership. No auto-discovery: see
    ``trigger_pitchbook`` for why a vendor's URL has to be entered by hand."""
    return _env("BRIGHTDATA_PITCHBOOK_DATASET_ID", "gd_m4ijiqfp2n9oe3oluj")


def zoominfo_dataset() -> str:
    """ZoomInfo companies — revenue, leadership, headcount. Same manual-URL
    caveat as ``pitchbook_dataset``."""
    return _env("BRIGHTDATA_ZOOMINFO_DATASET_ID", "gd_m0ci4a4ivx3j5l6nx")


def webhook_secret() -> str:
    return _env("BRIGHTDATA_LINKEDIN_WEBHOOK_SECRET")


def api_key() -> str:
    """One Bright Data token serves both the Web Unlocker and the LinkedIn
    datasets, so a dedicated key is optional and falls back to the shared one."""
    return _env("BRIGHTDATA_LINKEDIN_API_KEY") or _env("BRIGHTDATA_API_KEY")


def linkedin_enabled() -> bool:
    return _env("BRIGHTDATA_LINKEDIN_ENABLED", "false").lower() in ("1", "true", "yes", "on")

# Bright Data holds a sync request open while it scrapes. Twenty URLs is the
# documented practical ceiling; past that the request times out before the
# batch finishes and we lose the work without a snapshot id to recover it.
SYNC_MAX_URLS = 20
SYNC_TIMEOUT = 180.0
TRIGGER_TIMEOUT = 60.0
POLL_TIMEOUT = 30.0


class BrightDataError(RuntimeError):
    """A provider call failed. Carries the status so callers can decide whether
    the failure is retryable (5xx, 429) or terminal (4xx)."""

    def __init__(self, message: str, *, status: int | None = None,
                 retryable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable


@dataclass
class TriggerResult:
    snapshot_id: str
    dataset_id: str
    requested: int
    request_hash: str


def _request_hash(dataset_id: str, urls: list[str], extra: dict | None = None) -> str:
    """Stable fingerprint of a batch, so a retry is recognisable as one."""
    payload = "|".join([dataset_id, *sorted(urls), repr(sorted((extra or {}).items()))])
    return hashlib.sha256(payload.encode()).hexdigest()


class LinkedInDatasetClient:
    """Thin transport over Bright Data's dataset endpoints."""

    def __init__(self, api_key: str, *, base_url: str | None = None,
                 profile_dataset_id: str | None = None,
                 posts_dataset_id: str | None = None) -> None:
        if not api_key:
            raise BrightDataError("No Bright Data API key configured")
        self._key = api_key
        self._base = (base_url or api_base()).rstrip("/")
        self.profile_dataset_id = profile_dataset_id or profile_dataset()
        self.posts_dataset_id = posts_dataset_id or posts_dataset()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _raise_for(resp: httpx.Response, what: str) -> None:
        if resp.status_code < 400:
            return
        # 429 and 5xx are worth another attempt; a 4xx means the request itself
        # is wrong and retrying just spends the budget again.
        retryable = resp.status_code == 429 or resp.status_code >= 500
        raise BrightDataError(
            f"{what} failed: HTTP {resp.status_code} {resp.text[:300]}",
            status=resp.status_code,
            retryable=retryable,
        )

    # ── Async: trigger + webhook ────────────────────────────────────────────

    async def trigger(
        self,
        dataset_id: str,
        payload: list[dict[str, Any]],
        *,
        webhook_url: str | None = None,
        webhook_auth: str | None = None,
        include_errors: bool = True,
        extra_params: dict[str, Any] | None = None,
    ) -> TriggerResult:
        """Queue a batch. Returns the snapshot id to record against the run.

        The snapshot id is the only handle that survives the request, which is
        why the caller must persist it *before* awaiting anything else — a
        webhook that arrives before its run row exists has nowhere to land.
        """
        urls = [p.get("url", "") for p in payload]
        params: dict[str, Any] = {"dataset_id": dataset_id, "format": "json"}
        if include_errors:
            params["include_errors"] = "true"
        # Discovery datasets take their mode and bounds as query parameters;
        # sending them inside the payload is a validation error.
        params.update(extra_params or {})
        if webhook_url:
            params["endpoint"] = webhook_url
            params["notify"] = webhook_url
            if webhook_auth:
                # Bright Data echoes this back on the callback. It is the only
                # thing standing between the webhook and anyone who guesses
                # the URL, so it is required in practice.
                params["auth_header"] = webhook_auth

        async with httpx.AsyncClient(timeout=TRIGGER_TIMEOUT) as client:
            resp = await client.post(
                f"{self._base}/datasets/v3/trigger",
                params=params, headers=self._headers, json=payload,
            )
        self._raise_for(resp, "trigger")
        body = resp.json() if resp.content else {}
        snapshot_id = body.get("snapshot_id") or body.get("collection_id")
        if not snapshot_id:
            raise BrightDataError(f"trigger returned no snapshot id: {body}")
        return TriggerResult(
            snapshot_id=snapshot_id,
            dataset_id=dataset_id,
            requested=len(payload),
            request_hash=_request_hash(dataset_id, urls),
        )

    async def discover_by_keyword(
        self,
        dataset_id: str,
        inputs: list[dict[str, Any]],
        *,
        limit_per_input: int | None = None,
        webhook_url: str | None = None,
        webhook_auth: str | None = None,
    ) -> TriggerResult:
        """Shared transport for every ``discover_by=keyword`` dataset —
        LinkedIn jobs, Crunchbase companies, Indeed jobs, and any dataset
        added later that turns out to support it. Confirmed identical across
        those three from real sample requests (2026-08-22); only the input
        field *names* differ per dataset (``keyword``, ``keyword_search``,
        ``company`` + ``keyword``, ...), which is the caller's job to supply
        in ``inputs`` — this method only owns the query string and the
        request shape, not what a record means.

        Do not add a new caller here on a guessed field name. A wrong field
        can return another company's records rather than erroring — see
        ``trigger_jobs``'s history below for what that cost to find out.
        """
        params: dict[str, Any] = {"type": "discover_new", "discover_by": "keyword"}
        if limit_per_input:
            params["limit_per_input"] = str(limit_per_input)
        return await self.trigger(
            dataset_id, inputs, webhook_url=webhook_url, webhook_auth=webhook_auth,
            extra_params=params,
        )

    async def snapshot_status(self, snapshot_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=POLL_TIMEOUT) as client:
            resp = await client.get(
                f"{self._base}/datasets/v3/progress/{snapshot_id}",
                headers=self._headers,
            )
        self._raise_for(resp, "progress")
        return resp.json() if resp.content else {}

    async def fetch_snapshot(self, snapshot_id: str) -> list[dict[str, Any]]:
        """Download a finished snapshot.

        Bright Data serves either a JSON array or newline-delimited JSON
        depending on size, so both are accepted rather than assuming one.
        """
        async with httpx.AsyncClient(timeout=SYNC_TIMEOUT) as client:
            resp = await client.get(
                f"{self._base}/datasets/v3/snapshot/{snapshot_id}",
                params={"format": "json"}, headers=self._headers,
            )
        self._raise_for(resp, "snapshot")
        return _decode_records(resp.text)

    # ── Sync: manual refresh only ───────────────────────────────────────────

    async def scrape_sync(
        self, dataset_id: str, payload: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if len(payload) > SYNC_MAX_URLS:
            raise BrightDataError(
                f"Sync scrape accepts at most {SYNC_MAX_URLS} URLs; "
                f"got {len(payload)}. Use trigger() for larger batches."
            )
        async with httpx.AsyncClient(timeout=SYNC_TIMEOUT) as client:
            resp = await client.post(
                f"{self._base}/datasets/v3/scrape",
                params={"dataset_id": dataset_id, "format": "json"},
                headers=self._headers, json=payload,
            )
        self._raise_for(resp, "scrape")
        return _decode_records(resp.text)

    # ── Convenience wrappers ────────────────────────────────────────────────

    async def trigger_profiles(
        self, urls: list[str], *, webhook_url: str | None = None,
        webhook_auth: str | None = None,
    ) -> TriggerResult:
        return await self.trigger(
            self.profile_dataset_id, [{"url": u} for u in urls],
            webhook_url=webhook_url, webhook_auth=webhook_auth,
        )

    async def trigger_posts(
        self, urls: list[str], *, since: datetime | None = None,
        until: datetime | None = None, limit_per_input: int = 25,
        webhook_url: str | None = None, webhook_auth: str | None = None,
    ) -> TriggerResult:
        """Discover company posts by company URL.

        The payload carries the URL and nothing else — this dataset rejects
        ``start_date`` and ``limit`` as item fields, which is a validation
        error, not a silently ignored one. The bound goes in the query string
        as ``limit_per_input`` instead, and it matters for cost: without it a
        first run pulls a company's whole post history.

        ``since`` and ``until`` are accepted for interface symmetry with
        ``trigger_profiles`` and the poll task, but this dataset does not
        filter by date — recency is enforced when the records are ingested.
        """
        payload = [{"url": url} for url in urls]
        params: dict[str, Any] = {
            "type": "discover_new",
            "discover_by": "company_url",
        }
        if limit_per_input:
            params["limit_per_input"] = str(limit_per_input)
        return await self.trigger(
            self.posts_dataset_id, payload,
            webhook_url=webhook_url, webhook_auth=webhook_auth,
            extra_params=params,
        )


    async def trigger_jobs(
        self, companies: list[dict[str, Any]], *, limit_per_input: int = 20,
        webhook_url: str | None = None, webhook_auth: str | None = None,
    ) -> TriggerResult:
        """Discover job listings by employer.

        Verified against the dataset on 2026-08-20. ``discover_by=keyword``
        with ``company`` as its own input field is the only mode that works
        here. The alternatives all fail, and two of them fail quietly:

        - ``discover_by=company_url`` — rejected, mode not supported.
        - ``/company/{slug}/jobs/`` by url — every record a ``proxy`` error.
        - ``/jobs/{slug}-jobs?f_C={id}`` by url — dead page. The documented
          examples are Semrush and Reddit; small companies have no such page.
        - the company name in ``keyword`` — returns other employers' postings,
          which is worse than returning nothing.

        A control run separated "wrong input" from "nothing to find":
        CrowdStrike returned five postings, all correctly attributed, while a
        77-person vendor returned none. Small vendors simply have few public
        listings, so expect this signal to be sparse across an early-stage
        registry rather than to indicate a broken integration.

        ``companies`` entries take ``name`` and optionally ``location`` and
        ``keyword``.
        """
        payload = [
            {
                "company": c.get("name", ""),
                "location": c.get("location") or "United States",
                "keyword": c.get("keyword") or "",
            }
            for c in companies if c.get("name")
        ]
        return await self.discover_by_keyword(
            jobs_dataset(), payload, limit_per_input=limit_per_input,
            webhook_url=webhook_url, webhook_auth=webhook_auth,
        )

    async def trigger_crunchbase(
        self, urls: list[str], *, webhook_url: str | None = None,
        webhook_auth: str | None = None,
    ) -> TriggerResult:
        """Collect company records by Crunchbase URL.

        Straight collection, no discovery: this dataset takes a
        crunchbase.com/organization URL and returns the company, its rounds and
        its investors.
        """
        return await self.trigger(
            crunchbase_dataset(), [{"url": u} for u in urls],
            webhook_url=webhook_url, webhook_auth=webhook_auth,
        )

    async def trigger_crunchbase_discover(
        self, names: list[str], *, limit_per_input: int = 5,
        webhook_url: str | None = None, webhook_auth: str | None = None,
    ) -> TriggerResult:
        """Discover a company's Crunchbase record by name, instead of
        guessing its URL from a slugified name the way ``crunchbase_url_for``
        does (roughly two hits in three).

        Confirmed live via a real sample request (2026-08-22) — but the
        *response* shape for this mode (a search-hit list vs. a full company
        record) is not yet confirmed against real output, so this is not
        wired into ``seed_crunchbase_urls`` or the scheduled poller yet. Do
        not switch the working slug-guess flow over to this until a real
        response has been read.
        """
        payload = [{"keyword": n} for n in names if n]
        return await self.discover_by_keyword(
            crunchbase_dataset(), payload, limit_per_input=limit_per_input,
            webhook_url=webhook_url, webhook_auth=webhook_auth,
        )

    async def trigger_pitchbook(
        self, urls: list[str], *, webhook_url: str | None = None,
        webhook_auth: str | None = None,
    ) -> TriggerResult:
        """Collect company records by PitchBook URL.

        Confirmed request shape (2026-08-22): straight collection, no
        discovery, same as ``trigger_crunchbase``. Unlike Crunchbase,
        PitchBook's URL ends in an opaque numeric id
        (``pitchbook.com/profiles/company/10874-98``) that cannot be guessed
        from a company name — a vendor needs one recorded as an identifier
        (kind ``pitchbook_url``) before this has anything to collect.
        """
        return await self.trigger(
            pitchbook_dataset(), [{"url": u} for u in urls],
            webhook_url=webhook_url, webhook_auth=webhook_auth,
        )

    async def trigger_zoominfo(
        self, urls: list[str], *, webhook_url: str | None = None,
        webhook_auth: str | None = None,
    ) -> TriggerResult:
        """Collect company records by ZoomInfo URL. Same manual-identifier
        caveat as ``trigger_pitchbook`` — ZoomInfo profile URLs
        (``zoominfo.com/c/<slug>/<id>``) also end in an opaque numeric id."""
        return await self.trigger(
            zoominfo_dataset(), [{"url": u} for u in urls],
            webhook_url=webhook_url, webhook_auth=webhook_auth,
        )

    async def trigger_indeed_discover(
        self, searches: list[dict[str, Any]], *, limit_per_input: int = 15,
        webhook_url: str | None = None, webhook_auth: str | None = None,
    ) -> TriggerResult:
        """Discover Indeed job listings by employer.

        Confirmed request shape (2026-08-22): ``discover_by=keyword`` with
        ``country``, ``domain``, ``keyword_search``, ``location``,
        ``date_posted``, ``posted_by`` and ``location_radius``. The sample
        request used ``keyword_search`` for the role ("analyst", "product
        manager"), which leaves ``posted_by`` as the employer filter by
        elimination — an inference from the field name and the pattern
        already verified for LinkedIn jobs (a separate ``company`` field,
        not the keyword itself), not a confirmed response. Read the first
        live batch's employer attribution before trusting the volume, the
        same discipline ``trigger_jobs`` already documents for its own
        history of silently-wrong modes.

        ``searches`` entries take ``employer`` (required) and optionally
        ``role``, ``location``, ``country``, ``domain``, ``date_posted``.
        """
        payload = [
            {
                "country": s.get("country") or "US",
                "domain": s.get("domain") or "indeed.com",
                "keyword_search": s.get("role") or "",
                "location": s.get("location") or "United States",
                "date_posted": s.get("date_posted") or "",
                "posted_by": s["employer"],
                "location_radius": s.get("location_radius") or "",
            }
            for s in searches if s.get("employer")
        ]
        return await self.discover_by_keyword(
            indeed_dataset(), payload, limit_per_input=limit_per_input,
            webhook_url=webhook_url, webhook_auth=webhook_auth,
        )


def crunchbase_url_for(slug: str) -> str:
    """Derive a Crunchbase organization URL from a vendor slug.

    A guess, and recorded as one. Crunchbase's own slug usually matches the
    company name slugified, but not always — a miss costs one error record and
    should become a review task rather than a silent gap.
    """
    return f"https://www.crunchbase.com/organization/{slug}"


def _decode_records(body: str) -> list[dict[str, Any]]:
    import json

    text = (body or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("brightdata: unparseable snapshot line, skipped")
        return rows
    if isinstance(data, dict):
        # A single record, or an error envelope.
        return [data]
    return [r for r in data if isinstance(r, dict)]


# ---------------------------------------------------------------------------
# Webhook authentication
# ---------------------------------------------------------------------------

def webhook_auth_value(secret: str | None = None) -> str:
    """The exact ``Authorization`` value we ask Bright Data to send back."""
    return f"Bearer {secret or webhook_secret()}"


def verify_webhook_auth(header_value: str | None, secret: str | None = None) -> bool:
    """Constant-time check of the callback's Authorization header.

    Fail-closed on an unset secret. The endpoint has to be unauthenticated for
    Bright Data to reach it, so this shared value is the whole of its defence —
    an empty secret must reject everything, not accept everything.
    """
    expected_secret = secret if secret is not None else webhook_secret()
    if not expected_secret:
        return False
    if not header_value:
        return False
    return hmac.compare_digest(header_value.strip(), webhook_auth_value(expected_secret))


# ---------------------------------------------------------------------------
# Field mapping — provider shape in, our shape out
# ---------------------------------------------------------------------------

def _first(raw: dict[str, Any], *keys: str) -> Any:
    """Bright Data's field names drift between dataset versions, so read a
    small set of plausible names rather than pinning one and silently
    collecting nulls after a schema change."""
    for k in keys:
        if k in raw and raw[k] not in (None, "", []):
            return raw[k]
    return None


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits) if digits else None


def _as_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    for parse in (
        lambda s: datetime.fromisoformat(s),
        lambda s: datetime.strptime(s, "%Y-%m-%d"),
    ):
        try:
            dt = parse(text)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def normalize_crunchbase_key(url: Any) -> Optional[str]:
    """Canonical Crunchbase organization URL, or None."""
    if not url or not isinstance(url, str):
        return None
    m = re.search(r"crunchbase\.com/organization/([^/?#]+)", url, re.I)
    if not m:
        return None
    return f"https://www.crunchbase.com/organization/{m.group(1).strip().lower()}"


def normalize_linkedin_key(url: Any) -> Optional[str]:
    """The canonical company URL used as the identity key everywhere.

    Delegates to the importer's normalizer so the registry, the provider
    records and the lookup map cannot drift apart — a key derived two
    different ways is a vendor whose posts silently stop matching.
    """
    from app.services.market_import import normalize_linkedin

    if not url or not isinstance(url, str):
        return None
    canonical, _slug = normalize_linkedin(url)
    return canonical


def map_company_profile(raw: dict[str, Any]) -> dict[str, Any]:
    """Provider record → the snapshot payload we store.

    ``employee_count`` stays None when the field is absent. A zero would read
    as "this company has no staff", which is a claim the source did not make.
    """
    followers = _as_int(_first(raw, "followers", "followers_count", "follower_count"))
    employees = _as_int(_first(
        raw, "employees_in_linkedin", "company_size", "employees", "employee_count",
    ))
    return {
        "company_id": _first(raw, "company_id", "id", "linkedin_id"),
        "url": _first(raw, "url", "input_url", "company_url"),
        "name": _first(raw, "name", "company_name", "title"),
        "description": _first(raw, "about", "description"),
        "industry": _first(raw, "industries", "industry"),
        "specialties": _first(raw, "specialties"),
        "headquarters": _first(raw, "headquarters", "hq", "locations"),
        "country": _first(raw, "country_code", "country"),
        "founded": _as_int(_first(raw, "founded", "founded_year")),
        "website": _first(raw, "website", "company_website"),
        "employee_count": employees,
        "followers": followers,
        "employees_sample": _first(raw, "employees"),
        "affiliated": _first(raw, "affiliated", "affiliated_companies"),
        "observed_source": "brightdata_linkedin_profile",
    }


def _is_repost(raw: dict[str, Any]) -> bool:
    """Whether this record is a reshare rather than the company's own post.

    The provider returns a ``repost`` object on every record and fills it only
    when the post is a reshare, so its presence proves nothing — the fields
    inside it do.
    """
    repost = raw.get("repost")
    if not isinstance(repost, dict):
        return False
    return any(repost.get(k) for k in
               ("repost_id", "repost_url", "repost_text", "repost_user_id"))


def map_company_post(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Provider record → a raw article dict, mapped against real payloads.

    Field names verified against dataset ``gd_lyy3tktm25m4avu764`` on
    2026-08-20. Three of them are not what the docs imply:

    - The company is in ``discovery_input.url`` — the URL we asked for, which
      is exactly our stored identifier. There is no ``company_url``, and
      matching on anything else means every record is unattributable.
    - ``user_name`` is the display name ("7AI"); ``user_id`` is the slug.
    - ``headline`` is the human first line. ``title`` is hashtag soup
      ("#agenticsecurity #cybersecurity | 7AI").

    Returns None when the record carries no stable id or no text — an item we
    cannot dedup is worse than no item, because it lands once per run.
    """
    if raw.get("error") or raw.get("error_code"):
        # Bright Data reports dead pages and bad inputs as records.
        return None

    post_id = _first(raw, "id", "post_id", "urn", "post_urn")
    url = _first(raw, "url", "post_url", "link")
    if not post_id and url:
        post_id = str(url).rstrip("/").rsplit("/", 1)[-1] or None
    body = _first(raw, "post_text", "text", "content", "description")
    if not post_id or not body:
        return None

    company = _first(raw, "user_name", "company_name", "account_name", "author_name")

    # The company page this post was discovered from.
    company_url = None
    discovery = raw.get("discovery_input")
    if isinstance(discovery, dict):
        company_url = discovery.get("url")
    if not company_url:
        company_url = _first(raw, "use_url", "company_url", "user_url", "account_url")
    if not company_url:
        slug = _first(raw, "user_id")
        if slug:
            company_url = f"https://www.linkedin.com/company/{slug}"

    headline = _first(raw, "headline")
    if not headline:
        headline = str(body).strip().split("\n")[0]
    headline = str(headline)[:300]
    title = f"{company}: {headline}" if company else headline

    engagement = {
        "likes": _as_int(_first(raw, "num_likes", "likes", "reactions")),
        "comments": _as_int(_first(raw, "num_comments", "comments")),
        "shares": _as_int(_first(raw, "num_shares", "shares", "reposts")),
        "followers": _as_int(_first(raw, "user_followers")),
    }
    images = _first(raw, "images", "image", "thumbnail")
    if isinstance(images, list):
        images = images[0] if images else None

    return {
        "external_id": str(post_id),
        "url": url,
        "title": title,
        "content": str(body),
        "summary": str(body)[:1000],
        "author": company,
        "published_at": _as_dt(_first(raw, "date_posted", "post_date", "created_at")),
        "image_url": images if isinstance(images, str) else None,
        "engagement": {k: v for k, v in engagement.items() if v is not None},
        "company_url": company_url,
        "hashtags": _first(raw, "hashtags"),
        "post_type": _first(raw, "post_type"),
        # Both decide whether this is the company speaking. A repost is the
        # company amplifying somebody else, and a person's post is not the
        # company's at all — treating either as an owned claim would put words
        # in a vendor's mouth and give them relevance 1.0 while doing it.
        # Present in the dataset sample and previously discarded.
        "account_type": _first(raw, "account_type"),
        "is_repost": _is_repost(raw),
    }


def map_crunchbase_company(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Crunchbase record → the funding snapshot we store.

    Mapped against real payloads on 2026-08-20. **There are no dollar amounts
    in this dataset's public record** — ``funds_total`` is empty and the
    detailed rounds carry investors and titles but no ``money_raised``. So this
    cannot fill a registry's undisclosed figures. What it does carry is who
    backed the company, how many rounds, and Crunchbase's own momentum scores,
    which is arguably the more useful answer for a market view than a number.
    """
    if raw.get("error") or raw.get("error_code"):
        return None
    name = _first(raw, "name", "legal_name")
    if not name:
        return None

    rounds = raw.get("funding_rounds") if isinstance(raw.get("funding_rounds"), dict) else {}
    highlights = (raw.get("financials_highlights")
                  if isinstance(raw.get("financials_highlights"), dict) else {})

    investors: list[str] = []
    leads: list[str] = []
    for entry in (raw.get("funding_rounds_list") or []):
        if not isinstance(entry, dict):
            continue
        for lead in (entry.get("lead_investors") or []):
            if isinstance(lead, dict) and lead.get("name"):
                leads.append(lead["name"])
    for entry in (raw.get("investors") or []):
        if not isinstance(entry, dict):
            continue
        inv = entry.get("investor")
        if isinstance(inv, dict) and inv.get("value"):
            investors.append(inv["value"])

    linkedin = None
    for link in (raw.get("social_media_links") or raw.get("socila_media_urls") or []):
        if isinstance(link, str) and "linkedin.com/company" in link.lower():
            linkedin = link
            break

    return {
        "crunchbase_id": _first(raw, "company_id", "id"),
        "url": _first(raw, "url"),
        "name": name,
        "legal_name": _first(raw, "legal_name"),
        "website": _first(raw, "website"),
        "linkedin_url": linkedin,
        "about": _first(raw, "about"),
        "address": _first(raw, "address"),
        "country": _first(raw, "country_code"),
        # A band ("51-100"), not a count — do not compare it to a headcount.
        "employee_band": _first(raw, "num_employees"),
        "operating_status": _first(raw, "operating_status"),
        "ipo_status": _first(raw, "ipo_status"),
        "num_funding_rounds": _as_int(
            rounds.get("num_funding_rounds") or highlights.get("num_funding_rounds")),
        "last_funding_type": rounds.get("last_funding_type"),
        "num_investors": _as_int(
            _first(raw, "num_investors", "number_of_investors")
            or highlights.get("num_investors")),
        "investors": list(dict.fromkeys(investors))[:40],
        "lead_investors": list(dict.fromkeys(leads))[:20],
        "acquired_by": raw.get("acquired_by"),
        # Crunchbase's own momentum measures. Comparable across companies and
        # across time, which is what a market view needs.
        "cb_rank": _as_int(_first(raw, "cb_rank")),
        "growth_score": _as_int(_first(raw, "growth_score")),
        "growth_trend": _as_int(_first(raw, "growth_trend")),
        "heat_score": _as_int(_first(raw, "heat_score")),
        "heat_trend": _as_int(_first(raw, "heat_trend")),
        "founders": [f.get("value") for f in (raw.get("founders") or [])
                     if isinstance(f, dict) and f.get("value")],
        "recent_news": [
            {"date": n.get("date"), "title": n.get("title"),
             "publisher": n.get("publisher")}
            for n in (raw.get("news") or [])[:10] if isinstance(n, dict)
        ],
        "observed_source": "brightdata_crunchbase",
    }


def map_job_listing(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    """LinkedIn job listing → the hiring snapshot we store.

    What a vendor staffs says more about where it is investing than what its
    marketing says. Keyed on the posting id so a listing that stays open for
    weeks is one snapshot, not one per collection.
    """
    if raw.get("error") or raw.get("error_code"):
        return None
    posting_id = _first(raw, "job_posting_id", "title_id", "id")
    title = _first(raw, "job_title")
    if not posting_id or not title:
        return None

    company_url = _first(raw, "company_url")
    if not company_url:
        discovery = raw.get("discovery_input")
        if isinstance(discovery, dict):
            company_url = discovery.get("url")
    # The dataset dictionary documents company_id but not company_url, so a
    # record can arrive attributable by id and not by URL. A posting we cannot
    # tie back to a vendor is a paid record we throw away, and matching on
    # company_name instead is too loose — two vendors share a name often
    # enough that it would attribute a job to the wrong company.
    company_id = _first(raw, "company_id")

    return {
        "posting_id": str(posting_id),
        "title": title,
        "company": _first(raw, "company_name"),
        "company_url": company_url,
        "company_id": str(company_id) if company_id else None,
        "location": _first(raw, "job_location"),
        "seniority": _first(raw, "job_seniority_level"),
        "function": _first(raw, "job_function"),
        "employment_type": _first(raw, "job_employment_type"),
        "posted_date": _first(raw, "job_posted_date"),
        "url": _first(raw, "url", "apply_link"),
        "observed_source": "brightdata_linkedin_jobs",
    }


def map_zoominfo_company(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    """ZoomInfo record → the firmographic snapshot we store.

    Field names taken verbatim from the dataset's own published output
    dictionary (2026-08-22) — the one mapper in this file built from a
    schema rather than a real payload, because that is what was available.
    Read a real response before adding a field not listed there.
    """
    if raw.get("error") or raw.get("error_code"):
        return None
    name = raw.get("name")
    if not name:
        return None
    ceo = raw.get("ceo") if isinstance(raw.get("ceo"), dict) else {}
    return {
        "url": raw.get("url"),
        "name": name,
        "description": raw.get("description"),
        "revenue_usd": _as_int(raw.get("revenue")),
        "revenue_text": raw.get("revenue_text"),
        "employee_count": _as_int(raw.get("employees") or raw.get("total_employees")),
        "industry": raw.get("industry"),
        "headquarters": raw.get("headquarters"),
        "website": raw.get("website"),
        "stock_symbol": raw.get("stock_symbol"),
        "total_funding_usd": _as_int(raw.get("total_funding_amount")),
        "ceo_name": ceo.get("name"),
        "ceo_title": ceo.get("title"),
        "leadership": raw.get("leadership"),
        "tech_stack": raw.get("tech_stack"),
        "observed_source": "brightdata_zoominfo",
    }


def map_pitchbook_company(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    """PitchBook record → the funding snapshot we store.

    Unlike ``map_zoominfo_company``, no output sample was available for this
    one — only the request shape. Field names below are the most likely
    candidates, tried through ``_first`` so a near-miss still captures
    something, but none of them are verified. Read a real response and
    correct these before relying on the numbers.
    """
    if raw.get("error") or raw.get("error_code"):
        return None
    name = _first(raw, "name", "company_name")
    if not name:
        return None
    return {
        "url": _first(raw, "url", "input_url"),
        "name": name,
        "description": _first(raw, "description", "about"),
        "industry": _first(raw, "industry", "industries", "sector"),
        "headquarters": _first(raw, "headquarters", "hq", "location"),
        "employee_count": _as_int(_first(raw, "employees", "employee_count")),
        "total_funding_usd": _as_int(
            _first(raw, "total_raised", "total_funding", "total_funding_amount")),
        "last_round": _first(raw, "last_financing_deal_type", "last_round_type"),
        "investors": _first(raw, "investors"),
        "observed_source": "brightdata_pitchbook",
    }


def map_indeed_job(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Indeed job listing → the hiring snapshot we store.

    No output sample was available for this dataset either — field names are
    the most likely candidates, tried through ``_first``. Unverified; read a
    real response before trusting a count built from these.
    """
    if raw.get("error") or raw.get("error_code"):
        return None
    title = _first(raw, "job_title", "title")
    posting_id = _first(raw, "job_id", "id", "jk")
    if not title or not posting_id:
        return None
    return {
        "posting_id": str(posting_id),
        "title": title,
        "company": _first(raw, "company_name", "company", "employer"),
        "location": _first(raw, "location", "job_location"),
        "posted_date": _first(raw, "date_posted", "posted_date"),
        "url": _first(raw, "url", "job_link"),
        "salary": _first(raw, "salary", "salary_formatted"),
        "observed_source": "brightdata_indeed",
    }
