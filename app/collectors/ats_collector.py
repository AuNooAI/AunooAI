"""Job listings from the hiring system a company actually uses.

LinkedIn was our only source of job listings, and most of these companies do
not use it for hiring: 67 of 83 vendors in the SOC Automation market list
nothing there. Dropzone AI showed zero open roles and had eleven, because its
hiring runs through Greenhouse.

Scraping the careers page does not fix that. The stored text of
``dropzone.ai/careers`` contains the words "No items found." and not one job
title, because the page fetches its listings in the browser. The listings are
not in the HTML we were already keeping, so no extractor over that HTML could
ever have found them.

What does work is the applicant tracking system's own public job board API.
Greenhouse, Ashby, Lever, Workable, SmartRecruiters, Teamtailor and Recruitee
all publish one, unauthenticated, precisely so a job board can read it. That
gives structured records with stable ids, and both Greenhouse and Ashby carry a
real publication date — better data than the LinkedIn dataset, which never gave
a reliable one, and free, where every LinkedIn batch is billed.

So collection is two steps, mirroring ``vendor_web_discovery`` and
``vendor_web``:

1.  **Discovery** reads the careers page once and records which system the
    company uses, as a vendor identifier. This is the only step that needs the
    page HTML.
2.  **Collection** calls that system's API. It never touches the careers page
    again, so it is cheap, deterministic, and unaffected by a site redesign.

Attribution is exact, which is the thing Indeed could not give us: a board
token belongs to one company, so a listing read from ``ashbyhq.com/crogl``
is Crogl's by construction rather than by name matching.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, NamedTuple, Optional

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; AunooMarketMonitor/1.0)"
TIMEOUT = 25.0

# The identifier kind that records a discovered board, and the source keys.
IDENTIFIER_KIND = "ats_board"
SOURCE_JOBS = "ats_jobs"
SOURCE_DISCOVERY = "ats_discovery"

# Where a company's listings live is visible in its careers page as a link,
# iframe or script pointing at the board. Ordered because a page can mention
# more than one — a Greenhouse embed script beside a stale Lever link — and the
# embed is the one actually rendering the jobs.
#
# Each pattern's first group is the board token. Anchored on the host so a blog
# post that merely says the word "greenhouse" cannot produce a board.
_DETECTORS: List[tuple[str, str]] = [
    # The embed script carries the token in a query parameter, which is why a
    # naive path-segment match on this URL returns the literal "embed".
    ("greenhouse", r"greenhouse\.io/embed/job_board(?:/js)?\?for=([A-Za-z0-9_-]+)"),
    ("greenhouse", r"(?:job-)?boards\.greenhouse\.io/([A-Za-z0-9_-]+)"),
    ("greenhouse", r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)"),
    ("ashby",      r"jobs\.ashbyhq\.com/([A-Za-z0-9_.-]+)"),
    ("ashby",      r"api\.ashbyhq\.com/posting-api/job-board/([A-Za-z0-9_.-]+)"),
    ("lever",      r"jobs\.lever\.co/([A-Za-z0-9_-]+)"),
    ("lever",      r"api\.lever\.co/v0/postings/([A-Za-z0-9_-]+)"),
    ("workable",   r"apply\.workable\.com/(?:api/v\d+/widget/accounts/)?([A-Za-z0-9_-]+)"),
    ("smartrecruiters", r"careers\.smartrecruiters\.com/([A-Za-z0-9_-]+)"),
    ("teamtailor", r"([A-Za-z0-9_-]+)\.teamtailor\.com"),
    ("recruitee",  r"([A-Za-z0-9_-]+)\.recruitee\.com"),
]

# Tokens that are a path segment on the board host but not a company. Without
# this, "boards.greenhouse.io/embed/..." yields a board called "embed" and every
# such vendor collects the same wrong thing.
_NOT_TOKENS = frozenset({
    "embed", "job_board", "jobs", "api", "v1", "boards", "www", "posting-api",
})


class AtsBoard(NamedTuple):
    """One company's job board: which system, and its token."""
    system: str
    token: str

    @property
    def key(self) -> str:
        """How the board is stored as an identifier value."""
        return f"{self.system}:{self.token}"

    @property
    def board_url(self) -> Optional[str]:
        return _BOARD_URLS.get(self.system, lambda t: None)(self.token)


