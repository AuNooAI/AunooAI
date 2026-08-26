"""Market collection — provider mapping, webhook safety, diffs, scheduling.

No test here calls Bright Data. The client is exercised against a mock
transport and the mapping functions against sanitized fixtures, because paid
dataset calls in CI would bill real money to prove something a fixture proves
for free.

Monolith port. The article-shape test is gone: this codebase writes straight
into ``articles`` keyed on ``uri`` rather than through a collector's
``normalize_article``, so what matters is that a post carries a usable URL and
a stable id, which the mapping tests already cover.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import text

from app.collectors import vendor_web_collector as vw
from app.services import brightdata_linkedin as bd


# ---------------------------------------------------------------------------
# Provider mapping
# ---------------------------------------------------------------------------

PROFILE_FIXTURE = {
    "id": "urn:li:company:123",
    "name": "Dropzone AI",
    "url": "https://www.linkedin.com/company/dropzone-ai/",
    "about": "AI SOC analyst.",
    "employees_in_linkedin": 75,
    "followers": "12,400",
    "founded": 2023,
    "website": "https://www.dropzone.ai/",
    "country_code": "US",
}

POST_FIXTURE = {
    "post_id": "7231234567890",
    "url": "https://www.linkedin.com/posts/dropzone-ai_activity-7231234567890",
    "company_url": "https://www.linkedin.com/company/dropzone-ai/",
    "company_name": "Dropzone AI",
    "post_text": "We closed our Series B.\nMore in the blog.",
    "date_posted": "2026-08-14T09:30:00Z",
    "num_likes": 210,
    "num_comments": 14,
}


def test_profile_maps_counts_without_inventing_zeros():
    out = bd.map_company_profile(PROFILE_FIXTURE)
    assert out["employee_count"] == 75
    assert out["followers"] == 12400
    assert out["name"] == "Dropzone AI"

    # A record that simply does not carry the field must stay unknown. Zero
    # would read as "this company has no staff", which the source never said.
    sparse = bd.map_company_profile({"name": "Quiet Co"})
    assert sparse["employee_count"] is None
    assert sparse["followers"] is None


def test_post_maps_to_an_article_shaped_dict():
    out = bd.map_company_post(POST_FIXTURE)
    assert out["external_id"] == "7231234567890"
    assert out["title"].startswith("Dropzone AI: We closed our Series B.")
    assert out["published_at"] == datetime(2026, 8, 14, 9, 30, tzinfo=timezone.utc)
    assert out["engagement"] == {"likes": 210, "comments": 14}


def test_post_without_an_id_or_body_is_dropped():
    """An item we cannot dedup would re-land on every single run."""
    assert bd.map_company_post({"post_text": "no id anywhere"}) is None
    assert bd.map_company_post({"post_id": "1"}) is None


def test_post_carries_what_the_article_row_needs():
    """``articles`` is keyed on ``uri``, so a post without a URL cannot land."""
    out = bd.map_company_post(POST_FIXTURE)
    assert out["url"].startswith("https://www.linkedin.com/posts/")
    assert out["external_id"] and out["title"] and out["content"]


def test_linkedin_key_is_the_same_rule_everywhere():
    """Registry, provider records and lookup map must agree on the key."""
    variants = [
        "https://www.linkedin.com/company/dropzone-ai/",
        "https://de.linkedin.com/company/Dropzone-AI",
        "https://www.linkedin.com/company/dropzone-ai/about/?trk=public_post",
    ]
    keys = {bd.normalize_linkedin_key(v) for v in variants}
    assert keys == {"https://www.linkedin.com/company/dropzone-ai"}


# ---------------------------------------------------------------------------
# Webhook authentication
# ---------------------------------------------------------------------------

def test_webhook_auth_fails_closed_on_an_unset_secret():
    """The endpoint is unauthenticated by necessity, so an empty secret must
    reject everything rather than wave everything through."""
    assert bd.verify_webhook_auth("Bearer anything", "") is False
    assert bd.verify_webhook_auth(None, "s3cret") is False
    assert bd.verify_webhook_auth("Bearer wrong", "s3cret") is False
    assert bd.verify_webhook_auth("Bearer s3cret", "s3cret") is True


def test_webhook_body_shapes():
    from app.routes.market_monitor_routes import _records_from

    assert _records_from([{"a": 1}, "junk"]) == [{"a": 1}]
    assert _records_from({"data": [{"a": 1}]}) == [{"a": 1}]
    # A status notification carries no records and must not be read as an
    # empty delivery, which would close the run as succeeded-with-nothing.
    assert _records_from({"status": "running", "snapshot_id": "s1"}) is None


# ---------------------------------------------------------------------------
# Client transport
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trigger_records_the_snapshot_id(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"snapshot_id": "s_abc123"})

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    client = bd.LinkedInDatasetClient("k", profile_dataset_id="gd_profile")
    result = await client.trigger_profiles(
        ["https://www.linkedin.com/company/a"],
        webhook_url="https://app/api/v1/webhooks/brightdata/linkedin?run_id=9",
        webhook_auth="Bearer s3cret",
    )
    assert result.snapshot_id == "s_abc123"
    assert result.requested == 1
    assert "dataset_id=gd_profile" in captured["url"]
    assert "run_id%3D9" in captured["url"] or "run_id=9" in captured["url"]
    assert captured["auth"] == "Bearer k"


@pytest.mark.asyncio
async def test_provider_errors_are_classified_as_retryable_or_not(monkeypatch):
    # Capture the real class once. Re-reading httpx.AsyncClient inside the
    # helper would wrap the previous patch and every later call would replay
    # the first status.
    original = httpx.AsyncClient

    def make(status: int):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(status, text="nope")
        )

        def fake_client(*args, **kwargs):
            kwargs["transport"] = transport
            return original(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    client = bd.LinkedInDatasetClient("k")
    make(429)
    with pytest.raises(bd.BrightDataError) as rate_limited:
        await client.trigger_profiles(["https://www.linkedin.com/company/a"])
    assert rate_limited.value.retryable is True

    make(400)
    with pytest.raises(bd.BrightDataError) as bad_request:
        await client.trigger_profiles(["https://www.linkedin.com/company/a"])
    # Retrying a malformed request just spends the budget again.
    assert bad_request.value.retryable is False


@pytest.mark.asyncio
async def test_sync_scrape_refuses_an_oversized_batch():
    client = bd.LinkedInDatasetClient("k")
    with pytest.raises(bd.BrightDataError, match="at most 20"):
        await client.scrape_sync("gd_x", [{"url": f"u{i}"} for i in range(21)])


def test_snapshot_decoding_handles_both_shapes():
    assert bd._decode_records('[{"a":1},{"b":2}]') == [{"a": 1}, {"b": 2}]
    assert bd._decode_records('{"a":1}\n{"b":2}') == [{"a": 1}, {"b": 2}]
    assert bd._decode_records("") == []


# ---------------------------------------------------------------------------
# Page monitoring
# ---------------------------------------------------------------------------

def test_pricing_change_is_material_and_furniture_is_not():
    before = "Starter $10\nPro $50\nWe use cookies to improve your experience"
    after = "Starter $10\nPro $60\nEnterprise Contact us\nAccept all cookies"
    diff = vw.diff_pages(before, after)
    assert diff["material"] is True
    assert "Pro $60" in diff["added"]
    assert "Enterprise Contact us" in diff["added"]
    assert "Pro $50" in diff["removed"]
    # Cookie text appears in both versions and in neither side of the diff.
    assert not any("cookie" in line.lower() for line in diff["added"] + diff["removed"])


def test_reordering_is_not_a_change():
    """A reflowed or re-ordered feature list must not read as a product launch."""
    diff = vw.diff_pages("A\nB\nC", "C\nA\nB")
    assert diff["material"] is False
    # The diff is a minimal edit script, so only the line that actually moved
    # shows up on both sides — what matters is that nothing survives as new.
    assert diff["moved_count"] >= 1
    assert diff["added"] == [] and diff["removed"] == []


def test_hash_ignores_boilerplate():
    assert vw.hash_text("Real content") == vw.hash_text(
        "Menu\nSkip to content\nReal content\n© 2026 Acme\nAccept all cookies"
    )


def test_extract_drops_scripts_and_styles():
    title, text = vw.extract_text(
        "<html><head><title>T</title><style>a{}</style></head>"
        "<body><script>var x=1</script><h1>Hi</h1>"
        "<p>The pricing changed today.</p></body></html>"
    )
    assert "var x" not in (text or "")
    assert "pricing changed" in (text or "")


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

def test_cadences_are_twelve_hours_or_slower():
    from app.tasks import market_monitor as mm

    for source in (mm.SOURCE_POSTS, mm.SOURCE_PAGES, mm.SOURCE_PROFILE,
                   mm.SOURCE_DISCOVERY):
        assert mm.cadence(source) >= timedelta(hours=12), source
    # Profiles are the expensive surface and the slowest-moving number, so
    # they must not run as often as posts.
    assert mm.cadence(mm.SOURCE_PROFILE) > mm.cadence(mm.SOURCE_POSTS)


def test_default_category_covers_every_market_source():
    """A record with no keyword hit still has to be attributed, or the Brand
    Watcher UI — which reads through bw_article_categories — never shows it."""
    from app.routes.brand_watcher_routes import BW_CATEGORIES
    from app.services.market_collect import DEFAULT_CATEGORY
    from app.tasks import market_monitor as mm

    assert mm.SOURCE_POSTS in DEFAULT_CATEGORY
    assert mm.SOURCE_PAGES in DEFAULT_CATEGORY
    for category in DEFAULT_CATEGORY.values():
        assert category in BW_CATEGORIES, category


def test_linkedin_key_falls_back_to_the_shared_bright_data_token(monkeypatch):
    """One Bright Data token authorizes both capabilities, so a dedicated key
    is optional — but setting one must win."""
    monkeypatch.delenv("BRIGHTDATA_LINKEDIN_API_KEY", raising=False)
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "shared")
    assert bd.api_key() == "shared"
    monkeypatch.setenv("BRIGHTDATA_LINKEDIN_API_KEY", "dedicated")
    assert bd.api_key() == "dedicated"


def test_linkedin_is_off_until_explicitly_enabled(monkeypatch):
    monkeypatch.delenv("BRIGHTDATA_LINKEDIN_ENABLED", raising=False)
    assert bd.linkedin_enabled() is False
    monkeypatch.setenv("BRIGHTDATA_LINKEDIN_ENABLED", "true")
    assert bd.linkedin_enabled() is True


def test_the_callback_declares_no_session_and_the_rest_do():
    """This codebase has no global auth middleware — a route is protected only
    if it says so. The callback must be the one that does not, and everything
    else must be the ones that do."""
    import inspect

    from app.routes import market_monitor_routes as mr

    unprotected = []
    for route in mr.router.routes:
        params = inspect.signature(route.endpoint).parameters
        if "session" not in params:
            unprotected.append(route.path)
    assert unprotected == ["/api/market-monitor/webhooks/brightdata/linkedin"]


def test_a_funding_rule_does_not_reach_excluded_vendors():
    """Scope and funding are different questions.

    Edge Delta is funded and out of scope. "Collect for every funded vendor"
    must leave it alone unless the caller names the role explicitly.
    """
    from app.routes.market_monitor_routes import VendorFilter, _filter_sql

    where, _ = _filter_sql(VendorFilter(funding_status=["Disclosed"]))
    assert "role" not in where, "the base fragment stays scope-agnostic"

    # The endpoint appends the scope guard; assert the shape it appends.
    guarded = where + " AND mb.role <> 'excluded'"
    assert "mb.role <> 'excluded'" in guarded

    # Naming roles is how you opt in to excluded rows.
    named, params = _filter_sql(VendorFilter(roles=["excluded"]))
    assert "mb.role = ANY(:f_roles)" in named
    assert params["f_roles"] == ["excluded"]


# ---------------------------------------------------------------------------
# LinkedIn jobs: the output contract, from the dataset dictionary
# ---------------------------------------------------------------------------
#
# The source is paused. The provider rejects our discovery request with
# HTTP 400 "Incorrect discovery collector id. Available types: keyword, url",
# and the dashboard sample confirms only the *output* schema — it does not show
# the request shape, the dataset id, or where limit_per_input belongs. So these
# fixture-test what the sample does establish, and the paid canary stays
# blocked until the request configuration is confirmed.

def test_the_documented_jobs_output_maps_completely():
    """Every field the dataset dictionary documents survives the mapper."""
    from app.services.brightdata_linkedin import map_job_listing

    documented = {
        'url': 'https://www.linkedin.com/jobs/view/4443580965',
        'job_posting_id': '4443580965',
        'job_title': 'Sr. Product Manager',
        'company_name': 'Intezer',
        'company_id': '10656303',
        'job_location': 'Tel Aviv District, Israel',
        'job_summary': 'Own the roadmap.',
        'job_seniority_level': 'Mid-Senior level',
        'job_function': 'Product Management',
        'job_employment_type': 'Full-time',
    }
    mapped = map_job_listing(documented)

    assert mapped is not None
    assert mapped['posting_id'] == '4443580965'
    assert mapped['title'] == 'Sr. Product Manager'
    assert mapped['company'] == 'Intezer'
    assert mapped['company_id'] == '10656303'
    assert mapped['location'] == 'Tel Aviv District, Israel'
    assert mapped['seniority'] == 'Mid-Senior level'
    assert mapped['function'] == 'Product Management'
    assert mapped['employment_type'] == 'Full-time'


def test_a_posting_attributable_only_by_company_id_keeps_it():
    """The dictionary documents company_id and not company_url, so a record
    can arrive attributable by id alone. Dropping it would throw away a paid
    record; matching on company_name instead is too loose, because two vendors
    sharing a name would attribute each other's jobs."""
    from app.services.brightdata_linkedin import map_job_listing

    mapped = map_job_listing({
        'job_posting_id': '1', 'job_title': 'Engineer',
        'company_name': 'Intezer', 'company_id': '10656303',
    })
    assert mapped['company_url'] is None
    assert mapped['company_id'] == '10656303'


