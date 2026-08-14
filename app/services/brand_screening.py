"""Adverse-media screening for Brand Watcher (Brand Risk v2).

Extracted from brand_watcher_routes.py per docs/BRAND_RISK_BENCHMARK_SPEC.md and
extended: every screened (article, brand) pair now gets a row in
bw_screening_verdicts — including an explicit no_risk_found — so screening coverage
is distinguishable from articles that were never looked at. Typed findings keep
going to bw_article_risks, now with a one-sentence justification for display on
issues.

Screening gate (widened from negative-or-risk-vocabulary): an article is screened
when it is negative, matches risk vocabulary, sits in a risk-relevant category, or
is explicitly forced (attention-spike coverage, backfill).
"""
import json
import logging
import re
from typing import List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Bump on any change to RISK_TYPES, the screening prompt, or the fallback rules —
# stored on every verdict so historical evaluations can name their screener.
PROMPT_VERSION = "v2.0"
SCREENING_MODEL = "gpt-5.4-mini"

RISK_TYPES = ["legal_regulatory", "financial_distress", "fraud_integrity",
              "esg", "executive_misconduct", "data_breach", "workforce_labor",
              "product_safety"]

# Categories whose articles get screened even when tone is neutral — hostile
# events often arrive in neutral-toned wire copy.
RISK_RELEVANT_CATEGORIES = {
    "Legal & Regulatory", "Customer & Product Issues",
    "Leadership & Governance", "Brand Sentiment & Perception",
}

# Cheap pre-screen: articles matching this vocabulary get the LLM risk pass even
# when sentiment is neutral, bounding cost to the adverse sliver of the stream.
RISK_TRIGGER_RE = re.compile(
    r"lawsuit|\bsues?\b|\bsued\b|litigat|\bcourt\b|regulator|antitrust|\bprobe\b|investigat|\bfine[sd]?\b|penalty|"
    r"\bfraud|scandal|misconduct|bribe|corrupt|plagiar|retract|falsif|"
    r"\bbreach|\bhack|ransom|\bleak\b|cyberattack|"
    r"bankrupt|insolven|default|downgrade|layoff|restructur|going concern|"
    r"boycott|discriminat|harass|greenwash|child labor|resign|ousted|fired|"
    r"\bstrikes?\b|\bunion\b|redundanc|walkout|tribunal|unfair dismissal|"
    r"toxic (workplace|culture)|pay dispute|wage theft|understaff|"
    r"\brecall(s|ed)?\b|defect|\bunsafe\b|safety (hazard|risk|concern|issue)|injur",
    re.IGNORECASE)

NEG_SENT_RE = re.compile(r"negativ|concern|pessimis|critical|alarm", re.IGNORECASE)


def should_screen(sentiment: str, text_content: str, categories=None, forced: bool = False) -> bool:
    """The screening gate: negative tone, risk vocabulary, risk-relevant category,
    or forced (attention spikes, backfill)."""
    if forced:
        return True
    if NEG_SENT_RE.search(str(sentiment or "")):
        return True
    if RISK_TRIGGER_RE.search(text_content or ""):
        return True
    return bool(RISK_RELEVANT_CATEGORIES.intersection(categories or ()))


def keyword_risk_fallback(text_content: str) -> list:
    """Heuristic risk tagging when the LLM is unavailable."""
    t = (text_content or "").lower()
    found = []
    def add(rt, sev): found.append({"risk_type": rt, "severity": sev, "confidence": 0.4})
    if re.search(r"lawsuit|\bsues?\b|\bsued\b|litigat|regulator|antitrust|\bprobe\b|investigat|\bfine[sd]?\b|penalty|\bcourt\b", t): add("legal_regulatory", "medium")
    if re.search(r"bankrupt|insolven|default|downgrade|going concern|layoff|restructur", t): add("financial_distress", "medium")
    if re.search(r"fraud|scandal|bribe|corrupt|plagiar|retract|falsif", t): add("fraud_integrity", "high")
    if re.search(r"boycott|discriminat|harass|greenwash|child labor|environmental damage", t): add("esg", "medium")
    if re.search(r"misconduct|resign|ousted|fired.*(ceo|cfo|executive|director)|(ceo|cfo|executive|director).*(misconduct|resign|ousted|fired)", t): add("executive_misconduct", "medium")
    if re.search(r"\bbreach|\bhack|ransom|cyberattack|data leak", t): add("data_breach", "high")
    # Bare "union"/"strike" collide with ordinary prose ("union of ideas", "striking
    # design") — the fallback (which tags directly, no LLM adjudication) needs the
    # compound forms only.
    if re.search(r"(trade|labou?r|staff) union|union (members?|dispute|vote|action|strike)|(staff|workers?|employees?) (strike|walkout)|strike (action|ballot)|redundanc|tribunal|unfair dismissal|toxic (workplace|culture)|pay dispute|wage theft|mass layoff", t): add("workforce_labor", "medium")
    # Same collision logic: "recall" alone matches memory/recollection prose.
    if re.search(r"(product|safety|vehicle|device|consumer) recall|recall(s|ed)? (its|their|the|all|products?|units)|safety (hazard|defect)|defective (product|unit|device)|caused injur", t): add("product_safety", "high")
    return found