_BOARD_URLS: Dict[str, Any] = {
    "greenhouse": lambda t: f"https://job-boards.greenhouse.io/{t}",
    "ashby": lambda t: f"https://jobs.ashbyhq.com/{t}",
    "lever": lambda t: f"https://jobs.lever.co/{t}",
    "workable": lambda t: f"https://apply.workable.com/{t}/",
    "smartrecruiters": lambda t: f"https://careers.smartrecruiters.com/{t}",
    "teamtailor": lambda t: f"https://{t}.teamtailor.com/jobs",
    "recruitee": lambda t: f"https://{t}.recruitee.com/",
}

SUPPORTED_SYSTEMS = tuple(_BOARD_URLS)


def parse_board(value: Optional[str]) -> Optional[AtsBoard]:
    """Read back a stored ``system:token`` identifier."""
    if not value or ":" not in value:
        return None
    system, _, token = value.partition(":")
    system, token = system.strip().lower(), token.strip()
    if system not in _BOARD_URLS or not token:
        return None
    return AtsBoard(system, token)


def detect(html: str) -> Optional[AtsBoard]:
    """Which hiring system a careers page hands its listings to.

    Returns ``None`` rather than guessing. A vendor with no detectable board is
    reported as having no board, which is a fact about our coverage; inventing
    a token would produce confident listings belonging to somebody else.
    """
    if not html:
        return None
    for system, pattern in _DETECTORS:
        for match in re.finditer(pattern, html, re.I):
            token = match.group(1)
            if not token or token.lower() in _NOT_TOKENS:
                continue
            return AtsBoard(system, token)
    return None


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

# The job function groups the existing hiring analysis already uses, so an ATS
# listing lands in the same buckets as a LinkedIn one rather than starting a
# parallel vocabulary.
_FUNCTION_HINTS: List[tuple[str, tuple[str, ...]]] = [
    ("Engineering", ("engineer", "engineering", "developer", "sre", "devops",
                     "architect", "technical staff")),
    ("Security research", ("security research", "threat", "detection",
                           "malware", "reverse engineer", "red team")),
    ("Product", ("product manager", "product management", "ux", "designer",
                 "design")),
    ("Sales", ("sales", "account executive", "account manager",
               "business development", "revenue", "solutions engineer",
               "sales engineer")),
    ("Marketing", ("marketing", "content", "brand", "demand gen",
                   "communications")),
    ("Customer success", ("customer success", "support", "solutions architect",
                          "implementation", "deployment", "forward deployed")),
    ("Data science", ("data scientist", "machine learning", "ml engineer",
                      "ai engineer", "research scientist")),
    ("Operations", ("operations", "finance", "recruiter", "people",
                    "talent", "legal", "hr")),
]

# Ordered most senior first: "Senior Director" is a Director, not a Senior.
#
# Matched on word boundaries, not as substrings. "cto" as a substring matches
# inside "dire-cto-r", so every Director was being reported as an Executive —
# which is the kind of error that looks like a data problem rather than a regex
# one. Short acronyms are exactly where substring matching goes wrong.
_SENIORITY_HINTS: List[tuple[str, tuple[str, ...]]] = [
    ("Executive", ("chief", "cto", "ceo", "cfo", "ciso", "cro", "vp",
                   "vice president", "head of", "founder")),
    ("Director", ("director",)),
    ("Manager", ("manager", "lead", "principal", "staff")),
    ("Senior", ("senior", "sr")),
    ("Entry", ("intern", "junior", "graduate", "associate")),
]


def _function_of(title: str, department: Optional[str]) -> str:
    """Best guess at the job family, from the title then the department.

    The title first because a department called "G&A" says nothing useful while
    the title almost always does.
    """
    haystack = f"{title or ''} {department or ''}".lower()
    for label, hints in _FUNCTION_HINTS:
        if any(h in haystack for h in hints):
            return label
    return department.strip() if department else "Other"