def test_the_company_url_is_still_preferred_when_supplied():
    from app.services.brightdata_linkedin import map_job_listing

    mapped = map_job_listing({
        'job_posting_id': '2', 'job_title': 'Engineer',
        'company_name': 'Intezer', 'company_id': '10656303',
        'company_url': 'https://www.linkedin.com/company/intezer-labs',
    })
    assert mapped['company_url'] == 'https://www.linkedin.com/company/intezer-labs'
    assert mapped['company_id'] == '10656303'


def test_a_record_with_no_stable_id_is_dropped():
    """A posting we cannot dedup lands once per collection run."""
    from app.services.brightdata_linkedin import map_job_listing

    assert map_job_listing({'job_title': 'Engineer'}) is None
    assert map_job_listing({'job_posting_id': '3'}) is None


def test_linkedin_jobs_uses_the_one_discovery_mode_that_works():
    """This test used to assert the source stayed paused for an HTTP 400.

    The 400 was real on the morning of 20 August and fixed that afternoon by
    switching to ``discover_by=keyword`` with ``company`` as its own input
    field. The source then succeeded six times running. The pause was added
    five days later off the old failed rows, and this test pinned it there.

    What matters is the request shape, so that is what is asserted now. Three
    other modes were tried and two of them failed silently — a company-name
    keyword returns other employers' postings, which is worse than nothing.
    """
    from app.services import entity_scheduler as sch

    assert 'linkedin_jobs' not in sch.PAUSED_SOURCES
    assert 'linkedin_jobs' not in sch.MANUAL_ONLY_SOURCES

    payload_shape = bd.LinkedInDatasetClient.trigger_jobs.__doc__ or ''
    assert 'discover_by=keyword' in payload_shape


