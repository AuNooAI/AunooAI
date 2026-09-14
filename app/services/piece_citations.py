"""Does each citation in a piece support the sentence it sits in?

Written after the site's first analysis cited Prophet Security's piece on
OpenAI Astra as an evaluation guide, called CrowdStrike's launch a source
for reasoning it did not contain, and said "one of its agents" where the
source did not say whose. The tells detector and the format checks cannot
see any of that: only a reader who opens the source can, and the operator
did. This does that reading with a cheap model, on every save of a piece,
and writes what it finds into the piece's lint so the dashboard shows it
in the same amber box as the other findings. Approval refuses to publish
while a citation is judged unsupported, unless the approver overrides.

The model is asked a narrow question per citation, with the sentence and
the source's title and summary in front of it: supported, partly, or not.
It cannot rewrite anything. A marker with no entry in the index, and an
entry whose article is not in the corpus, are findings without a model.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

CHECK = "citation"
DEFAULT_MODEL = os.getenv("PIECE_CITATION_MODEL",
                          os.getenv("MARKET_TOPICS_MODEL", "bedrock-kimi-k2-5"))
MAX_TOKENS = 4000
_MARKER_RE = re.compile(r"\[([AC]\d+)\]")
_SENT_RE = re.compile(r"(?<=[.!?])\s+")


def _index(row: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    facts = row.get("facts") or {}
    if isinstance(facts, str):
        try:
            facts = json.loads(facts)
        except ValueError:
            facts = {}
    return facts.get("citation_index") or {}


def _prompt(entries: List[Dict[str, Any]]) -> str:
    lines = []
    for e in entries:
        lines.append(f"\n[{e['id']}] SOURCE TITLE: {e.get('title') or ''}")
        if e.get("uri"):
            lines.append(f"SOURCE URL: {e['uri']}")
        if e.get("summary"):
            lines.append(f"SOURCE SUMMARY: {e['summary']}")
        for c in e["claims"]:
            lines.append(f"SENTENCE CITING IT: {c}")
    return ("For each citation below, judge whether the source, as described by its title, "
            "URL and summary, supports what the sentence uses it for. \"yes\" means the source "
            "says that. \"partly\" means the source is on the subject but the sentence claims "
            "more than it says, or attributes to it a reason, actor or detail the summary does "
            "not contain. \"no\" means the source is about something else or contradicts the "
            "sentence. Judge only the part of the sentence the citation is attached to; a "
            "sentence may cite two sources for two different things. The URL's domain says who "
            "published the source: a sentence naming the publisher — a vendor's own guide, an "
            "author writing on a company's site — is supported by the domain even when the "
            "summary does not repeat the name.\n"
            "Reply with JSON only: {\"citations\": [{\"id\": \"C1\", \"supports\": "
            "\"yes|partly|no\", \"why\": \"one short sentence\"}]}\n" + "\n".join(lines))


def check(conn, row: Dict[str, Any], model: Optional[str] = None) -> List[Dict[str, Any]]:
    """The lint entries for this piece's citations: [] when every citation
    holds. Each entry is {"check": "citation", "id", "severity", "detail"}."""
    import litellm

    from app.ai_models import extract_json_response, resolve_litellm_call_params

    body = row.get("report_content") or ""
    index = _index(row)
    sents = _SENT_RE.split(body)
    entries: List[Dict[str, Any]] = []
    findings: List[Dict[str, Any]] = []
    for cid in sorted(set(_MARKER_RE.findall(body)), key=lambda k: (k[0], int(k[1:]))):
        claims = [s.strip() for s in sents if f"[{cid}]" in s]
        ref = index.get(cid)
        if not ref:
            findings.append({"check": CHECK, "id": cid, "severity": "no",
                             "detail": f"{cid}: no source in the citation index"})
            continue
        art = conn.execute(text("SELECT title, summary FROM articles WHERE uri = :u"),
                           {"u": ref.get("uri")}).mappings().first()
        entries.append({"id": cid, "claims": claims, "uri": ref.get("uri") or "",
                        "title": (art["title"] if art else None) or ref.get("title") or "",
                        "summary": ((art["summary"] if art else "") or "")[:700]})
    if not entries:
        return findings
    model = model or DEFAULT_MODEL
    try:
        response = litellm.completion(
            **resolve_litellm_call_params(model),
            messages=[{"role": "system",
                       "content": "You check whether cited sources support the sentences that "
                                  "cite them. You judge from the source's title and summary "
                                  "only and reply with JSON only."},
                      {"role": "user", "content": _prompt(entries)}],
            max_tokens=MAX_TOKENS)
        raw = (response.choices[0].message.content or "").strip()
        parsed = extract_json_response(raw)
        verdicts = (parsed.get("citations") if isinstance(parsed, dict) else parsed) or []
    except Exception as exc:  # noqa: BLE001 — the check is advisory when the model is not
        logger.warning("piece citation check failed: %s", exc)
        findings.append({"check": CHECK, "id": "*", "severity": "unchecked",
                         "detail": f"citations not checked: {exc}"})
        return findings
    by_id = {str(v.get("id")): v for v in verdicts if isinstance(v, dict)}
    for e in entries:
        v = by_id.get(e["id"])
        if not v:
            findings.append({"check": CHECK, "id": e["id"], "severity": "unchecked",
                             "detail": f"{e['id']}: the model returned no verdict"})
            continue
        verdict = str(v.get("supports") or "").strip().lower()
        if verdict in ("partly", "no"):
            findings.append({"check": CHECK, "id": e["id"], "severity": verdict,
                             "detail": f"{e['id']} ({e['title'][:70]}) "
                                       f"{'does not support' if verdict == 'no' else 'only partly supports'} "
                                       f"the sentence: {str(v.get('why') or '').strip()[:220]}"})
    return findings


def merge_lint(existing: Any, findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The piece's lint with the citation entries replaced."""
    if isinstance(existing, str):
        try:
            existing = json.loads(existing)
        except ValueError:
            existing = []
    kept = [l for l in (existing or []) if isinstance(l, dict) and l.get("check") != CHECK]
    return kept + findings


def store(conn, market_id: int, briefing_id: int, findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    existing = conn.execute(text(
        "SELECT lint FROM bw_market_briefings WHERE market_id = :m AND id = :i"
    ), {"m": market_id, "i": briefing_id}).scalar()
    lint = merge_lint(existing, findings)
    conn.execute(text("UPDATE bw_market_briefings SET lint = CAST(:l AS JSONB) WHERE market_id = :m AND id = :i"),
                 {"l": json.dumps(lint), "m": market_id, "i": briefing_id})
    conn.commit()
    return lint


def run_and_store(conn, market_id: int, row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Check the piece and write the result into its lint. Returns the
    citation findings only."""
    findings = check(conn, row)
    store(conn, market_id, int(row["id"]), findings)
    return findings


def blocking(lint: Any) -> List[Dict[str, Any]]:
    """The citation findings that stop an approval: unsupported ones."""
    if isinstance(lint, str):
        try:
            lint = json.loads(lint)
        except ValueError:
            lint = []
    return [l for l in (lint or []) if isinstance(l, dict)
            and l.get("check") == CHECK and l.get("severity") == "no"]
