"""Model names: what runs decides the call, not the name asked for.

Covers app.model_tiers (one default per tier), ai_models.model_caps (limits
and call shape from the yaml target), the invariants the litellm yaml must
keep, the call shapes the report pipelines send, and a guard that fails if a
legacy alias name comes back into app/ as a literal. No database.
"""
from __future__ import annotations

import io
import os
import tokenize
from pathlib import Path

import pytest
import yaml

from app import ai_models, model_tiers
from app.ai_models import is_reasoning_model, model_caps
from app.model_tiers import TIERS, check_tiers_resolve, default_model

ROOT = Path(__file__).resolve().parents[1]
YAML = ROOT / "app" / "config" / "litellm_config.yaml"

SONNET = "bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0"
KIMI = "bedrock/moonshotai.kimi-k2.5"
FAKE_YAML = {
    "gpt-5.4": {"model": SONNET, "additional_drop_params": ["reasoning_effort", "response_format"]},
    "claude-sonnet-4-5": {"model": SONNET, "additional_drop_params": ["reasoning_effort", "response_format"]},
    "claude-sonnet-5": {"model": "bedrock/us.anthropic.claude-sonnet-5",
                        "additional_drop_params": ["reasoning_effort", "temperature", "top_p", "top_k"]},
    "bedrock-kimi-k2-5": {"model": KIMI, "additional_drop_params": ["reasoning_effort", "response_format", "thinking"]},
    "gpt-5.4-mini": {"model": KIMI, "additional_drop_params": ["reasoning_effort", "response_format", "thinking"]},
    "openai-gpt-5.5": {"model": "openai/gpt-5.5"},
    "nova-lite": {"model": "bedrock/us.amazon.nova-lite-v1:0"},
}


@pytest.fixture
def fake_yaml(monkeypatch):
    monkeypatch.setattr(ai_models, "load_model_config", lambda: FAKE_YAML)


# --- tiers -------------------------------------------------------------------

def test_default_model_reads_env_and_treats_empty_as_unset(monkeypatch):
    monkeypatch.delenv("MODEL_TIER_FAST", raising=False)
    assert default_model("fast") == TIERS["fast"]
    monkeypatch.setenv("MODEL_TIER_FAST", "nova-lite")
    assert default_model("fast") == "nova-lite"
    monkeypatch.setenv("MODEL_TIER_FAST", "   ")
    assert default_model("fast") == TIERS["fast"]
    with pytest.raises(KeyError):
        default_model("turbo")


def test_check_tiers_resolve_names_missing_models(fake_yaml, monkeypatch):
    for t in TIERS:
        monkeypatch.delenv(f"MODEL_TIER_{t.upper()}", raising=False)
    assert check_tiers_resolve() == []
    monkeypatch.setenv("MODEL_TIER_PREMIUM", "not-in-yaml")
    assert check_tiers_resolve() == ["not-in-yaml"]


def test_tiers_resolve_on_this_sites_yaml(monkeypatch):
    for t in TIERS:
        monkeypatch.delenv(f"MODEL_TIER_{t.upper()}", raising=False)
    assert check_tiers_resolve() == []


# --- caps --------------------------------------------------------------------

def test_caps_come_from_the_target_not_the_name(fake_yaml):
    alias, honest = model_caps("gpt-5.4"), model_caps("claude-sonnet-4-5")
    assert alias.target == honest.target == SONNET
    assert (alias.family, alias.context, alias.max_output) == ("claude-sonnet-4-5", 200_000, 64_000)
    assert alias.reasoning is False and alias.bedrock is True and alias.supports_temperature is True
    assert model_caps("gpt-5.4-mini").reasoning is True  # it runs on Kimi


def test_caps_special_cases(fake_yaml):
    assert model_caps("claude-sonnet-5").supports_temperature is False
    openai = model_caps("openai-gpt-5.5")
    assert openai.reasoning is True and openai.bedrock is False and openai.family == "gpt-5"
    nova = model_caps("nova-lite")
    assert (nova.family, nova.context, nova.max_output, nova.reasoning) == ("nova", 300_000, 5_000, False)
    unknown = model_caps("qwen3:14b")
    assert (unknown.family, unknown.context, unknown.max_output, unknown.reasoning) == ("other", 32_768, 4_096, False)
    assert model_caps(None).family == "other"


def test_is_reasoning_model_truth_table(fake_yaml):
    # A gpt-5 name that runs on Bedrock Sonnet is a plain model.
    assert is_reasoning_model("gpt-5.4") is False
    assert is_reasoning_model("gpt-5.4-mini") is True
    assert is_reasoning_model("bedrock-kimi-k2-5") is True
    assert is_reasoning_model("openai-gpt-5.5") is True
    assert is_reasoning_model("claude-sonnet-4-5") is False
    assert is_reasoning_model("nova-lite") is False
    assert is_reasoning_model("") is False


# --- the yaml this site runs on ---------------------------------------------

def _entries():
    return yaml.safe_load(YAML.read_text())