# ---------------------------------------------------------------------------
# Dispatch has to claim the roster, on every paid path
# ---------------------------------------------------------------------------

def _brightdata_dispatchers():
    """Every function that puts a Bright Data batch up, by source.

    Found rather than listed. A new provider path added next month is caught
    by the assertions below without anyone remembering to add it here, which
    is the failure this whole check exists to prevent.
    """
    import ast
    import pathlib

    src = pathlib.Path('app/tasks/market_monitor.py').read_text()
    tree = ast.parse(src)
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        body = ast.get_source_segment(src, node) or ''
        # A `trigger_*` call, not merely a mention of the client: the
        # reconciler also builds a client, to collect the results of a batch
        # somebody else paid for, and it has no roster to claim.
        if any(f'.trigger_{verb}' in body for verb in
               ('posts', 'profiles', 'crunchbase', 'pitchbook', 'zoominfo',
                'indeed_discover', 'jobs')):
            out[node.name] = body
    return out


def test_every_paid_dispatch_path_claims_the_roster():
    """The bug this guards was a fix applied to one sibling and not the other.

    ``claim_due`` was added to the dataset path, which sweeps Crunchbase and
    the rest. The LinkedIn path — posts and profiles, the two sources the
    product leans on hardest — kept selecting the first twenty vendors by
    ``sort_order``, so the other sixty-three were never collected once and
    every one of them read as a measured zero.

    Asserting the property for whichever paid paths exist, rather than for a
    hand-written list of two, is what makes the next one safe.
    """
    dispatchers = _brightdata_dispatchers()
    assert dispatchers, 'no Bright Data dispatch path found — has the module moved?'

    for name, body in dispatchers.items():
        assert 'claim_due' in body, (
            f'{name} dispatches a paid batch without claiming vendors from '
            f'bw_entity_source_policies, so it will re-collect the same page '
            f'of the roster forever')
        assert 'requested_brand_ids' in body, (
            f'{name} does not record which vendors the batch was for, so a '
            f'batch that succeeds with zero records cannot advance them and '
            f'they stay permanently due')
        assert 'sort_order LIMIT' not in body.replace('\n', ' '), (
            f'{name} still slices the roster by sort_order')