async def llm_detect_risks(title: str, summary: str, brand_name: str) -> Optional[list]:
    """LLM risk classification. Returns a list of
    {risk_type, severity, confidence, justification} or None on failure."""
    from app.ai_models import LiteLLMModel, extract_content
    prompt = f"""You are an adverse-media screening analyst. Does this article describe an ADVERSE event involving the company "{brand_name}"?

Article Title: {title}
Article Summary: {(summary or "")[:1500]}

Risk types (use ONLY these keys): legal_regulatory (lawsuits, regulatory action, fines, probes), financial_distress (bankruptcy risk, downgrades, defaults), fraud_integrity (fraud, corruption, research/publication integrity, retractions), esg (environmental/social harms, consumer discrimination, boycotts), executive_misconduct (leadership scandals, forced departures), data_breach (hacks, breaches, ransomware), workforce_labor (strikes, union disputes, mass layoffs/redundancies, employment tribunals, unfair-dismissal or workplace-discrimination claims, toxic-culture allegations, pay disputes), product_safety (product recalls, safety defects, hazards, harm to users).

Rules:
- Only flag risks where {brand_name} is the SUBJECT of the adverse event (not merely mentioned, not the plaintiff suing someone else unless it exposes them to counter-risk).
- Routine negative sentiment (bad quarter, critical review) is NOT a risk finding unless it fits a type above.
- severity: high = material/ongoing threat; medium = notable; low = minor/speculative.
- justification: one factual sentence naming the event, no adjectives beyond the facts.

Respond with ONLY a JSON array (empty [] if none): [{{"risk_type": "...", "severity": "high|medium|low", "confidence": 0.0-1.0, "justification": "..."}}]"""
    try:
        model = LiteLLMModel.get_instance(SCREENING_MODEL)
        response = await model.agenerate_response(
            [{"role": "user", "content": prompt}], max_tokens=300, temperature=0.0)
        raw = extract_content(response).strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.MULTILINE).strip()
        # The model sometimes appends prose after the array — parse the FIRST JSON
        # value and ignore trailing text.
        start = raw.find("[")
        if start < 0:
            return []
        data, _ = json.JSONDecoder().raw_decode(raw[start:])
        out = []
        for item in (data if isinstance(data, list) else []):
            rt = (item.get("risk_type") or "").strip()
            if rt in RISK_TYPES:
                sev = item.get("severity") if item.get("severity") in ("high", "medium", "low") else "medium"
                out.append({"risk_type": rt, "severity": sev,
                            "confidence": max(0.0, min(1.0, float(item.get("confidence") or 0.5))),
                            "justification": (item.get("justification") or "")[:500] or None})
        return out
    except Exception as e:
        logger.debug(f"LLM risk detection failed: {e}")
        return None


def store_article_risks(conn, uri: str, brand_id: int, risks: list, method: str) -> None:
    for r in risks:
        try:
            conn.execute(text("""
                INSERT INTO bw_article_risks (article_uri, brand_id, risk_type, severity, confidence, method, justification)
                VALUES (:u, :b, :rt, :sev, :c, :m, :j)
                ON CONFLICT (article_uri, brand_id, risk_type)
                DO UPDATE SET severity = :sev, confidence = :c, method = :m,
                              justification = COALESCE(:j, bw_article_risks.justification),
                              detected_at = NOW()
            """), {"u": uri, "b": brand_id, "rt": r["risk_type"], "sev": r["severity"],
                   "c": r.get("confidence"), "m": method, "j": r.get("justification")})
        except Exception as e:
            logger.warning(f"risk store failed for {uri}: {e}")


def record_verdict(conn, uri: str, brand_id: int, outcome: str, method: str) -> None:
    try:
        conn.execute(text("""
            INSERT INTO bw_screening_verdicts (article_uri, brand_id, outcome, method, model, prompt_version)
            VALUES (:u, :b, :o, :m, :mo, :pv)
            ON CONFLICT (article_uri, brand_id)
            DO UPDATE SET outcome = :o, method = :m, model = :mo, prompt_version = :pv,
                          screened_at = NOW()
        """), {"u": uri, "b": brand_id, "o": outcome, "m": method,
               "mo": SCREENING_MODEL if method == "llm" else None, "pv": PROMPT_VERSION})
    except Exception as e:
        logger.warning(f"verdict store failed for {uri}: {e}")


async def screen_article(conn, uri: str, brand_id: int, brand_display_name: str,
                         title: str, summary: str, sentiment: str = "",
                         categories=None, forced: bool = False) -> Optional[str]:
    """Screen one (article, brand) pair. Returns the verdict outcome
    ('risk_found' | 'no_risk_found'), or None when the gate said skip.
    The caller owns the transaction (commit)."""
    text_input = f"{title or ''} {summary or ''}"
    if not should_screen(sentiment, text_input, categories, forced):
        return None
    risks = await llm_detect_risks(title or "", summary or "", brand_display_name)
    method = "llm"
    if risks is None:
        risks = keyword_risk_fallback(text_input)
        method = "keyword"
    if risks:
        store_article_risks(conn, uri, brand_id, risks, method)
    outcome = "risk_found" if risks else "no_risk_found"
    record_verdict(conn, uri, brand_id, outcome, method)
    return outcome
