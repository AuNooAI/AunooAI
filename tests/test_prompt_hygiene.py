"""Prompt hygiene: no new real-looking facts in prompt files.

The two worst defects of the 2026-08-03 Q3 review entered through worked
examples in our own prompts: a style example reading "1.4 million papers,
about one in forty" became the report's headline statistic, and the exec
agent's example event "Springer Nature retracted 1,200 Hindawi-linked
papers" put the customer's own retired imprint in the letter. Models copy
example content as findings.

Two checks:

* **Figure baseline** — every number-with-unit currently in the prompt
  files is frozen below. A new one fails the test until a human reviews it
  and either removes it or extends the baseline. The baseline entries are
  rule illustrations ("never write 'consensus 78% → 21%'"), not facts.
* **Banned names** — organisations that must never appear in any prompt,
  because a model quoting them as an example fact has already burned us.
"""
import glob
import json
import re

FIGURE_RE = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s*(?:%|percent|million|billion|trillion|lakh|crore)"
    r"|\bone in (?:ten|twenty|thirty|forty|fifty|\d+)\b",
    re.IGNORECASE,
)

# Frozen 2026-08-03. Every entry was reviewed: they are illustrations of
# FORM inside rules (thresholds, banned-phrasing examples), not copyable
# facts. Adding to this baseline requires the same review.
FIGURE_BASELINE = {
    "data/prompts/consensus_analysis/current.json": {"100%", "25%", "5%", "75%", "95%"},
    "data/prompts/market_signals/current.json": {"70%", "98%"},
    "data/auspex/agents/pam_trend_agent.md": {"15%", "20%", "25%"},
    "data/auspex/agents/report_writer.md": {"15%"},
    "data/auspex/agents/sio_deep_analysis_agent.md": {"0.25 percent", "0.25%"},
    "data/auspex/agents/sio_synthesis_agent.md": {"0.25%", "1.2%", "60%", "84%", "85%"},
    "data/auspex/agents/sio_triage_agent.md": {"0.25%"},
    "data/auspex/agents/wiley_analytics_agent.md": {"15 percent"},
    "data/auspex/agents/wiley_event_extractor_agent.md": {"18%"},
    "data/auspex/agents/wiley_exec_summary_agent.md": {"18%", "21%", "68%", "78%"},
    "data/auspex/agents/wiley_reviewer_agent.md": {"18%", "21%", "5%", "60%", "68%", "78%"},
}

# Names that have already been copied from a prompt into a customer
# artifact as fact, or that would be radioactive if they were. Never in
# any prompt, in any role.
BANNED_NAMES = ("Hindawi", "Novo Nordisk")


def _prompt_files():
    for path in sorted(glob.glob("data/prompts/**/*.json", recursive=True)):
        yield path
    for path in sorted(glob.glob("data/auspex/agents/*.md")):
        yield path


def _prompt_text(path: str) -> str:
    if path.endswith(".json"):
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            return ""
        return " ".join(str(d.get(k) or "") for k in ("system_prompt", "user_prompt"))
    return open(path, encoding="utf-8").read()


def test_no_new_figures_in_prompts():
    violations = []
    for path in _prompt_files():
        found = {m.group(0) for m in FIGURE_RE.finditer(_prompt_text(path))}
        new = found - FIGURE_BASELINE.get(path, set())
        if new:
            violations.append(f"{path}: {sorted(new)}")
    assert not violations, (
        "New figure(s) in prompt files — models copy example numbers into "
        "customer reports as facts (see the 1.4-million incident, "
        "docs/changes.md 2026-08-03). Remove them or, if they are genuine "
        "rule illustrations, extend FIGURE_BASELINE after review:\n"
        + "\n".join(violations)
    )


def test_no_banned_names_in_prompts():
    violations = []
    for path in _prompt_files():
        text = _prompt_text(path)
        for name in BANNED_NAMES:
            if name.lower() in text.lower():
                violations.append(f"{path}: {name}")
    assert not violations, (
        "Banned organisation name in a prompt file — a model has already "
        "copied a prompt-example name into a customer letter as fact:\n"
        + "\n".join(violations)
    )