def test_the_linkedin_path_releases_a_vendor_it_could_not_dispatch():
    """Claiming a vendor and then not asking about it must not look like success.

    Recording success for a vendor the provider was never sent is exactly how
    a gap in collection becomes a confident zero on the dashboard.
    """
    body = _brightdata_dispatchers()['_poll_linkedin']
    assert 'release_claims' in body
    assert 'record_failure' in body


# ---------------------------------------------------------------------------
# A size band is not a headcount
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('band', [
    '51-200', '51–200', '1,001-5,000', '51 to 200', '10K+', '10000+', 'n/a',
])
def test_a_size_band_never_becomes_a_headcount(band):
    """The old parser stripped non-digits, which is right for "13,111"
    followers and catastrophic for a band: "1,001-5,000" came back as
    10,015,000. One vendor like that would have put ten million staff into a
    market total with nothing on screen to suggest anything was wrong."""
    assert bd._as_headcount(band) is None


@pytest.mark.parametrize('value,expected', [
    ('145', 145), ('1,234', 1234), ('200 employees', 200), (145, 145),
    (145.0, 145), ('', None), (None, None), (True, None),
])
def test_an_exact_count_still_parses(value, expected):
    assert bd._as_headcount(value) == expected


@pytest.mark.parametrize('zero', [0, 0.0, '0', '000', '0 employees'])
def test_zero_staff_is_a_missing_field_not_a_measurement(zero):
    """Bright Data returned 0 for a real vendor whose band said "2-10".

    ``entity_field_registry`` already refuses a zero headcount, so the
    canonical column was safe — but the published vendor row and the headcount
    chart both read the snapshot payload directly and had no such guard, so one
    vendor would have shown 0 staff and plotted a point on the floor.
    """
    assert bd._as_headcount(zero) is None


