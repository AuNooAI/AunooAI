"""The tool-suggestion pre-pass for the MCP server, with the TypeSafe Jev model.

An assistant connected over MCP picks from this site's tools on almost no
information: one line per tool, in a catalogue it also has to carry in its
context. TypeSafe's skill-suggestion recipe measured what that costs (an agent
loads the wrong skill about one turn in six, and loads one when none fits
about one in ten) and halved both with two cheap requests: skim every option
against the request and ask whether a tool is needed at all, then re-read
only the top three with their full descriptions and allow "none".

``suggest_tool`` does exactly that here. The assistant passes the user's
request; the tool returns at most one suggestion, the shortlist with fit
probabilities, and whether the request needs this site's data at all. The
assistant keeps its catalogue and its own judgement; the suggestion is one
line to read first. Every call is logged so the suggestion can later be
compared with the tool the assistant actually called next.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

from .errors import ToolError
from .tools import ToolSpec

SHORTLIST = 3
GATE = 0.30      # below this on "needs a tool", suggest nothing
FIT_MIN = 0.30   # a shortlist whose best fit is under this is dropped
MAX_REQUEST_CHARS = 4000


def _catalogue() -> list[dict[str, Any]]:
    from . import recipes, tools
    out = []
    for t in tools.available_tools():
        if t.name in ("suggest_tool",):
            continue
        out.append({"name": t.name, "kind": "tool", "description": t.description,
                    "arguments": sorted(t.properties.keys())})
    for r in recipes.list_recipes():
        out.append({"name": f"prompt:{r['name']}", "kind": "prompt", "description": r.get("description") or "",
                    "arguments": [a["name"] for a in (r.get("arguments") or [])]})
    return out


def _skim_questions(cat: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        "which": {
            "type": "choice",
            "instructions": "Which entry in `catalogue` best serves `request`? Each option is the entry's name; `catalogue` carries its one-line description.",
            "criteria": {c["name"]: (c["description"] or "")[:160] for c in cat},
        },
        "needs_tool": {
            "type": "noul",
            "instructions": "Does answering `request` require calling one of the site's tools or prompts at all, rather than replying from the conversation or general knowledge?",
            "criteria": {"true": "The request asks for something in this site's articles, brands, markets or analyses",
                         "false": "Small talk, a question about the assistant, or something answerable without the site"},
        },
        "needs_site_data": {
            "type": "noul",
            "instructions": "Does `request` depend on what this site's collected articles say (current news, coverage, sentiment, brands, markets), as opposed to general knowledge?",
            "criteria": {"true": "The answer changes with what was collected", "false": "It does not depend on the site's data"},
        },
    }


def _reread_questions(short: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    q: dict[str, dict[str, Any]] = {
        "pick": {
            "type": "choice",
            "instructions": "Reading `candidates` in full (description and arguments), which one should the assistant call first for `request`? Choose `none` when no candidate does what the request needs.",
            "criteria": {**{c["name"]: None for c in short}, "none": "No candidate fits; the assistant should answer without these or look elsewhere"},
        },
    }
    for i, c in enumerate(short):
        q[f"fit_{i}"] = {
            "type": "noul",
            "instructions": f"Does `candidates[{i}]` do what `request` needs, on its own?",
            "criteria": {"true": "Calling it with the right arguments produces what the request asks for",
                         "false": "It is on a related topic but does not produce what is asked"},
        }
    return q


def _call(state: Any, questions: dict[str, dict[str, Any]], use_case: str) -> dict[str, Any] | None:
    from app.services import typesafe_client
    if not typesafe_client.is_configured():
        return None
    return typesafe_client.system_one(state, questions, use_case=use_case, timeout_s=20.0)


def _log(ctx, request: str, row: dict[str, Any]) -> None:
    try:
        import json
        from sqlalchemy import text
        from app.database import get_database_instance
        conn = get_database_instance()._temp_get_connection()
        try:
            conn.execute(text("""
                INSERT INTO mcp_tool_suggestions
                    (username, api_key_id, request, needs_tool, needs_site_data, shortlist, suggested, suggested_p,
                     jev_model, latency_ms, error)
                VALUES (:username, :api_key_id, :request, :needs_tool, :needs_site_data, :shortlist, :suggested,
                        :suggested_p, :jev_model, :latency_ms, :error)
            """), {"username": getattr(ctx, "username", None), "api_key_id": getattr(ctx, "api_key_id", None),
                   "request": request[:4000], "needs_tool": row.get("needs_tool"), "needs_site_data": row.get("needs_site_data"),
                   "shortlist": json.dumps(row.get("shortlist") or []), "suggested": row.get("suggested"),
                   "suggested_p": row.get("suggested_p"), "jev_model": row.get("model"),
                   "latency_ms": row.get("latency_ms"), "error": row.get("error")})
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — logging never breaks the tool
        pass


def _suggest(request: str, ctx) -> dict[str, Any]:
    started = time.monotonic()
    cat = _catalogue()
    by_name = {c["name"]: c for c in cat}
    out: dict[str, Any] = {"request": request, "suggested": None, "suggested_p": None, "needs_tool": None,
                           "needs_site_data": None, "shortlist": [], "model": None, "latency_ms": None, "error": None}
    r1 = _call({"request": request, "catalogue": [{"name": c["name"], "kind": c["kind"], "description": (c["description"] or "")[:160]} for c in cat]},
               _skim_questions(cat), "mcp_access.tool_suggestion:skim")
    if not r1:
        out["error"] = "the decision model is not configured or did not answer"
        out["latency_ms"] = int((time.monotonic() - started) * 1000)
        return out
    try:
        a1 = r1["answers"]
        out["model"] = r1.get("model")
        out["needs_tool"] = float(a1["needs_tool"]["noul"])
        out["needs_site_data"] = float(a1["needs_site_data"]["noul"])
        probs = a1["which"].get("probabilities") or {}
    except (KeyError, TypeError, ValueError) as e:
        out["error"] = f"unreadable skim answers: {e}"
        out["latency_ms"] = int((time.monotonic() - started) * 1000)
        return out
    ranked = sorted(((float(p), n) for n, p in probs.items() if n in by_name), reverse=True)[:SHORTLIST]
    out["shortlist"] = [{"tool": n, "p_rank": round(p, 4)} for p, n in ranked]
    if out["needs_tool"] < GATE or not ranked:
        out["reason"] = "the request does not appear to need a tool"
        out["latency_ms"] = int((time.monotonic() - started) * 1000)
        return out
    short = [by_name[n] for _, n in ranked]
    r2 = _call({"request": request, "candidates": [{"name": c["name"], "kind": c["kind"], "description": c["description"],
                                                    "arguments": c["arguments"]} for c in short]},
               _reread_questions(short), "mcp_access.tool_suggestion:reread")
    if not r2:
        out["error"] = "the re-read did not answer"
        out["latency_ms"] = int((time.monotonic() - started) * 1000)
        return out
    try:
        a2 = r2["answers"]
        fits = [float(a2[f"fit_{i}"]["noul"]) for i in range(len(short))]
        for entry, f in zip(out["shortlist"], fits):
            entry["p_fit"] = round(f, 4)
        pick = a2["pick"]
        choice = pick.get("choice")
        pprob = float((pick.get("probabilities") or {}).get(choice, 0.0)) if choice else 0.0
    except (KeyError, TypeError, ValueError) as e:
        out["error"] = f"unreadable re-read answers: {e}"
        out["latency_ms"] = int((time.monotonic() - started) * 1000)
        return out
    if choice and choice != "none" and max(fits) >= FIT_MIN:
        out["suggested"] = choice
        out["suggested_p"] = round(pprob, 4)
        out["reason"] = f"best fit {max(fits):.2f}; pick confidence {float(pick.get('confidence') or 0.0):.2f}"
    else:
        out["reason"] = "no shortlisted tool fits well enough; answer without these or ask for more detail"
    out["latency_ms"] = int((time.monotonic() - started) * 1000)
    return out


async def suggest_tool(ctx=None, request: str | None = None) -> dict[str, Any]:
    if not request or not str(request).strip():
        raise ToolError("request is required: the user's message, as they wrote it")
    req = str(request).strip()[:MAX_REQUEST_CHARS]
    row = await asyncio.to_thread(_suggest, req, ctx)
    await asyncio.to_thread(_log, ctx, req, row)
    return {k: v for k, v in row.items() if k != "request"}


SPECS: dict[str, ToolSpec] = {
    "suggest_tool": ToolSpec(
        name="suggest_tool",
        description=(
            "Call this first with the user's request, verbatim. It ranks every tool and prompt on this site "
            "against the request with the site's decision model, re-reads the top three in full, and returns at "
            "most one suggestion with probabilities, or none when the request does not need a tool. Read it as "
            "a hint about which entry to look at first; keep your own judgement."
        ),
        properties={"request": {"type": "string", "description": "The user's request, as written."}},
        required=("request",),
        timeout=30.0,
    ),
}

HANDLERS: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {"suggest_tool": suggest_tool}
