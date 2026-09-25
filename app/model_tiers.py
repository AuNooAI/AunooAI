"""One default model per tier, by its real name.

Until 25 Sep 2026 every pipeline carried its own model literal, and most of
those literals were OpenAI names that litellm_config.yaml quietly sent to a
Bedrock model. Changing the model for a job meant editing forty files or
repointing the yaml, which moved every job at once.

Now a pipeline asks for a tier and gets the model that tier means on this
site. The names here are the ones in the yaml that run, never an alias, so
a settings row or a provenance record that copies the value names the model
that actually ran.

    MODEL_TIER_FAST / MODEL_TIER_STANDARD / MODEL_TIER_PREMIUM in .env
    override a tier for one site. An empty value counts as unset.

This module must stay free of litellm and app imports: request schemas use
it as a default factory and must not pull the model layer in at import.
"""
from __future__ import annotations

import os
from typing import Dict, List

# fast: cheap classification, extraction, per-article work.
# standard: writing that a customer reads (reports, briefings, Auspex).
# premium: the same as standard until a larger model is chosen.
#
# standard was the gpt-5.4 alias until 25 Sep 2026. It always ran on Claude
# Sonnet 4.5, but under that name the report pipelines sent it the reasoning
# shape (a 4x budget and no temperature). The switch to Sonnet's own name
# went through a before/after on the four pipelines (docs/changes.md).
TIERS: Dict[str, str] = {
    "fast": "bedrock-kimi-k2-5",
    "standard": "claude-sonnet-4-5",
    "premium": "claude-sonnet-4-5",
}


def default_model(tier: str = "standard") -> str:
    """The model this site runs for a tier: the env override, else TIERS."""
    if tier not in TIERS:
        raise KeyError(f"unknown model tier {tier!r}; one of {sorted(TIERS)}")
    return os.getenv(f"MODEL_TIER_{tier.upper()}", "").strip() or TIERS[tier]


def tier_models() -> Dict[str, str]:
    """Every tier with the model it resolves to on this site."""
    return {t: default_model(t) for t in TIERS}


def check_tiers_resolve() -> List[str]:
    """Names that the site's litellm_config.yaml cannot route.

    Called at startup so a site whose yaml lacks a tier's model fails
    loudly (a bare name would otherwise reach litellm with no provider and
    no key). Imports the model layer here, not at module load."""
    from app.ai_models import load_model_config
    known = load_model_config()
    return [name for name in tier_models().values() if name not in known]
