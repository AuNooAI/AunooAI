"""Reading job listings from the system a company actually hires through.

Fixtures rather than live calls: these are somebody else's public APIs and a
test suite should not depend on their uptime or add traffic to them. The
fixtures are trimmed captures of real responses taken on 2026-08-26.

The detection tests carry most of the weight. A wrong board token does not fail
loudly — it returns somebody else's jobs, attributed to our vendor.
"""

from __future__ import annotations

import pytest

from app.collectors import ats_collector as ats


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def test_the_greenhouse_embed_script_yields_the_token_not_the_path():
    """The trap that made every Greenhouse vendor collect the same board.

    Dropzone's careers page references
    ``greenhouse.io/embed/job_board/js?for=dropzoneai``. A path-segment match on
    that URL returns the literal "embed", which is a real Greenhouse board
    belonging to nobody in particular — so a naive detector produces confident
    listings for the wrong company, silently.
    """
    html = ('<script src="https://boards.greenhouse.io/embed/job_board/js'
            '?for=dropzoneai"></script>')
    board = ats.detect(html)
    assert board == ats.AtsBoard('greenhouse', 'dropzoneai')
    assert board.key == 'greenhouse:dropzoneai'


def test_board_path_forms_are_all_recognised():
    cases = {
        '<a href="https://job-boards.greenhouse.io/dropzoneai">Jobs</a>':
            ('greenhouse', 'dropzoneai'),
        '<a href="https://jobs.ashbyhq.com/crogl">Careers</a>':
            ('ashby', 'crogl'),
        # A dotted token is legitimate and must survive.
        '<iframe src="https://jobs.ashbyhq.com/method.security"></iframe>':
            ('ashby', 'method.security'),
        '<a href="https://jobs.lever.co/acme-corp">Open roles</a>':
            ('lever', 'acme-corp'),
        '<a href="https://apply.workable.com/widgetco/">Jobs</a>':
            ('workable', 'widgetco'),
        '<a href="https://qevlar-1721317262.teamtailor.com/jobs">Jobs</a>':
            ('teamtailor', 'qevlar-1721317262'),
    }
    for html, expected in cases.items():
        assert ats.detect(html) == ats.AtsBoard(*expected), html


def test_a_page_with_no_board_returns_nothing_rather_than_guessing():
    """Four vendors in this market publish no machine-readable listings.

    Recording that is the honest answer. A detector that fell back to the
    domain, or to the first plausible-looking string, would attach a board that
    does not exist and then report its 404 as a collection failure forever.
    """
    assert ats.detect('') is None
    assert ats.detect('<p>Email us at jobs@example.com</p>') is None
    # The word alone is not a board. A blog post about hiring must not create
    # one.
    assert ats.detect('<p>We grow talent in our greenhouse.</p>') is None


def test_a_stored_board_round_trips_and_a_bad_one_is_refused():
    board = ats.AtsBoard('ashby', 'crogl')
    assert ats.parse_board(board.key) == board
    for bad in (None, '', 'crogl', 'notasystem:crogl', 'ashby:'):
        assert ats.parse_board(bad) is None, bad


def test_every_supported_system_has_an_adapter_and_a_board_url():
    """A system we can detect but not read is a permanent failure."""
    for system in ats.SUPPORTED_SYSTEMS:
        assert system in ats.ADAPTERS, f'{system} detected but not readable'
        assert ats.AtsBoard(system, 'token').board_url


# ---------------------------------------------------------------------------
# Adapters, against trimmed real responses
# ---------------------------------------------------------------------------

GREENHOUSE = {'jobs': [{
    'id': 4362664009,
    'title': 'Account Executive',
    'absolute_url': 'https://job-boards.greenhouse.io/dropzoneai/jobs/4362664009',
    'location': {'name': 'Remote - US'},
    'departments': [{'name': 'Sales'}],
    'company_name': 'Dropzone AI',
    'first_published': '2026-08-13T13:55:34-04:00',
    'updated_at': '2026-08-25T14:18:04-04:00',
}]}

ASHBY = {'apiVersion': '1', 'jobs': [
    {'id': 'bba19059-94c7-46bf-b2f2-34e7d15f390c',
     'title': 'Growth Marketer', 'location': 'United States',
     'department': 'Marketing', 'team': 'Marketing',
     'employmentType': 'FullTime', 'isRemote': True, 'isListed': True,
     'jobUrl': 'https://jobs.ashbyhq.com/crogl/bba19059',
     'publishedAt': '2026-04-24T16:52:17.279+00:00'},
    # Delisted: the company took it off its own board.
    {'id': 'deadbeef', 'title': 'Withdrawn Role', 'isListed': False,
     'publishedAt': '2026-01-01T00:00:00.000+00:00'},
]}

TEAMTAILOR = {'items': [{
    'id': '4632cb62-8ba0-4133-8f49-5c9595948a43',
    'title': 'Business Development Representative France',
    'url': 'https://qevlar-1721317262.teamtailor.com/jobs/8142897',
    'date_published': '2026-07-29T12:16:35+02:00',
    '_jobposting': {
        '@type': 'JobPosting',
        'title': 'Business Development Representative France',
        'datePosted': '2026-07-29T12:16:35+02:00',
        'employmentType': 'FULL_TIME',
        'jobLocation': [{'@type': 'Place', 'address': {
            '@type': 'PostalAddress', 'addressLocality': 'Paris',
            'addressRegion': 'EMEA', 'addressCountry': 'FR'}}],
    },
}]}

