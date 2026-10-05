"""MCP tools that expose typed judgments from the TypeSafe Jev decision model.

Two tools, registered into the catalogue by ``tools.py``:

``typed_judgment``  the raw primitive. The caller supplies a ``state`` (text or
    JSON) and a map of typed questions (choice / score / noul, with
    instructions and criteria) and gets one typed answer per question:
    probabilities, never prose. An assistant on the other end of MCP can ask
    "is this about X" or "which of these five categories" without a round
    trip to a generative model, and can branch on the probability.

``judge_articles``  the convenience form for this site's own articles. The
    caller names article URIs (from any other tool's results) and one yes/no
    question; each article's title and summary is judged separately and the
    tool returns a probability per article, so a caller can rerank, filter or
    verify what it was given. Only readable articles (the site's relevance
    floor) are judged, the same gate every other article tool applies.

Both are metered like every tool call (the dispatcher records them) and
bounded: at most 24 questions per request and 40 articles per call. They
never raise; a failed call is returned as an ``error`` field.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from .errors import ToolError
from .tools import ToolSpec

MAX_QUESTIONS = 24
MAX_ARTICLES = 40
MAX_STATE_CHARS = 60_000
_ALLOWED_TYPES = {"choice", "score", "noul"}


def _validate_questions(questions: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(questions, dict) or not questions:
        raise ToolError("questions must be a non-empty object of {id: {type, instructions, criteria}}")
    if len(questions) > MAX_QUESTIONS:
        raise ToolError(f"at most {MAX_QUESTIONS} questions per call")
    out: dict[str, dict[str, Any]] = {}
    for qid, q in questions.items():
        if not isinstance(q, dict):
            raise ToolError(f"question {qid!r} must be an object")
        t = str(q.get("type") or "").lower()
        if t not in _ALLOWED_TYPES:
            raise ToolError(f"question {qid!r}: type must be one of choice, score, noul")
        if not q.get("instructions"):
            raise ToolError(f"question {qid!r}: instructions are required")
        crit = q.get("criteria")
        if t == "choice" and (not isinstance(crit, dict) or len(crit) < 2):
            raise ToolError(f"question {qid!r}: a choice needs criteria as an object of at least two options")
        if t == "score" and (not isinstance(crit, list) or len(crit) < 2):
            raise ToolError(f"question {qid!r}: a score needs criteria as an ordered list of at least two levels")
        spec = {"type": t, "instructions": q["instructions"]}
        if crit is not None:
            spec["criteria"] = crit
        out[str(qid)[:64]] = spec
    return out


def _call(state: Any, questions: dict[str, dict[str, Any]], use_case: str) -> dict[str, Any]:
    from app.services import typesafe_client
    if not typesafe_client.is_configured():
        return {"error": "the decision model is not configured on this site"}
    out = typesafe_client.system_one(state, questions, use_case=use_case, timeout_s=20.0)
    if not out:
        return {"error": "the decision model did not answer"}
    usage = out.get("usage") or {}
    tokens = int(usage.get("input_tokens") or 0)
    return {"model": out.get("model"), "answers": out.get("answers") or {},
            "usage": {"input_tokens": tokens, "cost_usd": round(tokens * typesafe_client.USD_PER_INPUT_TOKEN, 6)}}


async def typed_judgment(ctx=None, state: Any = None, questions: Any = None) -> dict[str, Any]:
    if state is None or state == "":
        raise ToolError("state is required: the text or JSON object to judge")
    if isinstance(state, str) and len(state) > MAX_STATE_CHARS:
        state = state[:MAX_STATE_CHARS]
    qs = _validate_questions(questions)
    result = await asyncio.to_thread(_call, state, qs, "mcp_access.judgment_tools:typed_judgment")
    result["questions"] = list(qs.keys())
    return result


async def judge_articles(ctx=None, article_uris: Any = None, question: str | None = None,
                         yes_means: str | None = None, no_means: str | None = None,
                         context: str | None = None) -> dict[str, Any]:
    if not isinstance(article_uris, list) or not article_uris:
        raise ToolError("article_uris must be a non-empty list of URIs from this site")
    if not question or not str(question).strip():
        raise ToolError("question is required: a yes/no question about each article")
    uris = [str(u) for u in article_uris if u][:MAX_ARTICLES]
    from app.database import get_database_instance
    from app.services.article_visibility import is_readable
    rows = await asyncio.to_thread(lambda: get_database_instance().facade.get_articles_by_uris(uris) or [])
    by_uri = {str(r.get("uri")): r for r in rows if isinstance(r, dict) and r.get("uri")}
    q: dict[str, dict[str, Any]] = {"answer": {"type": "noul", "instructions": f"About `article`: {str(question).strip()}"}}
    if yes_means or no_means:
        q["answer"]["criteria"] = {"true": str(yes_means or "yes"), "false": str(no_means or "no")}
    ctx_text = (str(context).strip()[:2000] if context else None)

    def _one(uri: str) -> dict[str, Any]:
        row = by_uri.get(uri)
        if row is None:
            return {"uri": uri, "error": "not found on this site"}
        if not is_readable(row):
            return {"uri": uri, "error": "below the site's relevance floor"}
        state: dict[str, Any] = {"article": {"title": row.get("title") or "", "summary": (row.get("summary") or "")[:2500],
                                             "source": row.get("news_source") or "", "published": str(row.get("publication_date") or "")[:10]}}
        if ctx_text:
            state["context"] = ctx_text
        r = _call(state, q, "mcp_access.judgment_tools:judge_articles")
        if r.get("error"):
            return {"uri": uri, "error": r["error"]}
        try:
            p = float(r["answers"]["answer"]["noul"])
        except (KeyError, TypeError, ValueError):
            return {"uri": uri, "error": "unreadable answer"}
        return {"uri": uri, "title": row.get("title"), "probability": p, "tokens": r["usage"]["input_tokens"]}

    loop = asyncio.get_running_loop()
    sem = asyncio.Semaphore(8)

    async def _run(uri: str) -> dict[str, Any]:
        async with sem:
            return await loop.run_in_executor(None, _one, uri)

    results = await asyncio.gather(*(_run(u) for u in uris))
    ok = [r for r in results if "probability" in r]
    from app.services import typesafe_client
    tokens = sum(r.get("tokens", 0) for r in ok)
    return {"question": str(question).strip(), "judged": len(ok), "skipped": len(results) - len(ok),
            "results": sorted(results, key=lambda r: -r.get("probability", -1.0)),
            "usage": {"input_tokens": tokens, "cost_usd": round(tokens * typesafe_client.USD_PER_INPUT_TOKEN, 6)}}


SPECS: dict[str, ToolSpec] = {
    "typed_judgment": ToolSpec(
        name="typed_judgment",
        description=(
            "Ask the site's decision model typed questions about a piece of text or a JSON state and get "
            "probabilities back instead of prose: a 'choice' returns a probability per option, a 'score' a "
            "position on ordered levels, a 'noul' the probability the answer is yes. Use it to classify, rank, "
            "verify or route without generating text. Each question needs 'type', 'instructions' and, for "
            "choice and score, 'criteria' (an object of options or an ordered list of levels). At most 24 "
            "questions per call; they are answered independently against the same state."
        ),
        properties={
            "state": {"type": ["object", "string"], "description": "The material to judge: a string, or a JSON object whose keys the instructions can reference in backticks (e.g. `article.title`)."},
            "questions": {"type": "object", "description": "Map of question id → {type: choice|score|noul, instructions: string, criteria: object|array}."},
        },
        required=("state", "questions"),
        timeout=30.0,
    ),
    "judge_articles": ToolSpec(
        name="judge_articles",
        description=(
            "Ask one yes/no question about each of up to 40 of this site's articles (by URI, from any other "
            "tool's results) and get a probability per article from the decision model, sorted highest first. "
            "Use it to rerank, filter or verify articles another tool returned, e.g. 'Is this article about a "
            "funding round for a SOC automation vendor?'. Optional yes_means / no_means sharpen the criteria; "
            "optional context supplies a definition the question relies on."
        ),
        properties={
            "article_uris": {"type": "array", "items": {"type": "string"}, "description": "Article URIs from this site (max 40)."},
            "question": {"type": "string", "description": "A yes/no question asked about each article."},
            "yes_means": {"type": "string", "description": "What a yes means (optional)."},
            "no_means": {"type": "string", "description": "What a no means (optional)."},
            "context": {"type": "string", "description": "Optional definition or background the question relies on."},
        },
        required=("article_uris", "question"),
        timeout=60.0,
    ),
}

HANDLERS: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {
    "typed_judgment": typed_judgment,
    "judge_articles": judge_articles,
}
