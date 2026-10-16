"""check_ai_tells on the monolith MCP server: runs the humanize_mcp regex
detector over a draft and returns flagged spans with fixes, a verdict and a
per-detector count. No database, no model call."""

import asyncio

import pytest


@pytest.fixture
def prose(monkeypatch):
    monkeypatch.setenv("NORN_SECRET_KEY", "test-secret-not-for-prod")
    from app.mcp_access import prose_tools
    return prose_tools


SLOPPY = (
    "In today's rapidly evolving landscape, it is crucial to delve into the multifaceted "
    "realm of AI security. It's not a tool, it's a testament to innovation. Moreover, robust, "
    "comprehensive and pivotal approaches underscore the significance of this shift."
)

PLAIN = (
    "Three vendors raised money this week. Vectra closed a 40 million dollar round on Monday. "
    "Two of the three rounds were led by existing investors, which is the pattern since June."
)


def test_sloppy_draft_is_flagged_with_fixes(prose):
    out = asyncio.run(prose.check_ai_tells(text=SLOPPY))
    assert out["verdict"] == "rewrite"
    assert out["tell_count"] >= 8
    assert "ai_vocabulary" in out["by_type"]
    first = out["tells"][0]
    assert set(first) == {"type", "label", "text", "start", "end", "fix"}
    assert first["start"] == 0 and first["fix"]
    assert SLOPPY[first["start"]:first["end"]] == first["text"]
    assert "check_ai_tells again" in out["next_step"]
    assert out["readability"]["word_count"] > 0


def test_plain_draft_passes(prose):
    out = asyncio.run(prose.check_ai_tells(text=PLAIN))
    assert out["verdict"] in ("clean", "acceptable")
    assert out["tell_count"] <= 1
    assert out["next_step"] == "No action needed." or out["verdict"] == "acceptable"


MARKED_UP = (
    "## What happened\n\n- Vectra closed a round on Monday, see [the filing](https://example.com/a).\n"
    "- Two of the three rounds were led by existing investors.\n\n## The tone\n\nFlat.\n\n## What to watch\n\nThe Q3 numbers land on Friday.\n"
)


def test_markdown_is_the_medium_by_default_but_a_tell_in_plain_text(prose):
    md = asyncio.run(prose.check_ai_tells(text=MARKED_UP))
    assert md["medium"] == "markdown"
    assert "markdown_formatting" not in md["by_type"]
    plain = asyncio.run(prose.check_ai_tells(text=MARKED_UP, medium="plain"))
    assert "markdown_formatting" in plain["by_type"]
    assert plain["tell_count"] == md["tell_count"] + plain["by_type"]["markdown_formatting"]


def test_unknown_medium_is_a_tool_error(prose):
    from app.mcp_access.errors import ToolError
    with pytest.raises(ToolError):
        asyncio.run(prose.check_ai_tells(text=MARKED_UP, medium="pdf"))


def test_empty_text_is_a_tool_error(prose):
    from app.mcp_access.errors import ToolError
    with pytest.raises(ToolError):
        asyncio.run(prose.check_ai_tells(text="   "))


def test_long_text_is_truncated_and_says_so(prose):
    out = asyncio.run(prose.check_ai_tells(text=("word " * 20000)))
    assert out["truncated_to_chars"] == prose.MAX_TEXT_CHARS


def test_missing_detector_is_reported_not_raised(prose, monkeypatch):
    def boom(_text):
        raise ImportError("no humanize_mcp")
    monkeypatch.setattr(prose, "_detect", boom)
    out = asyncio.run(prose.check_ai_tells(text=SLOPPY))
    assert "not installed" in out["error"]


def test_tool_is_registered_and_kept_out_of_suggestions(monkeypatch):
    monkeypatch.setenv("NORN_SECRET_KEY", "test-secret-not-for-prod")
    from app.mcp_access import tools
    spec, fn = tools.resolve("check_ai_tells")
    assert spec.required == ("text",)
    assert fn.__name__ == "check_ai_tells"
    assert "check_ai_tells" in {t.name for t in tools.available_tools()}
    # Older tenant trees have no suggestion pre-pass; the exclusion only applies where it exists.
    tool_suggestion = pytest.importorskip("app.mcp_access.tool_suggestion")
    assert "check_ai_tells" not in {c["name"] for c in tool_suggestion._catalogue()}


def test_prose_recipes_tell_the_assistant_to_check(monkeypatch):
    monkeypatch.setenv("NORN_SECRET_KEY", "test-secret-not-for-prod")
    from app.mcp_access import recipes
    for name in ("topic_briefing", "deep_dive", "keyword_scan", "brand_briefing"):
        msgs = recipes.render_recipe(name, {"topic": "AI Security", "query": "q", "keywords": "x", "brand": "b"})
        assert "check_ai_tells" in msgs[0]["content"][0]["text"], name