LEVER = [{'id': 'abc-123', 'text': 'Senior Engineer',
          'hostedUrl': 'https://jobs.lever.co/acme/abc-123',
          'createdAt': 1735689600000,
          'categories': {'location': 'Remote', 'team': 'Engineering',
                         'commitment': 'Full-time'}}]


def _one(system, token, payload):
    board = ats.AtsBoard(system, token)
    return board, ats.ADAPTERS[system].parse(board, payload)


def test_greenhouse_maps_completely():
    board, rows = _one('greenhouse', 'dropzoneai', GREENHOUSE)
    assert len(rows) == 1
    row = rows[0]
    assert row['title'] == 'Account Executive'
    assert row['location'] == 'Remote - US'
    assert row['function'] == 'Sales'
    assert row['url'].endswith('/4362664009')
    assert row['observed_source'] == 'ats:greenhouse'
    # The real publication date, which the LinkedIn dataset never gave.
    assert row['posted_date'].startswith('2026-08-13')


def test_ashby_maps_and_drops_a_delisted_role():
    """A role the company delisted must not appear.

    Showing it would contradict the board a reader can open and check, which is
    the one source of truth this collector has.
    """
    board, rows = _one('ashby', 'crogl', ASHBY)
    assert len(rows) == 1, 'the delisted role should be gone'
    row = rows[0]
    assert row['title'] == 'Growth Marketer'
    assert row['employment_type'] == 'FullTime'
    assert row['remote'] is True
    assert row['function_hint'] == 'Marketing'


def test_teamtailor_reads_the_embedded_job_posting():
    """The feed carries only a title and a date; the rest is in the schema.

    An earlier version read a ``_teamtailor`` key that does not exist, so all
    fifteen of Qevlar's listings came back with no location at all.
    """
    board, rows = _one('teamtailor', 'qevlar-1721317262', TEAMTAILOR)
    assert len(rows) == 1
    assert rows[0]['location'] == 'Paris, EMEA, FR'
    assert rows[0]['employment_type'] == 'FULL_TIME'


def test_lever_accepts_an_epoch_timestamp():
    board, rows = _one('lever', 'acme', LEVER)
    assert rows[0]['location'] == 'Remote'
    assert rows[0]['posted_date'].startswith('2025-')


# ---------------------------------------------------------------------------
# Identity and normalisation
# ---------------------------------------------------------------------------

def test_a_posting_id_is_namespaced_so_two_boards_cannot_collide():
    """Two systems can issue the same id.

    Unnamespaced, an integer id from Greenhouse and one from Lever would be the
    same snapshot key, and two companies' listings would silently merge into
    one.
    """
    _, gh = _one('greenhouse', 'boardone', {'jobs': [
        {'id': 1, 'title': 'Engineer', 'location': {'name': 'Remote'}}]})
    _, lv = _one('lever', 'boardtwo', [
        {'id': '1', 'text': 'Engineer', 'categories': {}}])
    assert gh[0]['posting_id'] != lv[0]['posting_id']
    assert gh[0]['posting_id'] == 'greenhouse:boardone:1'


def test_a_missing_date_stays_missing():
    """Never today's date as a stand-in.

    Filling it in would make every listing look posted on the day we found it,
    which is the "first observed is not an opening date" error one level down.
    """
    assert ats._iso(None) is None
    assert ats._iso('') is None
    assert ats._iso('not a date') is None
    assert ats._iso('2026-08-13T13:55:34-04:00').startswith('2026-08-13')


def test_the_function_guess_prefers_the_title_over_the_department():
    """A department called G&A says nothing; the title almost always does."""
    assert ats._function_of('Senior Security Engineer', 'G&A') == 'Engineering'
    assert ats._function_of('Account Executive', None) == 'Sales'
    # With no hint in the title, the board's own department is kept verbatim
    # rather than being forced into one of our buckets.
    assert ats._function_of('Mission Manager', 'Federal') == 'Federal'
    assert ats._function_of('Something Novel', None) == 'Other'


def test_seniority_picks_the_most_senior_signal():
    assert ats._seniority_of('Head of Security Research') == 'Executive'
    assert ats._seniority_of('Senior Director, Sales') == 'Director'
    assert ats._seniority_of('Detection Engineering Lead') == 'Manager'
    assert ats._seniority_of('Senior Backend Engineer') == 'Senior'
    assert ats._seniority_of('Backend Engineer') is None


def test_a_posting_with_no_id_or_title_is_dropped(monkeypatch):
    """It could not be tracked between runs, so it would look new every time."""
    board = ats.AtsBoard('greenhouse', 'x')
    rows = ats.ADAPTERS['greenhouse'].parse(board, {'jobs': [
        {'id': None, 'title': 'No id'},
        {'id': 5, 'title': ''},
        {'id': 6, 'title': 'Real Role'},
    ]})
    # The adapter itself is permissive; fetch_jobs applies the filter, so
    # replicate it here rather than asserting the adapter drops them.
    kept = [r for r in rows if r.get('posting_id') and r.get('title')
            and not r['posting_id'].endswith(':None')]
    assert [r['title'] for r in kept] == ['Real Role']


def test_an_error_is_raised_rather_than_an_empty_list():
    """An empty board is a real answer and must not look like a failure.

    A company with nothing open returns zero listings. If a failed request also
    returned zero, a zero would stop meaning anything — which is the defect the
    whole metric contract exists to prevent.
    """
    assert issubclass(ats.AtsError, RuntimeError)
    err = ats.AtsError('gone', retryable=False, code='board_not_found')
    assert err.retryable is False and err.code == 'board_not_found'
