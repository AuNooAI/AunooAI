"""A cut-off synthesis reply must fail loudly, not become a briefing with no themes.

On Sonnet 5 the synthesis hit its 3,000-token limit. extract_json_response then
decoded the first inner object it could (one theme), and the briefing shipped
with 0 themes and 0 decision points while the log said "Synthesis complete".
The model call is mocked; nothing reaches Bedrock.
"""
import asyncio
import json
from types import SimpleNamespace

import litellm
import pytest

from app.services import daily_report_service as drs

FULL = {
    "briefing_summary": "Two filings moved the market.",
    "themes": [{"name": "Filing pressure", "summary": "x", "supporting_items": [1]}],
    "priority_actions": [{"action": "Consider whether to wait", "urgency": "this_week", "rationale": "y"}],
}


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


def _synth(monkeypatch, raw, finish="stop"):
    sent = {}

    async def fake(**kw):
        sent.update(kw)
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=raw), finish_reason=finish)])

    monkeypatch.setattr(litellm, "acompletion", fake)
    svc = drs.DailyReportService.__new__(drs.DailyReportService)
    monkeypatch.setattr(svc, "_load_agent_prompt", lambda name: "", raising=False)
    monkeypatch.setattr(svc, "_get_agent_config", lambda name: {"model": "claude-sonnet-5"}, raising=False)
    out = _run_fresh(svc._run_synthesis("B", [{"title": "a"}], [], drs.DRConfig()))
    return out, sent


def test_full_reply_is_kept(monkeypatch):
    out, sent = _synth(monkeypatch, json.dumps(FULL))
    assert out["themes"][0]["name"] == "Filing pressure"
    assert sent["max_tokens"] == 6000


def test_cut_off_reply_falls_back_instead_of_inner_fragment(monkeypatch):
    raw = json.dumps(FULL)[:-60]  # cut mid priority_actions, after a complete theme object
    out, _ = _synth(monkeypatch, raw, finish="length")
    assert out["themes"] == []
    assert out["briefing_summary"].startswith("Briefing of 1 articles")