def _has_word(haystack: str, needle: str) -> bool:
    """Whole-word match, so a short acronym cannot hide inside a longer word."""
    return re.search(rf"(?<![a-z]){re.escape(needle)}(?![a-z])",
                     haystack) is not None


def _seniority_of(title: str) -> Optional[str]:
    low = (title or "").lower()
    for label, hints in _SENIORITY_HINTS:
        if any(_has_word(low, h) for h in hints):
            return label
    return None


def _iso(value: Any) -> Optional[str]:
    """A date we can store, or nothing. Never today's date as a stand-in.

    A missing publication date filled in with the collection time would make
    every listing look posted the day we found it, which is exactly the
    "first observed is not opened" error one level down.
    """
    if not value:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        cleaned = text_value.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).astimezone(
            timezone.utc).isoformat()
    except ValueError:
        # Some boards send epoch milliseconds.
        try:
            return datetime.fromtimestamp(
                int(text_value) / 1000, tz=timezone.utc).isoformat()
        except (ValueError, OSError, OverflowError):
            return None


def _posting(board: AtsBoard, *, item_id: str, title: str,
             location: Optional[str], department: Optional[str],
             employment_type: Optional[str], url: Optional[str],
             posted: Optional[str], remote: Optional[bool] = None,
             company: Optional[str] = None) -> Dict[str, Any]:
    """One listing in the shape the rest of the system already reads.

    Same keys as a LinkedIn job snapshot, so the counts, the drill-down and the
    newly/no-longer-observed rules work on these without changes.

    ``posting_id`` is namespaced by system and board. Two systems can issue the
    same integer id, and an unnamespaced collision would silently merge two
    companies' listings into one.
    """
    return {
        "posting_id": f"{board.system}:{board.token}:{item_id}",
        "title": (title or "").strip(),
        "location": (location or "").strip() or None,
        "function": department,
        "function_hint": _function_of(title, department),
        "seniority": _seniority_of(title),
        "employment_type": employment_type,
        "url": url,
        "posted_date": posted,
        "remote": remote,
        "company": company,
        "company_url": board.board_url,
        # Which board it came from, so a reader can tell an ATS listing from a
        # LinkedIn one without inferring it from the id.
        "observed_source": f"ats:{board.system}",
        "ats_system": board.system,
        "ats_board": board.token,
    }


# ---------------------------------------------------------------------------
# One adapter per system
# ---------------------------------------------------------------------------

def _greenhouse(board: AtsBoard, payload: Any) -> List[Dict[str, Any]]:
    out = []
    for job in (payload or {}).get("jobs", []) or []:
        out.append(_posting(
            board, item_id=str(job.get("id")), title=job.get("title") or "",
            location=(job.get("location") or {}).get("name"),
            department=next((d.get("name") for d in (job.get("departments") or [])
                             if d.get("name")), None),
            employment_type=None, url=job.get("absolute_url"),
            posted=_iso(job.get("first_published") or job.get("updated_at")),
            company=job.get("company_name")))
    return out


def _ashby(board: AtsBoard, payload: Any) -> List[Dict[str, Any]]:
    out = []
    for job in (payload or {}).get("jobs", []) or []:
        # isListed false is a job the company has taken off its own board, so
        # showing it would contradict the board a reader can check.
        if job.get("isListed") is False:
            continue
        out.append(_posting(
            board, item_id=str(job.get("id")), title=job.get("title") or "",
            location=job.get("location"),
            department=job.get("department") or job.get("team"),
            employment_type=job.get("employmentType"),
            url=job.get("jobUrl") or job.get("applyUrl"),
            posted=_iso(job.get("publishedAt")),
            remote=job.get("isRemote")))
    return out


