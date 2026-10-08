"""The consensus and horizons prompts take their years from today.

They used to show fixed example years (2025, 2025-2040) and the model copied
them: an October 2026 run gave milestones dated 2025."""
import re
from datetime import datetime

from app.routes import trend_convergence_routes as t

_ARTICLE = {"title": "A", "source": "S", "publication_date": "2026-10-01", "uri": "http://x",
            "summary": "s", "category": "c", "driver_type": "d", "future_signal": "f",
            "sentiment": "Positive", "time_to_impact": "Short-term"}
_PROFILE = {"name": "Buyer", "organization_type": "Enterprise security team"}


def _check(prompt: str) -> None:
    year = datetime.now().year
    assert f"TODAY IS {datetime.now().date().isoformat()}" in prompt
    assert not re.search(r"\{(today|current_year|year_plus_\d+)\}", prompt)
    assert f"{year}-{year + 2}" in prompt or f"{year}-{year + 7}" in prompt


def test_consensus_prompt_years_follow_today():
    _check(t.generate_consensus_analysis_prompt("T", [_ARTICLE], "", {"focus": "x"}, _PROFILE))


def test_horizons_prompt_years_follow_today():
    _check(t.generate_future_horizons_prompt("T", [_ARTICLE], "", _PROFILE))