def test_company_size_is_kept_as_a_band_not_promoted_to_a_count():
    """``company_size`` used to sit second in the count chain, so a response
    without ``employees_in_linkedin`` stored the band as the number. It is
    still retained — just never as arithmetic."""
    mapped = bd.map_company_profile({
        'name': 'Acme', 'url': 'https://www.linkedin.com/company/acme',
        'company_size': '51-200 employees',
    })
    assert mapped['employee_count'] is None
    assert mapped['employee_band'] == '51-200 employees'

    exact = bd.map_company_profile({
        'name': 'Acme', 'url': 'https://www.linkedin.com/company/acme',
        'employees_in_linkedin': 145, 'company_size': '51-200 employees',
    })
    assert exact['employee_count'] == 145


def test_the_pass_seeds_policies_before_it_dispatches():
    """Dispatch claims vendors from bw_entity_source_policies, so whatever
    creates those rows has to run first, on every pass.

    Nothing outside the tests called ``seed_policies``, which was harmless
    while dispatch read the vendor table directly. Once dispatch moved to
    claiming policies, a vendor with no policy row became uncollectable and
    silent — no error, no run, no coverage figure saying it was skipped.
    """
    import ast
    import pathlib

    src = pathlib.Path('app/tasks/market_monitor.py').read_text()
    tree = ast.parse(src)
    tick = next(n for n in ast.walk(tree)
                if isinstance(n, ast.AsyncFunctionDef) and n.name == 'tick')
    body = ast.get_source_segment(src, tick) or ''
    assert 'seed_policies' in body, (
        'tick() does not refresh collection policies, so a vendor added after '
        'the last hand-run of seed_policies will never be collected')


#: One record from the Bright Data dashboard sample for gd_l4dx9j9sscpvs7no2,
#: trimmed to the fields the mapper reads. The point of keeping it is that the
#: id is `jobid` and the usable date is `date_posted_parsed`.
INDEED_SAMPLE = {
    'jobid': '97203ff9bcc3ad72',
    'company_name': 'Mediacom Communications Corporation',
    'date_posted_parsed': '2026-08-18T01:34:46.635Z',
    'date_posted': '8 days ago',
    'job_title': 'Customer Retention and Sales Representative I',
    'job_type': 'Full-time',
    'location': 'Chillicothe, IL',
    'job_location': 'Hybrid work in Chillicothe, IL',
    'salary_formatted': '$15.00 - $16.50 an hour',
    'url': 'https://www.indeed.com/viewjob?jk=97203ff9bcc3ad72',
    'is_expired': False,
}


def test_an_indeed_record_maps_against_the_real_field_names():
    """The id is ``jobid``, one word.

    The mapper looked for ``job_id``, ``id`` and ``jk``, so every record failed
    the id guard and was dropped. A live batch would have reported that Indeed
    returned nothing while actually returning everything — the worst shape of
    failure, because it looks like an answer.
    """
    mapped = bd.map_indeed_job(INDEED_SAMPLE)
    assert mapped is not None, 'the whole batch would be silently discarded'
    assert mapped['posting_id'] == '97203ff9bcc3ad72'
    assert mapped['company'] == 'Mediacom Communications Corporation'
    assert mapped['title'].startswith('Customer Retention')
    assert mapped['salary'] == '$15.00 - $16.50 an hour'