def _lever(board: AtsBoard, payload: Any) -> List[Dict[str, Any]]:
    out = []
    for job in payload or []:
        cats = job.get("categories") or {}
        out.append(_posting(
            board, item_id=str(job.get("id")), title=job.get("text") or "",
            location=cats.get("location"), department=cats.get("team"),
            employment_type=cats.get("commitment"),
            url=job.get("hostedUrl") or job.get("applyUrl"),
            posted=_iso(job.get("createdAt"))))
    return out


def _workable(board: AtsBoard, payload: Any) -> List[Dict[str, Any]]:
    out = []
    for job in (payload or {}).get("jobs", []) or []:
        city = job.get("city") or ""
        country = job.get("country") or ""
        out.append(_posting(
            board, item_id=str(job.get("shortcode") or job.get("id")),
            title=job.get("title") or "",
            location=", ".join(p for p in (city, country) if p) or None,
            department=job.get("department"),
            employment_type=job.get("employment_type"),
            url=job.get("url") or job.get("application_url"),
            posted=_iso(job.get("published_on") or job.get("created_at")),
            remote=job.get("telecommuting")))
    return out


def _smartrecruiters(board: AtsBoard, payload: Any) -> List[Dict[str, Any]]:
    out = []
    for job in (payload or {}).get("content", []) or []:
        loc = job.get("location") or {}
        out.append(_posting(
            board, item_id=str(job.get("id")), title=job.get("name") or "",
            location=", ".join(p for p in (loc.get("city"), loc.get("country"))
                               if p) or None,
            department=(job.get("department") or {}).get("label"),
            employment_type=(job.get("typeOfEmployment") or {}).get("label"),
            url=job.get("ref") or job.get("applyUrl"),
            posted=_iso(job.get("releasedDate"))))
    return out


def _schema_location(job_location: Any) -> Optional[str]:
    """A place name out of a schema.org jobLocation.

    The shape is a Place, or a list of them, each wrapping a PostalAddress
    whose fields are individually optional — so this assembles whatever is
    present rather than assuming a locality exists.
    """
    places = job_location if isinstance(job_location, list) else [job_location]
    for place in places:
        if not isinstance(place, dict):
            continue
        address = place.get("address")
        if not isinstance(address, dict):
            continue
        parts = [address.get(k) for k in
                 ("addressLocality", "addressRegion", "addressCountry")]
        joined = ", ".join(str(p) for p in parts if p)
        if joined:
            return joined
    return None


def _teamtailor(board: AtsBoard, payload: Any) -> List[Dict[str, Any]]:
    """A JSON Feed, where each item embeds a schema.org JobPosting.

    The feed's own fields carry only a title, a URL and a date; the location,
    employment type and department are in the embedded ``_jobposting``. An
    earlier version read a ``_teamtailor`` key that does not exist, so every
    listing came back with no location.
    """
    out = []
    for item in (payload or {}).get("items", []) or []:
        posting = item.get("_jobposting") or {}
        out.append(_posting(
            board, item_id=str(item.get("id")),
            title=item.get("title") or posting.get("title") or "",
            location=_schema_location(posting.get("jobLocation")),
            department=posting.get("occupationalCategory")
                       or posting.get("industry"),
            employment_type=posting.get("employmentType"),
            url=item.get("url") or item.get("external_url"),
            posted=_iso(item.get("date_published")
                        or posting.get("datePosted"))))
    return out


def _recruitee(board: AtsBoard, payload: Any) -> List[Dict[str, Any]]:
    out = []
    for job in (payload or {}).get("offers", []) or []:
        out.append(_posting(
            board, item_id=str(job.get("id")), title=job.get("title") or "",
            location=job.get("location") or job.get("city"),
            department=job.get("department"),
            employment_type=job.get("employment_type_code"),
            url=job.get("careers_url") or job.get("careers_apply_url"),
            posted=_iso(job.get("published_at"))))
    return out


class _Adapter(NamedTuple):
    url: Any                       # token -> request URL
    parse: Any                     # (board, payload) -> postings


