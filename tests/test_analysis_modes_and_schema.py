"""Analysis modes, parsing and the fixed output block (WP3b, WP6c, WP6d; M3).

A fake model returns scripted responses; prompts and cache live in tmp
directories, never in the site's data/prompts.
"""
import time

import pytest

from app.analyzers import analysis_schema as schema
from app.analyzers import prompt_templates as pt
from app.analyzers.prompt_manager import PromptManager, PromptSchemaError

LISTS = dict(categories=["Policy", "Markets"], future_signals=["Growth", "Decline"],
             sentiment_options=["Positive", "Negative", "Neutral"],
             time_to_impact_options=["Immediate", "Long-term"], driver_types=["Accelerator", "Blocker"])


def _reply(sentiment="Positive", summary="The CEO said: profits rose 5%.", extra=""):
    return "\n".join([
        "Title: Big news",
        f"Summary: {summary}",
        "Category: Policy",
        "Future Signal: Growth",
        "Future Signal Explanation: Because.",
        f"Sentiment: {sentiment}",
        "Sentiment Explanation: Upbeat.",
        "Time to Impact: Immediate",
        "Time to Impact Explanation: Now.",
        "Driver Type: Accelerator",
        "Driver Type Explanation: Pushes.",
    ] + ([extra] if extra else []) + ["Tags: chip making, export controls"])


class FakeModel:
    model_name = "fake-model"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def generate_response(self, messages, **kw):
        self.calls.append((messages, kw))
        return self.replies.pop(0) if self.replies else ""


@pytest.fixture
def make(tmp_path, monkeypatch):
    store = tmp_path / "prompts"
    monkeypatch.setattr(pt, "PromptManager", lambda: PromptManager(storage_dir=str(store)))
    from app.analyzers.article_analyzer import ArticleAnalyzer

    def _make(replies, use_cache=True):
        model = FakeModel(replies)
        return ArticleAnalyzer(model, cache_dir=str(tmp_path / "cache"), use_cache=use_cache), model
    return _make


def _run(an, mode="auto", text="Article body " * 30, uri="https://x.test/a", **kw):
    return an.analyze_content(text, "Big news", "x.test", uri, 50, "neutral", "informative",
                              mode=mode, **LISTS, **kw)


def test_colons_and_multiline_values_survive(make):
    reply = _reply(summary="The CEO said: profits rose.\nNote: guidance is unchanged.")
    an, _ = make([reply])
    out = _run(an)
    assert out["summary"] == "The CEO said: profits rose.\nNote: guidance is unchanged."
    assert out["sentiment"] == "Positive" and out["tags"] == ["chip making", "export controls"]


def test_aliases_and_markdown_headings_are_read(make):
    reply = _reply().replace("Driver Type Explanation:", "**Driver Signal Explanation:**").replace(
        "Tags:", "Relevant tags:")
    an, _ = make([reply])
    out = _run(an)
    assert out["driver_type_explanation"] == "Pushes." and out["tags"] == ["chip making", "export controls"]


def test_auto_mode_uses_the_auto_prompt_and_omits_bias_fields(make):
    an, model = make([_reply()])
    out = _run(an, mode="auto")
    user = model.calls[0][0][1]["content"]
    assert "Political Bias" not in user and "Factuality" not in user and schema.SEPARATOR in user
    assert "political_bias" not in out and "factuality" not in out
    assert out["publication_date"] is None and len(model.calls) == 1  # no date call


def test_manual_mode_keeps_bias_fields_and_extracts_the_date(make):
    reply = _reply(extra="Political Bias: Center\nPolitical Bias Explanation: Even.\n"
                         "Factuality: High\nFactuality Explanation: Sourced.")
    an, model = make([reply, "2026-10-01"])
    out = _run(an, mode="manual")
    assert out["political_bias"] == "Center" and out["factuality"] == "High"
    assert out["publication_date"].startswith("2026-10-01") and len(model.calls) == 2
    assert "Political Bias" in model.calls[0][0][1]["content"]


def test_an_off_list_sentiment_retries_then_fails(make):
    from app.analyzers.article_analyzer import ArticleAnalyzerError
    an, model = make([_reply(sentiment="Ecstatic")] * 3, use_cache=False)
    with pytest.raises(ArticleAnalyzerError, match="sentiment"):
        _run(an)
    assert len(model.calls) == 3


def test_an_off_list_sentiment_recovers_on_retry(make):
    an, model = make([_reply(sentiment="Ecstatic"), _reply()], use_cache=False)
    assert _run(an)["sentiment"] == "Positive" and len(model.calls) == 2


def test_an_auto_cache_entry_never_answers_a_manual_request(make):
    manual_reply = _reply(extra="Political Bias: Center\nPolitical Bias Explanation: Even.\n"
                                "Factuality: High\nFactuality Explanation: Sourced.")
    an, model = make([_reply(), manual_reply, "2026-10-01"])
    _run(an, mode="auto")
    out = _run(an, mode="manual")
    assert len(model.calls) == 3 and out["factuality"] == "High"
    # Same mode again is a cache hit; a changed list or text is not.
    _run(an, mode="auto")
    assert len(model.calls) == 3
    an.ai_model.replies = [_reply()]
    _run(an, mode="auto", text="Different body " * 30)
    assert len(model.calls) == 4