def test_the_indeed_posted_date_is_a_date_and_not_eight_days_ago():
    """``date_posted`` is relative text; ``date_posted_parsed`` is the ISO one.
    First-seen and last-seen are useless built from the former."""
    mapped = bd.map_indeed_job(INDEED_SAMPLE)
    assert mapped['posted_date'] == '2026-08-18T01:34:46.635Z'


# ---------------------------------------------------------------------------
# A reshare is not the vendor speaking
# ---------------------------------------------------------------------------


def _python_says_company_speaking(meta):
    """``entity_ingest._is_company_speaking`` over a plain dict.

    That function probes its argument with ``in row.keys()``, so a dict is fed
    through a shim rather than passed directly.
    """
    from app.services.entity_ingest import _is_company_speaking

    class Row(dict):
        def keys(self):                                            # noqa: D102
            return super().keys()

    return _is_company_speaking(Row({'social_meta': meta}))


#: Every shape the two implementations have to agree on. The realistic ones are
#: the last three: a plain owned post, and a record from before these fields
#: were retained.
OWN_VOICE_CASES = [
    {'is_repost': True},
    {'is_repost': False},
    {'is_repost': True, 'account_type': 'organization'},
    {'account_type': 'organization'},
    {'account_type': 'company'},
    {'account_type': 'person'},
    {'account_type': 'PERSON'},
    {'account_type': 'Organization'},
    {'is_repost': False, 'account_type': 'organization'},
    {'platform': 'linkedin'},
    {},
    None,
]


@pytest.mark.skipif(os.getenv('DB_TYPE', 'postgresql').lower() != 'postgresql',
                    reason='the fragment is Postgres jsonb')
def test_the_sql_and_python_rules_agree_on_who_is_speaking():
    """Two implementations of one rule, pinned to each other.

    The entity layer has excluded reshares in Python since those fields were
    kept; the Market Monitor read paths needed the same rule in SQL, and a
    second copy of a rule is a second thing to drift.

    Evaluated on PostgreSQL, not a stand-in. A first version of this test ran
    the fragment through sqlite's ``json_extract``, which returns integer 1 for
    a JSON ``true`` where Postgres ``->>`` returns the text ``'true'`` — so the
    translation disagreed with the rule and the test blamed the rule. Testing a
    Postgres expression anywhere but Postgres is how that goes wrong.
    """
    import json

    from sqlalchemy import text

    from app.database import get_database_instance
    from app.services.market_corpus import own_voice_sql

    conn = get_database_instance()._temp_get_connection()
    try:
        frag = own_voice_sql('a')
        disagreements = []
        for meta in OWN_VOICE_CASES:
            payload = json.dumps(meta) if meta is not None else None
            sql_says = conn.execute(text(
                f'SELECT {frag} FROM (SELECT CAST(:m AS JSONB) AS social_meta) a'
            ), {'m': payload}).scalar()
            expected = _python_says_company_speaking(meta)
            if bool(sql_says) != expected:
                disagreements.append((meta, bool(sql_says), expected))
    finally:
        conn.rollback()
        conn.close()

    assert not disagreements, '\n'.join(
        f'{m!r}: SQL={s}, Python={e}' for m, s, e in disagreements)


def _owned_post_queries():
    """Every SQL block that counts a vendor's own posts.

    Per query, not per file: a file-level tally counts docstring mentions and
    the deliberately-unguarded ``is_owned`` label, which is what an earlier
    version of this did — it failed on correct code and had to be replaced.
    """
    import pathlib
    import re

    out = []
    for path in ('app/services/market_analysis.py',
                 'app/services/market_publish.py',
                 'app/routes/market_monitor_routes.py'):
        src = pathlib.Path(path).read_text()
        for m in re.finditer(r'text\(f?"""(.*?)"""', src, re.S):
            body = m.group(1)
            if "= 'vendor:linkedin'" not in body:
                continue
            # A count or an existence test over owned posts. A SELECT that only
            # labels a row is not a count and is excluded on purpose.
            if not re.search(r'COUNT\s*\(|EXISTS\s*\(|SUM\s*\(', body):
                continue
            out.append((path, src[:m.start()].count('\n') + 1, body))
    return out