ADAPTERS: Dict[str, _Adapter] = {
    "greenhouse": _Adapter(
        lambda t: f"https://boards-api.greenhouse.io/v1/boards/{t}/jobs",
        _greenhouse),
    "ashby": _Adapter(
        lambda t: f"https://api.ashbyhq.com/posting-api/job-board/{t}",
        _ashby),
    "lever": _Adapter(
        lambda t: f"https://api.lever.co/v0/postings/{t}?mode=json",
        _lever),
    "workable": _Adapter(
        lambda t: (f"https://apply.workable.com/api/v1/widget/accounts/{t}"
                   "?details=true"),
        _workable),
    "smartrecruiters": _Adapter(
        lambda t: f"https://api.smartrecruiters.com/v1/companies/{t}/postings",
        _smartrecruiters),
    "teamtailor": _Adapter(
        lambda t: f"https://{t}.teamtailor.com/jobs.json",
        _teamtailor),
    "recruitee": _Adapter(
        lambda t: f"https://{t}.recruitee.com/api/offers/",
        _recruitee),
}


class AtsError(RuntimeError):
    """The board could not be read. Carries whether retrying is worthwhile."""

    def __init__(self, message: str, *, retryable: bool = True,
                 code: str = "ats_error"):
        super().__init__(message)
        self.retryable = retryable
        self.code = code


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=TIMEOUT, follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"})


async def fetch_careers_html(url: str) -> Optional[str]:
    """The careers page, for discovery only.

    A 403 is common — several of these sites refuse an unfamiliar client — and
    it is not an error worth failing a run over. It means we cannot discover a
    board this way, which is recorded as not-found rather than as a failure.
    """
    async with _client() as client:
        try:
            response = await client.get(
                url, headers={"Accept": "text/html,application/xhtml+xml"})
        except httpx.HTTPError as exc:
            logger.info("ats discovery: %s unreachable — %s", url, exc)
            return None
        if response.status_code >= 400:
            logger.info("ats discovery: %s returned %s", url,
                        response.status_code)
            return None
        return response.text


async def discover_board(urls: List[str]) -> Optional[AtsBoard]:
    """The first hiring board found across a vendor's candidate pages.

    Lives here rather than in the sweep so the sweep's vendor loop holds no
    open transaction across these fetches. This function touches no database,
    which is the point: the caller commits before calling it and has nothing to
    lose while it runs.
    """
    for url in urls:
        try:
            html = await fetch_careers_html(url)
        except Exception:                                         # noqa: BLE001
            logger.info("ats discovery: %s failed", url)
            continue
        if not html:
            continue
        board = detect(html)
        if board:
            return board
    return None


async def fetch_jobs(board: AtsBoard) -> List[Dict[str, Any]]:
    """Every listing on one board, normalised.

    Raises :class:`AtsError` rather than returning an empty list on failure. An
    empty list is a real answer — a company with nothing open — and conflating
    it with a failed request is exactly how a zero stops meaning anything.
    """
    adapter = ADAPTERS.get(board.system)
    if adapter is None:
        raise AtsError(f"no adapter for {board.system}", retryable=False,
                       code="unsupported_system")

    async with _client() as client:
        try:
            response = await client.get(adapter.url(board.token))
        except httpx.HTTPError as exc:
            raise AtsError(f"{board.system} unreachable: {exc}",
                           code="unreachable") from exc

    if response.status_code == 404:
        # The board moved or the token is wrong. Retrying will not fix it.
        raise AtsError(f"{board.key} does not exist", retryable=False,
                       code="board_not_found")
    if response.status_code == 429:
        raise AtsError(f"{board.system} rate limited", code="rate_limited")
    if response.status_code >= 400:
        raise AtsError(f"{board.system} returned {response.status_code}",
                       code=f"http_{response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise AtsError(f"{board.system} returned non-JSON",
                       code="bad_payload") from exc

    postings = adapter.parse(board, payload)
    # A posting with no id cannot be tracked between runs, so it would appear
    # new every time and never be seen to disappear.
    return [p for p in postings
            if p.get("posting_id") and p.get("title")
            and not p["posting_id"].endswith(":None")]
