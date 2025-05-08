import logging
from typing import List

from fastapi import HTTPException, status
import litellm

logger = logging.getLogger(__name__)


DEFAULT_MODEL = "gpt-3.5-turbo"  # reference from litellm_config.yaml

# High-level background (condensed) to give the LLM enough context when
# suggesting options. We keep it short to avoid exceeding context limits.
BACKGROUND_SNIPPET = (
    "AuNoo follows strategic-foresight methodology.\n"
    "Categories: thematic sub-clusters inside a topic.\n"
    "Future Signals: concise hypotheses about possible future states.\n"
    "Sentiments: Positive / Neutral / Negative plus nuanced variants.\n"
    "Time to Impact: Immediate; Short-Term (3-18m); Mid-Term (18-60m); "
    "Long-Term (5y+).\n"
    "Driver Types: Accelerators, Blockers, Catalysts, Delayers, Initiators, "
    "Terminators."
)

# Map block kind to extra context that should precede the user prompt.
KIND_CONTEXT: dict[str, str] = {
    "categorization": (
        "Focus on concrete thematic clusters relevant to the scenario."
    ),
    "sentiment": (
        "Use Positive / Negative / Neutral or nuanced variants where helpful."
    ),
    "relationship": (
        "Think in terms of blocker, catalyst, accelerator, "
        "initiator or supporting datapoint."
    ),
    "weighting": (
        "Return objective scale descriptors "
        "(e.g., Highly objective, Anecdotal)."
    ),
    "classification": "Propose discrete, mutually exclusive classes.",
    "summarization": "No additional options required.",
    "keywords": "Return succinct single- or two-word tags.",
}


def suggest_options(kind: str, scenario_name: str, scenario_description: str | None = None) -> List[str]:
    """Ask the LLM for a short list of options suitable for the given building-block kind."""

    prompt_parts: list[str] = [
        BACKGROUND_SNIPPET,
        KIND_CONTEXT.get(kind.lower(), ""),
        (
            "Generate a concise comma-separated list of options "
            f"for a building-block of type '{kind}'."
        ),
        f"Scenario name: {scenario_name}.",
    ]
    if scenario_description:
        prompt_parts.append(f"Scenario description: {scenario_description}.")

    prompt_parts.append(
        "Return ONLY the list in plain text, no numbering, no explanations.",
    )

    prompt = "\n".join(prompt_parts)

    try:
        response = litellm.completion(model=DEFAULT_MODEL, messages=[{"role": "user", "content": prompt}])
        text = response.choices[0].message["content"].strip()
        # split by comma / newline
        options = [o.strip() for o in text.replace("\n", ",").split(",") if o.strip()]
        if not options:
            raise ValueError("LLM returned empty list")
        return options[:10]
    except Exception as exc:
        logger.error("Auspex LLM call failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="LLM suggestion failed") from exc 