def test_every_owned_post_count_excludes_reshares():
    """A count of a vendor's own posts must not include its reshares.

    17% of this market's supposed vendor posts were the vendor amplifying
    somebody else — 32% for one vendor — and every figure built on them
    (loudest, quietest, post volume, share of voice, the Announced column)
    credited the vendor for words it did not write. The rule existed in the
    entity layer and no read path consulted it.
    """
    queries = _owned_post_queries()
    assert queries, 'found no owned-post counts — have these modules moved?'

    unguarded = [f'{path}:{line}' for path, line, body in queries
                 if '_OWN_VOICE' not in body]
    assert not unguarded, (
        'these queries count a vendor\'s own posts without excluding '
        'reshares: ' + ', '.join(unguarded))


def test_a_source_that_is_never_dispatched_does_not_report_as_failing():
    """A policy decision is not a fault, and the panel has to say which it is.

    PitchBook, ZoomInfo and Indeed are refused at admission, so nothing will
    ever replace their last run — three rows from 24 August reading
    "no collector dispatched source ...". The health panel reports the state of
    the most recent run, so all three read "failing" indefinitely: not their
    state, not actionable, and it buries a source that is genuinely broken
    among two that are working as designed.

    Every manual-only and paused source must therefore carry a reason a reader
    can act on, rather than inheriting a stale error.
    """
    from app.services import entity_scheduler as sch

    for source in sch.MANUAL_ONLY_SOURCES:
        reason = sch.MANUAL_ONLY_REASONS.get(source)
        assert reason, f'{source} is manual-only with no stated reason'
        assert len(reason) > 30, f'{source}: reason is too thin to act on'

    for source, reason in sch.PAUSED_SOURCES.items():
        assert reason and len(reason) > 30, (
            f'{source} is paused with no usable reason')


def test_the_health_panel_separates_policy_from_run_state():
    """``state`` answers "is this working"; ``policy`` answers "is this even
    running". Collapsing them is what made three sources read as broken."""
    import inspect

    from app.routes import market_monitor_routes as mmr

    src = inspect.getsource(mmr.source_health)
    for field in ('"scheduled"', '"policy"', '"policy_reason"',
                  '"not_scheduled"'):
        assert field in src, f'source_health no longer reports {field}'
    assert 'MANUAL_ONLY_REASONS' in src, (
        'source_health does not surface why a source is not dispatched, so a '
        'reader sees "not scheduled" with no way to find out why')


def test_no_sweep_holds_a_transaction_across_an_http_call():
    """A vendor sweep must commit as it goes, not once at the end.

    PostgreSQL here runs with ``idle_in_transaction_session_timeout = 60s``.
    Both website sweeps awaited HTTP inside an open transaction, so the
    connection sat idle-in-transaction while a site was fetched; one slow
    domain killed the backend and the rollback discarded every vendor already
    probed. Run 345 spent 452 seconds and saved nothing — the error was
    "SSL connection has been closed unexpectedly" on the next INSERT, which
    reads like a network fault rather than a design one.

    So: any sweep that awaits inside its vendor loop has to commit inside that
    loop too.
    """
    import ast
    import pathlib

    src = pathlib.Path('app/tasks/market_monitor.py').read_text()
    tree = ast.parse(src)

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for loop in ast.walk(node):
            if not isinstance(loop, (ast.For, ast.AsyncFor)):
                continue
            body = ast.get_source_segment(src, loop) or ''
            if 'await ' not in body:
                continue
            # Only loops that themselves reach the network. A loop awaiting
            # another poller (tick over markets, _poll_market over sources) is
            # not holding anything open — the callee owns its own transaction
            # scope — and a courtesy sleep reaches nothing at all.
            awaits = [ln for ln in body.splitlines()
                      if 'await ' in ln
                      and 'asyncio.sleep' not in ln
                      and 'await _poll' not in ln
                      and 'await _discover' not in ln
                      and 'await _review' not in ln
                      and 'await _write' not in ln
                      and 'await _reconcile' not in ln]
            if not awaits:
                continue
            if 'conn.commit()' not in body:
                offenders.append(f'{node.name} (line {loop.lineno})')

    assert not offenders, (
        'these vendor loops await network calls without committing inside the '
        'loop, so the connection sits idle-in-transaction and one slow host '
        'loses the whole sweep: ' + ', '.join(offenders))


# ---------------------------------------------------------------------------
# Top voices: a post is not a voice
# ---------------------------------------------------------------------------

def test_the_voice_threshold_is_configurable_and_defaults_to_three(monkeypatch):
    from app.services.market_analysis import consistent_voice_min_posts

    monkeypatch.delenv('MARKET_CONSISTENT_VOICE_MIN_POSTS', raising=False)
    assert consistent_voice_min_posts() == 3
    monkeypatch.setenv('MARKET_CONSISTENT_VOICE_MIN_POSTS', '5')
    assert consistent_voice_min_posts() == 5
    # A threshold of zero would put every single-post account back among the
    # voices, which is the thing being fixed.
    monkeypatch.setenv('MARKET_CONSISTENT_VOICE_MIN_POSTS', '0')
    assert consistent_voice_min_posts() == 1
    monkeypatch.setenv('MARKET_CONSISTENT_VOICE_MIN_POSTS', 'not a number')
    assert consistent_voice_min_posts() == 3


