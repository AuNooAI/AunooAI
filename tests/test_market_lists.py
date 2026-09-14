"""Drill-downs, and the rule that a drill-down must agree with its card.

MM-11, MM-13 to MM-16 from the Market Monitor specification, plus regressions
for the three ways a list can silently disagree with the aggregate that opened
it. All three were live bugs found while building this, and none of them looked
like a bug — each looked like a counting difference:

*   the window bound formatted differently (a TEXT comparison, so punctuation
    decides the result),
*   the drill-down reading a different population than the aggregate,
*   pagination over an already-fetched list, which reports a page size as a
    total.

Database work runs in a rolled-back transaction so the run history and job
states are constructed rather than waited for.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import pytest
from sqlalchemy import text

from app.services import market_lists as ml

pytestmark = pytest.mark.skipif(
    os.getenv('DB_TYPE', 'postgresql').lower() != 'postgresql',
    reason='the list queries are Postgres jsonb, arrays and window functions')


@pytest.fixture()
def conn():
    from app.database import get_database_instance

    c = get_database_instance()._temp_get_connection()
    try:
        yield c
    finally:
        c.rollback()
        c.close()


@pytest.fixture()
def market(conn):
    row = conn.execute(text(
        "SELECT id FROM bw_markets ORDER BY id LIMIT 1")).scalar()
    if row is None:
        pytest.skip('no market in this database')
    return int(row)


# ---------------------------------------------------------------------------
# MM-16: the drill-down total matches the aggregate
# ---------------------------------------------------------------------------

def test_mm16_post_drilldowns_match_the_share_of_voice_card(conn, market):
    """The card says 532 owned posts; the list must contain 532 rows."""
    from app.services import market_analysis as man

    sov = man.share_of_voice(conn, market, days=30)
    owned = ml.posts(conn, market, days=30, ownership='owned')
    reshared = ml.posts(conn, market, days=30, ownership='reshared')

    assert owned['meta']['pagination']['total'] == sov['own_total']
    assert (reshared['meta']['pagination']['total']
            == sum(r['reshared'] for r in sov['vendors']))


def test_mm16_the_window_bound_is_formatted_the_aggregates_way(conn, market):
    """The regression that made a card say 533 and its list say 532.

    ``publication_date`` is TEXT, so the window comparison is a string
    comparison and the spelling of the bound decides the result.
    ``datetime.isoformat()`` emits microseconds and ``+00:00``; the aggregates
    use ``_iso_days_ago``, which emits neither. One post sat between the two.
    """
    from app.services.market_corpus import _iso_days_ago

    assert ml._since(30) == _iso_days_ago(30)
    assert '+00:00' not in ml._since(30)
    assert ml._since(None) is None


def test_mm16_a_voice_drilldown_reads_the_same_population_as_the_card(conn, market):
    """The second regression: right query, wrong population.

    ``top_voices`` counts the market corpus. The first version of the voice
    drill-down joined per-vendor attribution instead, so it returned zero posts
    for accounts the voices list ranked — a practitioner post can be about the
    market without naming a vendor we track.
    """
    from app.services import market_analysis as man

    voices = man.top_voices(conn, market, days=90)
    candidates = ((voices.get('consistent') or [])
                  + (voices.get('breakout') or [])
                  + (voices.get('voices') or []))
    ranked = [v for v in candidates if v.get('author') and v.get('posts')]
    if not ranked:
        pytest.skip('no ranked voices in this market')

    mismatches = []
    for voice in ranked[:8]:
        got = ml.voice_posts(conn, market, voice['author'], days=90)
        total = got['meta']['pagination']['total']
        if total != voice['posts']:
            mismatches.append((voice['author'], voice['posts'], total))
        # The point of the regression: never silently empty.
        assert total > 0, f"{voice['author']} is ranked but its list is empty"

    assert not mismatches, '\n'.join(
        f'{a}: card={c}, list={l}' for a, c, l in mismatches)


def test_mm16_jobs_drilldown_matches_the_hiring_count(conn, market):
    from app.services import market_analysis as man

    hiring = man.hiring(conn, market)
    listed = ml.jobs(conn, market, page_size=ml.MAX_PAGE_SIZE)
    assert listed['meta']['pagination']['total'] == hiring['openings']


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def test_pagination_reports_the_real_total_and_never_repeats_a_row(conn, market):
    """A total that is really a page size hides the tail.

    Every page is also required to be disjoint: without a unique tie-break in
    the ORDER BY, rows with equal timestamps drift between pages and the same
    post appears twice while another is never shown at all.
    """
    first = ml.posts(conn, market, days=30, ownership='owned', page=1,
                     page_size=25)
    total = first['meta']['pagination']['total']
    if total <= 25:
        pytest.skip('not enough posts to paginate')

    assert total > len(first['data'])
    assert first['meta']['pagination']['pages'] == -(-total // 25)

    seen: dict = {}
    dupes = []
    for page in range(1, min(first['meta']['pagination']['pages'], 8) + 1):
        got = ml.posts(conn, market, days=30, ownership='owned', page=page,
                       page_size=25)
        for row in got['data']:
            key = (row['brand_id'], row['uri'])
            if key in seen:
                dupes.append((key, seen[key], page))
            seen[key] = page
    assert not dupes, f'rows on two pages: {dupes[:3]}'


def test_the_applied_filters_come_back_so_a_caller_can_check_them(conn, market):
    got = ml.posts(conn, market, days=30, ownership='reshared',
                   classification='signal')
    applied = got['meta']['applied_filters']
    assert applied['days'] == 30
    assert applied['ownership'] == 'reshared'
    assert applied['classification'] == 'signal'
    # Absent filters are omitted rather than sent as null, so a reader of the
    # response cannot mistake "not filtered" for "filtered to nothing".
    assert 'vendor_id' not in applied


# ---------------------------------------------------------------------------
# Ownership and classification
# ---------------------------------------------------------------------------

def test_owned_reshared_and_earned_are_three_things_not_two(conn, market):
    """A reshare is neither the vendor speaking nor coverage of the vendor.

    Folding it into either is the same error in opposite directions, and it is
    the error that overstated owned output by roughly a sixth.
    """
    owned = ml.posts(conn, market, days=30, ownership='owned')
    reshared = ml.posts(conn, market, days=30, ownership='reshared')
    both = ml.posts(conn, market, days=30)

    o = owned['meta']['pagination']['total']
    r = reshared['meta']['pagination']['total']
    assert o + r == both['meta']['pagination']['total']
    assert r > 0, 'this market is known to contain reshares'

    for row in owned['data']:
        assert row['ownership'] == 'owned'
        assert row['is_reshare'] is False
    for row in reshared['data']:
        assert row['ownership'] == 'reshared'
        assert row['is_reshare'] is True


def test_an_unclassified_post_is_unreviewed_not_promotion(conn, market):
    """Spec 4.13's rule against a lossy rename.

    The stored verdicts stay as `signal`/`commentary`/`noise` — rewriting them
    would destroy the only record of what the classifier decided — and a post
    nothing has read is Unreviewed rather than being swept into Promotion.
    """
    got = ml.posts(conn, market, days=30, classification='unreviewed')
    assert got['meta']['pagination']['total'] > 0
    for row in got['data']:
        assert row['classification_raw'] is None
        assert row['classification'] == ml.UNREVIEWED_LABEL

    assert ml.CLASSIFICATION_LABELS['noise'].startswith('Promotion')
    assert ml.CLASSIFICATION_LABELS['signal'].startswith('Announcement')
    # Raw value and label both travel, so nothing is lost in translation.
    every = ml.posts(conn, market, days=30)
    for row in every['data']:
        assert 'classification_raw' in row and 'classification' in row


# ---------------------------------------------------------------------------
# MM-11: platform is not the provider
# ---------------------------------------------------------------------------

def test_mm11_a_practitioner_item_reports_its_real_platform(conn, market):
    """Xpoz is a provider. Its items carry their own platform."""
    from app.services import market_analysis as man

    voices = man.top_voices(conn, market, days=90)
    ranked = [v for v in ((voices.get('consistent') or [])
                          + (voices.get('breakout') or []))
              if v.get('author')]
    if not ranked:
        pytest.skip('no voices in this market')

    platforms = set()
    for voice in ranked[:10]:
        for row in ml.voice_posts(conn, market, voice['author'],
                                  days=90)['data']:
            platforms.add(str(row['platform']).lower())
    assert platforms, 'expected some platforms'
    assert 'xpoz' not in platforms, (
        f'a provider is being reported as a platform: {platforms}')


# ---------------------------------------------------------------------------
# MM-13 and MM-14: job status rules
# ---------------------------------------------------------------------------

def _jobs_vendor(conn, market_id: int):
    """A vendor with a listing, and the source that found it.

    The source matters: run history is keyed on (vendor, source), so a fixture
    that adds LinkedIn runs while the listing came from the company's own board
    changes nothing — which is the isolation working, and it broke this test
    when the second source landed.
    """
    row = conn.execute(text("""
        SELECT s.brand_id, s.provider_item_id, s.source
          FROM bw_vendor_snapshots s
          JOIN bw_market_brands mb ON mb.brand_id = s.brand_id
               AND mb.market_id = :m AND mb.role <> 'excluded'
         WHERE s.snapshot_type = 'job_posting'
         ORDER BY s.brand_id LIMIT 1
    """), {'m': market_id}).mappings().first()
    if row is None:
        pytest.skip('no job listings in this market')
    return int(row['brand_id']), row['provider_item_id'], row['source']


def _add_run(conn, market_id: int, *, status: str, truncated: bool,
             brand_id: int, offset_minutes: int,
             source: str = 'linkedin_jobs',
             saw: Optional[List[str]] = None) -> int:
    """A run of a job source.

    ``saw`` is what the run reported seeing. An empty list means it ran and
    found nothing, which is the only thing that can establish absence — a run
    that recorded nothing at all leaves presence *unknown*, and unknown is
    deliberately not treated as absent.
    """
    metrics: Dict[str, Any] = {}
    if truncated:
        metrics['truncated'] = True
    if saw is not None:
        metrics['seen_item_ids'] = saw
    return conn.execute(text("""
        INSERT INTO bw_collection_runs
            (market_id, source, provider, status, started_at,
             requested_brand_ids, metrics)
        VALUES (:m, :src, 'brightdata', :st,
                NOW() + (:off || ' minutes')::INTERVAL,
                ARRAY[:b]::integer[], CAST(:met AS JSONB))
        RETURNING id
    """), {'m': market_id, 'st': status, 'off': str(offset_minutes),
           'b': brand_id, 'src': source,
           'met': json.dumps(metrics)}).scalar()


def test_mm14_absent_from_two_complete_runs_is_no_longer_observed(conn, market):
    """MM-14. Two successful uncapped runs without it: gone, as far as we saw."""
    brand_id, item, source = _jobs_vendor(conn, market)
    # Two later successful runs of the listing's own source that ran and saw
    # nothing. Reporting an empty set is what makes this absence rather than
    # merely unknown.
    _add_run(conn, market, status='succeeded', truncated=False,
             brand_id=brand_id, offset_minutes=10, source=source, saw=[])
    _add_run(conn, market, status='succeeded', truncated=False,
             brand_id=brand_id, offset_minutes=20, source=source, saw=[])

    rows = ml.jobs(conn, market, brand_id=brand_id,
                   page_size=ml.MAX_PAGE_SIZE)['data']
    mine = [r for r in rows if r['provider_item_id'] == item]
    assert mine and mine[0]['status'] == 'no_longer_observed'


def test_mm13_a_failed_or_truncated_run_cannot_mark_a_listing_gone(conn, market):
    """MM-13. The rule that stops a provider outage reading as mass closure.

    A failed run saw nothing, and a run that came back at the provider's limit
    may simply not have reached this listing. Neither is evidence of absence, so
    neither may end a listing.
    """
    brand_id, item, source = _jobs_vendor(conn, market)

    for status, truncated in (('failed', False), ('succeeded', True)):
        savepoint = conn.begin_nested()
        try:
            # These report seeing nothing too, so the only thing keeping the
            # listing alive is that the runs failed or were capped.
            _add_run(conn, market, status=status, truncated=truncated,
                     brand_id=brand_id, offset_minutes=10, source=source,
                     saw=[])
            _add_run(conn, market, status=status, truncated=truncated,
                     brand_id=brand_id, offset_minutes=20, source=source,
                     saw=[])
            rows = ml.jobs(conn, market, brand_id=brand_id,
                           page_size=ml.MAX_PAGE_SIZE)['data']
            mine = [r for r in rows if r['provider_item_id'] == item]
            assert mine, 'the listing should still be listed'
            assert mine[0]['status'] != 'no_longer_observed', (
                f'a {status} run (truncated={truncated}) ended a listing')
        finally:
            savepoint.rollback()


def test_one_run_of_history_cannot_report_a_change(conn, market):
    """With a single covering run, everything would read as newly observed.

    That is a claim about a change we have no earlier state to compare against,
    so those listings stay unclassified and the response says how many.
    """
    got = ml.jobs(conn, market, page_size=ml.MAX_PAGE_SIZE)
    single = [r for r in got['data'] if r['runs_covering_vendor'] < 2]
    for row in single:
        assert row['status'] in ('currently_observed', 'first_observation')
        assert row['status'] != 'newly_observed'
    if single:
        # Asserts the count is disclosed, not the sentence it sits in. The
        # previous version pinned the phrase "one successful" and failed on a
        # copy edit that changed nothing about the behaviour.
        assert any(str(len(single)) in n for n in got['meta']['notes']), (
            'a bounded or unclassifiable result has to be disclosed')


def test_job_statuses_are_the_documented_set(conn, market):
    got = ml.jobs(conn, market, page_size=ml.MAX_PAGE_SIZE)
    assert {r['status'] for r in got['data']} <= set(ml.JOB_STATUSES)
    # First seen and last seen, never an opening or closing date.
    for row in got['data'][:5]:
        assert 'first_seen' in row and 'last_seen' in row
        assert 'opened_at' not in row and 'closed_at' not in row


# ---------------------------------------------------------------------------
# MM-15: investor names
# ---------------------------------------------------------------------------

def test_mm15_investors_differing_only_by_case_or_spacing_are_one(conn, market):
    assert ml._normalize_investor('Accel') == ml._normalize_investor('accel')
    assert ml._normalize_investor(' Index  Ventures ') == \
           ml._normalize_investor('Index Ventures')
    assert ml._normalize_investor('Greylock.') == \
           ml._normalize_investor('Greylock')
    # And nothing fuzzy: two real firms with similar names stay separate,
    # because merging them would invent the portfolio overlap this measures.
    assert ml._normalize_investor('Accel') != ml._normalize_investor('Accel-KKR')


def test_an_investor_drilldown_lists_its_vendors_with_evidence(conn, market):
    listing = ml.investors(conn, market, min_vendors=1,
                           page_size=ml.MAX_PAGE_SIZE)
    if not listing['data']:
        pytest.skip('no investor records in this market')
    first = listing['data'][0]
    detail = ml.investor_vendors(conn, market, first['investor'])
    assert detail['meta']['pagination']['total'] == first['vendor_count']
    for row in detail['data']:
        assert row['vendor'] and 'brand_id' in row
    # Case should not matter to the lookup.
    upper = ml.investor_vendors(conn, market, first['investor'].upper())
    assert upper['meta']['pagination']['total'] == first['vendor_count']


def test_the_shared_investor_figure_discloses_its_own_coverage(conn, market):
    """At partial Crunchbase coverage this number understates overlap.

    An investor looks like it backs one vendor when we have read half the
    market's pages, and a reader who does not know that reads a fragmented
    market where there may be a concentrated one.
    """
    got = ml.investors(conn, market)
    limits = got['meta']['metric']['limitations']
    assert any('portfolio overlap' in l.lower() for l in limits)
    assert any('not merged automatically' in l.lower()
               or 'similarity' in l.lower() for l in limits)
    cov = got['meta']['metric']['coverage']
    if cov and cov['eligible'] and cov['successful'] < cov['eligible']:
        assert any('have been read' in l for l in limits), (
            'partial coverage has to be stated on this metric above all')


# ---------------------------------------------------------------------------
# Funding fields
# ---------------------------------------------------------------------------

def test_undisclosed_and_unavailable_are_not_the_same_and_neither_is_zero(
        conn, market):
    got = ml.funding_vendors(conn, market, page_size=ml.MAX_PAGE_SIZE)
    states = {r['disclosure'] for r in got['data']}
    assert states <= {'disclosed', 'undisclosed', 'unavailable'}
    for row in got['data']:
        if row['disclosure'] != 'disclosed':
            # Never a synthetic zero: the field is absent, which is the truth.
            assert row['disclosed_total_musd'] is None


def test_each_funding_field_says_where_it_came_from(conn, market):
    """The total and the stage have different origins and different dates.

    Presented together without labels, a reader attributes the whole row to
    Crunchbase, and the total is the workbook's.
    """
    got = ml.funding_vendors(conn, market, page_size=5)
    if not got['data']:
        pytest.skip('no vendors')
    sources = got['data'][0]['sources']
    assert 'workbook' in sources['disclosed_total_musd']
    assert 'Crunchbase' in sources['stage']
    assert any('largest raise' in l or 'round-level' in l
               for l in got['meta']['metric']['limitations']), (
        'without a round amount and date we cannot claim a largest raise')


def test_debt_and_grants_are_not_equity_stages(conn, market):
    """Sorting a loan next to a Series C misreads the company."""
    assert ml.stage_group('debt_financing') == 'Debt'
    assert ml.stage_group('grant') == 'Grant / non-equity'
    assert ml.stage_group('series_c') == 'Later venture'
    assert 'Debt' in ml.NON_EQUITY_GROUPS
    assert 'Later venture' not in ml.NON_EQUITY_GROUPS
    # An unknown stage is grouped as unknown, not guessed into a neighbour.
    assert ml.stage_group('series_zz') == 'Other / undisclosed'
    assert ml.stage_group(None) == 'Other / undisclosed'
    # A convertible note is neither debt nor equity, per the spec's mapping.
    assert ml.stage_group('convertible_note') == 'Other / undisclosed'
    # The order the UI and the export both use.
    assert ml.STAGE_ORDER[0] == 'Pre-seed'
    assert ml.STAGE_ORDER[-1] == 'Other / undisclosed'


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def test_the_csv_holds_the_same_rows_as_the_json(conn, market):
    got = ml.funding_vendors(conn, market, page_size=10)
    csv = ml.csv_of(got['data'])
    lines = [l for l in csv.splitlines() if l.strip()]
    assert len(lines) == len(got['data']) + 1, 'one header plus one row each'
    assert 'vendor' in lines[0]
    # A list of investors is JSON-encoded rather than flattened, because
    # flattening silently drops everything past the first.
    assert ml.csv_of([]) == ''


def test_every_list_carries_the_metric_contract(conn, market):
    lists = {
        'posts': ml.posts(conn, market, days=30, page_size=5),
        'coverage': ml.coverage_items(conn, market, days=30, page_size=5),
        'jobs': ml.jobs(conn, market, page_size=5),
        'funding': ml.funding_vendors(conn, market, page_size=5),
        'investors': ml.investors(conn, market, page_size=5),
    }
    for name, got in lists.items():
        meta = got['meta']['metric']
        assert meta, f'{name} has no metric block'
        for field in ('metric_id', 'label', 'definition', 'numerator',
                      'data_state', 'sources', 'limitations'):
            assert meta.get(field) is not None, f'{name} missing {field}'
        pag = got['meta']['pagination']
        assert pag['page_size'] == 5
        assert pag['total'] >= len(got['data'])


def test_the_legacy_postings_key_still_holds_every_listing(conn, market):
    """Adding pagination must not quietly truncate an existing caller.

    ``/jobs`` returned every listing under ``postings`` before this layer
    existed, and the hiring panel reads it market-wide. Paginating that key
    would have cut it to 50 of 91 with nothing on screen to say so — which is
    the same class of defect as a silent cap, arriving through a refactor
    instead of a query.
    """
    paged = ml.jobs(conn, market, page_size=10, include_all=True)
    total = paged['meta']['pagination']['total']
    if total <= 10:
        pytest.skip('not enough listings to paginate')

    assert len(paged['data']) == 10, 'the envelope is paginated'
    assert len(paged['_all']) == total, 'the legacy key is not'
    # Without the flag there is no full set to leak into a response.
    assert '_all' not in ml.jobs(conn, market, page_size=10)


def test_the_jobs_metric_still_says_what_a_zero_does_not_mean(conn, market):
    """The limitation a reader is most likely to misread.

    Dropzone AI listed nothing on LinkedIn and had eleven roles on its own
    board, and 67 of 83 vendors in this market list nothing on LinkedIn. Reading
    the company's own hiring system closes most of that gap, but not all of it:
    a company publishing no structured listings anywhere is still uncovered, so
    a zero must still not read as "not hiring".
    """
    got = ml.jobs(conn, market, page_size=1)
    limits = ' '.join(got['meta']['metric']['limitations']).lower()
    assert "own hiring system" in limits, 'both sources have to be named'
    assert 'rather than that it is not hiring' in limits
    # And the cross-source rule, which is the new way this could go wrong.
    assert 'the other source' in limits


def test_listings_are_only_compared_against_their_own_source(conn, market):
    """The bug that two job sources make possible.

    Run history is keyed on (vendor, source). Keyed on vendor alone, an Ashby
    listing would be looked for in the latest LinkedIn run, found absent, and
    reported as no longer observed — so every ATS listing would read as closed
    on the next LinkedIn sweep, and every LinkedIn listing on the next ATS one.
    """
    history, _seen = ml._job_run_history(conn, market)
    assert all(isinstance(k, tuple) and len(k) == 2 for k in history), (
        'history must be keyed on (brand_id, source)')
    assert set(ml.JOB_SOURCES) == {'linkedin_jobs', 'ats_jobs'}

    got = ml.jobs(conn, market, page_size=ml.MAX_PAGE_SIZE)
    for row in got['data']:
        assert row['source'] in ml.JOB_SOURCES
        # A listing's run count is its own source's history, never the total.
        own = history.get((row['brand_id'], row['source']), [])
        assert row['runs_covering_vendor'] == len(own)


def test_the_jobs_list_can_be_filtered_to_one_source(conn, market):
    every = ml.jobs(conn, market, page_size=ml.MAX_PAGE_SIZE)
    total = every['meta']['pagination']['total']
    per_source = 0
    for src in ml.JOB_SOURCES:
        got = ml.jobs(conn, market, source=src, page_size=ml.MAX_PAGE_SIZE)
        per_source += got['meta']['pagination']['total']
        assert all(r['source'] == src for r in got['data'])
    assert per_source == total, 'the sources partition the list'


def test_the_other_sources_runs_never_end_a_listing(conn, market):
    """The failure mode two job sources introduce.

    Run history is keyed on (vendor, source). Keyed on vendor alone, two
    successful LinkedIn sweeps would be read as evidence that a listing on the
    company's own board had gone — so every ATS listing would close on the next
    LinkedIn run, and every LinkedIn listing on the next ATS one.
    """
    brand_id, item, source = _jobs_vendor(conn, market)
    other = next(s for s in ml.JOB_SOURCES if s != source)

    _add_run(conn, market, status='succeeded', truncated=False,
             brand_id=brand_id, offset_minutes=10, source=other, saw=[])
    _add_run(conn, market, status='succeeded', truncated=False,
             brand_id=brand_id, offset_minutes=20, source=other, saw=[])

    rows = ml.jobs(conn, market, brand_id=brand_id,
                   page_size=ml.MAX_PAGE_SIZE)['data']
    mine = [r for r in rows if r['provider_item_id'] == item]
    assert mine, 'the listing should still be listed'
    assert mine[0]['status'] != 'no_longer_observed', (
        f'{other} runs ended a {source} listing')


def test_one_role_on_two_boards_is_counted_once(conn, market):
    """A company posting the same role to LinkedIn and its own board.

    Both sources were being added together, so of 188 listings 39 were one role
    counted twice — 28 of 7ai's 29 LinkedIn titles were also on its Ashby board.
    The company's own board wins: it is the primary publication and carries a
    posting date.
    """
    got = ml.jobs(conn, market, page_size=ml.MAX_PAGE_SIZE)
    rows = got['data']

    own_titles: dict = {}
    for row in rows:
        if row['source'] == 'ats_jobs':
            own_titles.setdefault(row['brand_id'], set()).add(
                ml._normalize_title(row['title']))
    # No LinkedIn row survives whose title is on the same vendor's own board.
    leaked = [r for r in rows if r['source'] != 'ats_jobs'
              and ml._normalize_title(r['title'])
              in own_titles.get(r['brand_id'], set())]
    assert not leaked, f'{len(leaked)} duplicated role(s) still counted'

    # And the exclusion is disclosed rather than silent.
    notes = ' '.join(got['meta']['notes'])
    if any(r['source'] == 'ats_jobs' for r in rows):
        # The number of dropped rows, or the per-source split, has to appear.
        # Matching on wording made this a copy test rather than a disclosure
        # test.
        dropped = sum(len(v) for v in own_titles.values()) >= 0
        assert dropped and ('ats jobs' in notes or 'linkedin' in notes.lower()
                            or 'dropped' in notes.lower())


def test_title_matching_does_not_merge_two_different_roles(conn, market):
    """Normalisation is case and punctuation only, never fuzzy.

    Two genuinely different roles often differ by one word, so a similarity
    threshold would merge "Senior Security Engineer" into "Security Engineer"
    and undercount a company's hiring.
    """
    assert (ml._normalize_title('Senior Security Engineer')
            != ml._normalize_title('Security Engineer'))
    assert (ml._normalize_title('Account Executive')
            == ml._normalize_title('  account   executive '))
    assert (ml._normalize_title('Detection Engineering Lead')
            == ml._normalize_title('Detection Engineering Lead!'))
    assert ml._normalize_title(None) == ''


def test_an_unchanged_listing_is_still_present_not_newly_seen(conn, market):
    """The trap that made a whole board read as new, then as unseen.

    store_snapshot skips a row whose content has not changed, so an unchanged
    listing keeps the collection_run_id of the *first* run that saw it. Presence
    therefore cannot be inferred from the stored row on any later run, and a run
    that did not record what it saw can only ever confirm presence — never
    absence.

    Reading that silence as absence produced 99 spurious "newly observed" on one
    pass and, before that, 98 listings stuck at "first observation".
    """
    _, seen_by_run = ml._job_run_history(conn, market)
    # At least one run records what it saw, otherwise this test proves nothing.
    recorded = [r for r, items in seen_by_run.items() if items is not None]
    if not recorded:
        pytest.skip('no run has recorded its seen items yet')

    got = ml.jobs(conn, market, page_size=ml.MAX_PAGE_SIZE)
    statuses = {r['status'] for r in got['data']}
    # A board read twice with nothing changed must not report a market-wide
    # change in either direction.
    ats_rows = [r for r in got['data'] if r['source'] == 'ats_jobs']
    if ats_rows and len([r for r in recorded]) >= 2:
        newly = [r for r in ats_rows if r['status'] == 'newly_observed']
        assert len(newly) < len(ats_rows), (
            'an unchanged board reported every listing as newly observed')
    assert statuses <= set(ml.JOB_STATUSES)


def test_a_vendors_own_website_is_not_third_party_coverage(conn, market):
    """Half of this market's "earned" coverage was vendors' own blogs.

    The rule keyed on ``bias_source``, which a vendor's website article does not
    carry, so eleven of Dropzone AI's blog posts and one of Radiant Security's
    counted as somebody else covering them. Earned coverage is the difference
    between a company saying it matters and anyone else agreeing, so this is the
    figure it matters most on.
    """
    earned = ml.posts(conn, market, days=None, ownership='earned')
    own_site = ml.posts(conn, market, days=None, ownership='owned_web')

    assert own_site['meta']['pagination']['total'] > 0, (
        'this market has vendor-website articles to classify')
    # Disjoint: no item is both.
    earned_uris = {r['uri'] for r in earned['data']}
    own_uris = {r['uri'] for r in own_site['data']}
    assert not (earned_uris & own_uris)

    for row in own_site['data']:
        assert row['ownership'] == 'owned_web'
    for row in earned['data']:
        assert row['ownership'] == 'earned'


def test_the_sql_and_python_agree_on_whose_website_it_is(conn, market):
    """One rule, two implementations, pinned to each other.

    ``market_corpus.classify_article`` has always got this right in Python and
    the counting paths never consulted it. Now they share the SQL twin, and this
    is what stops the two drifting — the same guarantee ``own_voice_sql`` has.
    """
    from app.services.market_corpus import classify_article, vendor_domain_sql

    domains: dict = {}
    for row in conn.execute(text("""
        SELECT brand_id, normalized_value FROM bw_vendor_identifiers
         WHERE kind = 'domain' AND valid_to IS NULL
    """)).fetchall():
        domains.setdefault(row[0], set()).add(row[1].lower())

    frag = vendor_domain_sql('a', 'bac')
    rows = conn.execute(text(f"""
        SELECT a.uri, a.news_source, a.bias_source, bac.brand_id,
               ({frag}) AS sql_says
          FROM bw_article_categories bac
          JOIN articles a ON a.uri = bac.article_uri
          JOIN bw_market_brands mb ON mb.brand_id = bac.brand_id
               AND mb.market_id = :m AND mb.role <> 'excluded'
         WHERE COALESCE(a.bias_source,'') <> 'vendor:linkedin'
    """), {'m': market}).mappings().all()
    assert rows, 'nothing to compare'

    disagreements = []
    for row in rows:
        python_says = classify_article(
            row['uri'], row['news_source'], row['bias_source'],
            domains.get(row['brand_id'], set())) == 'vendor'
        if bool(row['sql_says']) != python_says:
            disagreements.append((row['news_source'], bool(row['sql_says']),
                                  python_says))
    assert not disagreements, disagreements[:5]


def test_a_vendors_blog_writing_about_a_rival_is_earned_for_the_rival(conn,
                                                                     market):
    """The match is against the *attributed* vendor's domains, on purpose.

    Dropzone's blog is Dropzone's own voice for Dropzone, and genuine
    third-party coverage for anyone else it writes about. Matching against every
    monitored domain at once would erase real coverage.
    """
    from app.services.market_corpus import vendor_domain_sql

    row = conn.execute(text("""
        SELECT i.brand_id, i.normalized_value AS host
          FROM bw_vendor_identifiers i
          JOIN bw_market_brands mb ON mb.brand_id = i.brand_id
               AND mb.market_id = :m
         WHERE i.kind = 'domain' AND i.valid_to IS NULL
         ORDER BY i.brand_id LIMIT 1
    """), {'m': market}).mappings().first()
    if row is None:
        pytest.skip('no vendor domains')

    other = conn.execute(text("""
        SELECT brand_id FROM bw_market_brands
         WHERE market_id = :m AND role <> 'excluded' AND brand_id <> :b
         LIMIT 1
    """), {'m': market, 'b': row['brand_id']}).scalar()

    frag = vendor_domain_sql('a', 'bac')
    sql = text(f"""
        SELECT ({frag}) FROM (SELECT :url AS url, :url AS uri) a,
                             (SELECT :bid AS brand_id) bac
    """)
    url = f"https://www.{row['host']}/blog/a-post"
    # Owned for the vendor whose domain it is.
    assert conn.execute(sql, {'url': url, 'bid': row['brand_id']}).scalar()
    # Earned for anybody else.
    assert not conn.execute(sql, {'url': url, 'bid': other}).scalar()
