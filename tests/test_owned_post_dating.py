"""A vendor post that looks back at earlier news takes the date it states."""
from datetime import datetime, timezone

from app.services.entity_event_extractors import owned_post as op


def _utc(y, m, d):
    return datetime(y, m, d, tzinfo=timezone.utc)


def test_a_full_date_in_the_announcing_sentence_is_read():
    body = ("Accelerating the Agentic AI SOC Movement. On February 25, 2026, "
            "Prophet Security announced a strategic investment from Amex "
            "Ventures and Citi Ventures to scale its platform.")
    assert op.look_back_date(body, 'funding', _utc(2026, 10, 8)) == (
        _utc(2026, 2, 25), 'day')


def test_month_and_year_alone_read_as_month_precision():
    body = "In July 2025 we raised our $30M Series A led by Accel."
    assert op.look_back_date(body, 'funding', _utc(2026, 10, 8)) == (
        _utc(2025, 7, 1), 'month')


def test_day_first_british_order_is_read():
    assert op.stated_date("On 25 February 2026 we announced the round.") == (
        _utc(2026, 2, 25), 'day')


def test_a_recent_date_is_not_a_look_back():
    body = "On October 6, 2026 we announced our partnership with ExtraHop."
    assert op.look_back_date(body, 'partnership', _utc(2026, 10, 8)) is None


def test_an_older_date_outside_the_announcing_sentence_is_ignored():
    body = ("Since our Series A in July 2025 the team has doubled. Today we "
            "are launching Prophet AI Detection Engineer for every customer.")
    assert op.look_back_date(body, 'launch', _utc(2026, 10, 8)) is None


def test_no_date_keeps_the_post_date():
    assert op.look_back_date("We raised a new round led by Accel.", 'funding',
                             _utc(2026, 10, 8)) is None


def test_research_and_hiring_never_fetch_or_redate():
    row = {'title': 'On January 2, 2025 we published a benchmark',
           'summary': '', 'channel': 'owned_web', 'url': 'https://x.test/p'}
    assert op.dated_from_post(row, 'research', _utc(2026, 10, 8)) is None


def test_a_byline_under_the_title_is_the_posts_own_date():
    page = ("Why Prophet AI Company\n About us\n Careers\n\n"
            "Accelerating the Agentic AI SOC Movement with Amex Ventures\n\n"
            " February 25, 2026\n\n SOC teams are under more pressure than ever.")
    assert op.byline_date(page) == _utc(2026, 2, 25)


def test_a_date_inside_a_sentence_is_not_a_byline():
    assert op.byline_date("We announced it on February 25, 2026 to our customers.") is None