def test_yaml_bedrock_claude_entries_drop_reasoning_effort():
    """The Wiley reviewer sends reasoning_effort='high'; on a Bedrock Claude
    target only this drop list keeps it from switching extended thinking on
    next to a temperature, which Bedrock rejects."""
    for e in _entries()["model_list"]:
        p = e["litellm_params"]
        if p["model"].startswith("bedrock/") and "anthropic" in p["model"]:
            assert "reasoning_effort" in (p.get("additional_drop_params") or []), e["model_name"]


def test_yaml_every_legacy_alias_has_a_fallback():
    cfg = _entries()
    with_fallback = {k for f in cfg.get("fallbacks", []) for k in f}
    for e in cfg["model_list"]:
        if (e.get("model_info") or {}).get("legacy_alias"):
            assert e["model_name"] in with_fallback, e["model_name"]


def test_listers_hide_legacy_aliases():
    tagged = {e["model_name"] for e in _entries()["model_list"] if (e.get("model_info") or {}).get("legacy_alias")}
    listed = {m["name"] for m in ai_models.get_available_models()}
    assert not (tagged & listed)
    assert tagged <= {m["name"] for m in ai_models.get_available_models(include_hidden=True)} or not listed


def test_load_model_config_keeps_model_info():
    cfg = ai_models.load_model_config()
    assert cfg["gpt-5.4"]["model_info"].get("legacy_alias") is True
    assert "model_info" in cfg["bedrock-kimi-k2-5"]


# --- call shapes the pipelines send ------------------------------------------

def test_daily_report_and_auspex_call_shapes(fake_yaml):
    from app.services.daily_report_service import _llm_token_kwargs
    from app.services.auspex_service import _llm_call_kwargs
    assert _llm_token_kwargs("gpt-5.4", output_tokens=1000) == {"max_tokens": 1000}
    assert _llm_token_kwargs("bedrock-kimi-k2-5", output_tokens=1000) == {"reasoning_effort": "minimal", "max_completion_tokens": 4000}
    assert _llm_token_kwargs("claude-sonnet-4-5", output_tokens=1000) == {"max_tokens": 1000}
    assert _llm_token_kwargs("nova-lite", output_tokens=1000) == {"max_tokens": 1000}
    assert _llm_call_kwargs("gpt-5.4", output_tokens=4000) == {"max_tokens": 4000, "temperature": 0.7}
    assert _llm_call_kwargs("openai-gpt-5.5", output_tokens=40000) == {"reasoning_effort": "none", "max_completion_tokens": 128000}
    assert _llm_call_kwargs("bedrock-kimi-k2-5", output_tokens=40000)["max_completion_tokens"] == 64000
    assert _llm_call_kwargs("claude-sonnet-4-5", output_tokens=4000) == {"max_tokens": 4000, "temperature": 0.7}


def test_sample_sizes_no_longer_treat_a_200k_model_as_mega(fake_yaml):
    from app.routes.trend_convergence_routes import calculate_optimal_sample_size
    from app.routes.executive_summary_routes import _calculate_optimal_sample_size
    assert calculate_optimal_sample_size("gpt-5.4") == calculate_optimal_sample_size("claude-sonnet-4-5") == 90
    assert _calculate_optimal_sample_size("gpt-5.4") == 75


# --- no alias literal comes back ---------------------------------------------

# Files that may name an alias: the price table, the disclosure labels, the
# tier module itself, schema history, and the alias-tagging script.
GUARD_ALLOW_FILES = {
    "app/model_tiers.py", "app/services/llm_usage_logger.py", "app/compliance/ai_disclosure.py",
    "app/utils/db_manager.py", "app/utils/create_new_db.py", "app/database_models.py",
}
# Lines that use a name as a family prefix or a search keyword, not a model.
GUARD_ALLOW_LINES = {
    ("app/services/pam_event_extraction_service.py", "gpt-5.4"),
    ("app/ai_models.py", "gpt-5"),
    ("app/services/relevance_scorer.py", "gpt-5"),
}


def _quoted_literals(path: Path, names: set) -> list:
    src = path.read_text()
    if not any(n in src for n in names):
        return []
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    out = []
    for i, t in enumerate(toks):
        if t.type != tokenize.STRING:
            continue
        val = t.string.strip("'\"")
        if val not in names or t.string not in (f'"{val}"', f"'{val}'"):
            continue
        nxt = next((x for x in toks[i + 1:] if x.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT)), None)
        if nxt is not None and nxt.string == ":":
            continue  # a dict key in a limits or price table
        out.append((t.start[0], val))
    return out


def test_no_legacy_alias_literal_in_app():
    legacy = {e["model_name"] for e in _entries()["model_list"] if (e.get("model_info") or {}).get("legacy_alias")}
    bad = []
    for p in sorted((ROOT / "app").rglob("*.py")):
        rel = str(p.relative_to(ROOT))
        if rel in GUARD_ALLOW_FILES or ".bak" in p.name:
            continue
        try:
            hits = _quoted_literals(p, legacy)
        except (UnicodeDecodeError, tokenize.TokenError):
            continue
        bad += [f"{rel}:{ln} {val}" for ln, val in hits if (rel, val) not in GUARD_ALLOW_LINES]
    assert not bad, "legacy model names used as literals (name the model that runs, or a tier):\n" + "\n".join(bad)