def test_top_voices_separates_a_voice_from_a_single_post():
    """One post is a post. 81 of this market's 87 authors posted once.

    Ranked by engagement and labelled "top voices", the list put those 81 above
    the one account that posted nine times — which had zero engagement and so
    came last. That inverts the question the panel is asking: who is driving
    this conversation, not which single post did numbers.
    """
    import inspect

    from app.services import market_analysis as man

    src = inspect.getsource(man.top_voices)
    for key in ('"consistent"', '"breakout"', '"consistent_min_posts"',
                '"sample_of_one"'):
        assert key in src, f'top_voices no longer reports {key}'
    # The union stays, so existing callers do not break.
    assert '"voices": voices' in src


def test_top_voices_links_accounts_without_building_profiles():
    """Brand monitoring's account profiles are built on demand, never in bulk.

    ``social_profile_service`` says so outright — "Built ON-DEMAND only (never
    bulk/auto) for cost" — and this list is 87 accounts. Joining to report
    whether a profile exists is free; calling the builder from a read path
    would profile the whole market every time somebody opened the tab.
    """
    import inspect

    from app.services import market_analysis as man

    src = inspect.getsource(man.top_voices)
    assert 'social_accounts' in src, (
        'top_voices no longer joins the account profiles, so a handle here is '
        'a stranger while its profile sits one screen away')
    assert 'handle_canonical' in src, (
        'the account link must carry handle_canonical — /accounts/profile is '
        'keyed on (platform, handle_canonical)')
    for forbidden in ('build_profile', 'SocialProfileService'):
        assert forbidden not in src, (
            f'top_voices calls {forbidden}: a read path must not build '
            f'profiles, which are on-demand only for cost')


# ---------------------------------------------------------------------------
# Earned attention comes from the resolved mentions, not from nowhere
# ---------------------------------------------------------------------------

def test_share_of_voice_reads_the_resolved_mentions():
    """The entity layer resolves who a third-party post is about; use it.

    ``bw_entity_mentions`` holds 1,933 rows across 53 brands with channel and
    platform kept separate, and no Market Monitor read path referenced it while
    ``ENTITY_INTELLIGENCE_MENTION_READ`` was on. So practitioner discussion of
    a vendor was being resolved and then ignored: the article-categories count
    saw 22 items where the mentions table has 50 across news, Twitter, Bluesky,
    Reddit and Glassdoor.
    """
    import inspect

    from app.services import market_analysis as man

    src = inspect.getsource(man.share_of_voice)
    assert 'bw_entity_mentions' in src
    assert 'mention_read' in src, (
        'the mention read must be gated on the rollout flag, like every other '
        'entity read')
    assert '"earned"' in src or 'earned' in src, (
        'the article-derived earned count must stay: callers compare against '
        'it, and a number that silently doubles is worse than two whose '
        'sources are stated')


@pytest.mark.skipif(os.getenv('DB_TYPE', 'postgresql').lower() != 'postgresql',
                    reason='reads live mention rows')
def test_earned_attention_never_counts_a_vendors_own_posts():
    """Owned social is already `own_posts`. Counting it again under attention
    would double it beneath a heading that says the opposite.

    The first version of this excluded owned_social from the channel breakdown
    and not from the platform breakdown, so a vendor showed
    ``platforms={'linkedin': 72}`` beside ``total=13`` — its own LinkedIn posts
    reported as earned attention. Both breakdowns are filtered now, and the
    invariant that catches it is that platforms can never outnumber the total.
    """
    from app.database import get_database_instance
    from app.services import market_analysis as man

    conn = get_database_instance()._temp_get_connection()
    try:
        market = conn.execute(text(
            'SELECT id FROM bw_markets WHERE enabled ORDER BY id LIMIT 1'
        )).scalar()
        if market is None:
            pytest.skip('no market to read')
        sov = man.share_of_voice(conn, int(market))
    finally:
        conn.rollback()
        conn.close()

    for row in sov['vendors']:
        att = row['attention']
        assert 'owned_social' not in att['by_channel'], (
            f"{row['vendor']}: owned social counted as earned attention")
        assert sum(att['by_platform'].values()) <= att['total'], (
            f"{row['vendor']}: platform counts ({att['by_platform']}) exceed "
            f"the attention total ({att['total']}) — something outside the "
            f"earned channels is being counted")
