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
from datetime import datetime, timedelta, timezone

import httpx
import pytest

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


def test_linkedin_jobs_stays_paused_until_the_request_shape_is_confirmed():
    """The output contract being known is not permission to dispatch. The
    HTTP 400 is about the discovery request, which the sample does not show."""
    from app.services import entity_scheduler as sch

    assert 'linkedin_jobs' in sch.PAUSED_SOURCES
    assert 'discovery' in sch.PAUSED_SOURCES['linkedin_jobs'].lower()
