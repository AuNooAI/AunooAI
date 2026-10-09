"""The topic report's executive summary must survive replies a strict parse rejects.

Sonnet 5 returned a 15k-char summary that both strict parses refused, and the
cards were skipped. These cases run generate_executive_summary_for_run with the
model call and the database mocked out, so nothing reaches Bedrock or Postgres.
"""
import asyncio
import json
from types import SimpleNamespace

import pytest

from app.services import topic_report_service as trs

CARDS = {"summaries": [{"title": "A", "body": "x"}, {"title": "B", "body": "y"}]}
GOOD = json.dumps(CARDS)


def _run_fresh(coro):
    # nest_asyncio (imported by other tests) swaps asyncio.run for one that
    # reuses the current loop, which an earlier test may have closed.
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        asyncio.set_event_loop(None)
        loop.close()


def _run(monkeypatch, raw):
    saved = {}

    class FakeFacade:
        def save_horizons_executive_summary(self, analysis_id, topic, summary_data):
            saved["data"] = summary_data

    import app.database as dbmod
    import app.services.prompt_loader as pl
    import litellm

    monkeypatch.setattr(dbmod, "get_database_instance", lambda: SimpleNamespace(facade=FakeFacade()))
    monkeypatch.setattr(trs, "_default_profile_text", lambda db: "")
    monkeypatch.setattr(pl.PromptLoader, "load_prompt", staticmethod(lambda *a, **k: {}))
    monkeypatch.setattr(pl.PromptLoader, "get_prompt_template", staticmethod(lambda *a, **k: ("sys", "user")))
    reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=raw))])
    monkeypatch.setattr(litellm, "completion", lambda **kw: reply)

    out = _run_fresh(trs.generate_executive_summary_for_run(
        "run-1", "Topic", [{"title": "s"}], model="claude-sonnet-5"))
    return out, saved


@pytest.mark.parametrize("raw", [
    GOOD,                                                  # bare JSON
    "```json\n" + GOOD + "\n```",                          # fenced
    "Here are the cards:\n" + GOOD + "\nHope this helps {see notes}.",  # braces in trailing prose
    "```json\n" + GOOD[:-1] + ",}\n```",                   # trailing comma inside a fence
    GOOD[:-2] + ',}]}',                                    # trailing comma, no fence
])
def test_exec_summary_parses(monkeypatch, raw):
    out, saved = _run(monkeypatch, raw)
    assert out is not None
    assert [c["title"] for c in out["summaries"]] == ["A", "B"]
    assert saved["data"]["analysis_id"] == "run-1"


def test_exec_summary_skips_reply_with_no_object(monkeypatch):
    out, saved = _run(monkeypatch, "I could not produce the summary.")
    assert out is None
    assert saved == {}


# The Three Horizons reply: Sonnet 5 finished normally with a trailing comma
# at char 2619 and the whole topic report failed (9 Oct 2026 gate).
HORIZONS = {"topic_briefing": {"headline": "h"}, "scenarios": [{"type": "H1", "title": "t"}]}


@pytest.mark.parametrize("raw", [
    json.dumps(HORIZONS),
    "```json\n" + json.dumps(HORIZONS) + "\n```",
    '{"topic_briefing": {"headline": "h",}, "scenarios": [{"type": "H1", "title": "t"},]}',
])
def test_horizons_reply_parses(raw):
    assert trs._parse_horizons_reply(raw)["scenarios"][0]["type"] == "H1"


def test_horizons_reply_without_scenarios_still_raises():
    with pytest.raises(RuntimeError, match="not valid JSON"):
        trs._parse_horizons_reply('{"topic_briefing": {"headline": "h",}')