def test_a_superseded_attempt_neither_caches_nor_returns(make):
    from app.analyzers.article_analyzer import AnalysisSuperseded
    an, model = make([_reply(), _reply()])
    with pytest.raises(AnalysisSuperseded):
        _run(an, is_current=lambda: False)
    _run(an)  # the next attempt must call the model, not find a cached late result
    assert len(model.calls) == 2


def test_a_passed_deadline_starts_no_model_call(make):
    from app.analyzers.article_analyzer import AnalysisDeadlineExceeded
    an, model = make([_reply()], use_cache=False)
    with pytest.raises(AnalysisDeadlineExceeded):
        _run(an, deadline=time.monotonic() - 1)
    assert model.calls == []


def test_the_model_call_gets_the_remaining_budget_as_its_timeout(make):
    an, model = make([_reply()], use_cache=False)
    _run(an, deadline=time.monotonic() + 30)
    assert 25 < model.calls[0][1]["timeout"] <= 30


# --- the fixed output block ------------------------------------------------

def _pm(tmp_path):
    pm = PromptManager(storage_dir=str(tmp_path / "pm"))
    pm.initialize_defaults(pt.PromptTemplates.DEFAULT_TEMPLATES)
    return pm


def test_defaults_seed_both_prompts_with_the_block(tmp_path):
    pm = _pm(tmp_path)
    for t in schema.SCHEMA_PROMPT_TYPES:
        assert schema.schema_problem(t, pm.get_current_version(t)["user_prompt"]) is None


def test_instructions_can_change_but_the_block_cannot(tmp_path):
    pm = _pm(tmp_path)
    cur = pm.get_current_version(schema.MANUAL)
    instr, block = schema.split(cur["user_prompt"])
    pm.save_version(schema.MANUAL, cur["system_prompt"], "Be brief.\n\n" + block)
    # Keeps the heading, renames a field: rejected.
    with pytest.raises(PromptSchemaError):
        pm.save_version(schema.MANUAL, cur["system_prompt"],
                        instr + "\n\n" + block.replace("Sentiment:", "Mood:"))
    # Drops the block entirely: rejected.
    with pytest.raises(PromptSchemaError):
        pm.save_version(schema.MANUAL, cur["system_prompt"], instr)
    # Smuggled through additional fields after the merge: rejected.
    with pytest.raises(PromptSchemaError):
        pm.save_version(schema.MANUAL, cur["system_prompt"], cur["user_prompt"],
                        {"user_prompt": instr})
    # The auto block is not a valid manual block.
    with pytest.raises(PromptSchemaError):
        pm.save_version(schema.MANUAL, cur["system_prompt"], instr + "\n\n" + schema.output_block(schema.AUTO))


def test_restoring_an_old_free_text_version_is_refused_and_migration_fixes_it(tmp_path):
    import json, os
    pm = _pm(tmp_path)
    old = {"system_prompt": "s", "user_prompt": "Do it.\n\nOUTPUT FORMAT\nTitle: <title>",
           "version": "0.9.0", "created_at": "2026-01-01T00:00:00"}
    path = os.path.join(str(tmp_path / "pm"), schema.MANUAL, "oldversion.json")
    json.dump(old, open(path, "w"))
    with pytest.raises(PromptSchemaError):
        pm.restore_version(schema.MANUAL, "oldversion")
    # A live prompt from before the block existed is migrated explicitly.
    json.dump(old, open(os.path.join(str(tmp_path / "pm"), schema.MANUAL, "current.json"), "w"))
    saved = pm.migrate_output_block(schema.MANUAL)
    assert saved["schema_migration"] == schema.SCHEMA_VERSION
    assert saved["user_prompt"].startswith("Do it.") and schema.schema_problem(schema.MANUAL, saved["user_prompt"]) is None
    assert pm.migrate_output_block(schema.MANUAL) is None


def test_the_save_route_answers_422(tmp_path, monkeypatch):
    import os
    os.environ.setdefault("NORN_SECRET_KEY", "test-secret-not-for-prod")
    os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-not-for-prod")
    from fastapi import FastAPI
    from starlette.testclient import TestClient
    # prompt_routes builds a PromptManager on the live store at import; keep
    # that from touching data/prompts while it loads.
    monkeypatch.setattr(PromptManager, "_ensure_storage_dir", lambda self: None)
    monkeypatch.setattr(PromptManager, "initialize_defaults", lambda self, d: None)
    from app.routes import prompt_routes
    from app.security.session import verify_session
    pm = _pm(tmp_path)
    monkeypatch.setattr(prompt_routes, "prompt_manager", pm)
    app = FastAPI()
    app.include_router(prompt_routes.router)
    app.dependency_overrides[verify_session] = lambda: {"user": "t"}
    client = TestClient(app)
    r = client.post(f"/api/prompts/{schema.AUTO}", json={"system_prompt": "s", "user_prompt": "free text"})
    assert r.status_code == 422 and "exactly once" in r.json()["detail"]
