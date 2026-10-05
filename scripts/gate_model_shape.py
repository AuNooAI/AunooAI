"""Before/after gate for a model-name switch on the report pipelines.

Runs the four pipelines whose call settings depend on the model name (daily
report synthesis, briefing compose, topic report, Auspex) with one model
name, records what each litellm call actually sent (budget, temperature)
and what came back (tokens, finish reason), plus a few structural facts
about the output. Run it once per arm and compare the two JSON files:

    .venv/bin/python scripts/gate_model_shape.py --model gpt-5.4 --runs 2
    .venv/bin/python scripts/gate_model_shape.py --model claude-sonnet-4-5 --runs 2

Nothing customer-visible is written: the daily report is generated but not
saved, the topic report's save calls are captured instead of run, the
compose briefing is deleted afterwards, and the Auspex chat session is
deleted afterwards. The humanizer and the Jev shadow are switched off so
they do not blur the comparison.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")
os.environ["TYPESAFE_SHADOW_BRIEFING"] = "false"

import litellm  # noqa: E402

CALLS: list = []
_orig_acompletion, _orig_completion = litellm.acompletion, litellm.completion


def _shape(kw):
    return {k: kw.get(k) for k in ("max_tokens", "max_completion_tokens", "temperature", "reasoning_effort")
            if k in kw} | {"json": "response_format" in kw}


def _record(kw, resp, started, err=None):
    row = {"model": kw.get("model"), "sent": _shape(kw), "ms": int((time.time() - started) * 1000)}
    if err is not None:
        row["error"] = repr(err)[:200]
    else:
        u = getattr(resp, "usage", None)
        row["prompt_tokens"] = getattr(u, "prompt_tokens", None)
        row["completion_tokens"] = getattr(u, "completion_tokens", None)
        try:
            row["finish_reason"] = resp.choices[0].finish_reason
        except Exception:  # noqa: BLE001 - streaming responses have no choices yet
            row["finish_reason"] = None
    CALLS.append(row)


async def _rec_acompletion(*a, **kw):
    t = time.time()
    try:
        r = await _orig_acompletion(*a, **kw)
    except Exception as e:  # noqa: BLE001
        _record(kw, None, t, e)
        raise
    _record(kw, r, t)
    return r


def _rec_completion(*a, **kw):
    t = time.time()
    try:
        r = _orig_completion(*a, **kw)
    except Exception as e:  # noqa: BLE001
        _record(kw, None, t, e)
        raise
    _record(kw, r, t)
    return r


litellm.acompletion, litellm.completion = _rec_acompletion, _rec_completion


def _silence_shadows():
    """The Jev shadow jobs write comparison rows next to a run; keep the gate
    from leaving any behind."""
    import importlib
    for name in ("briefing_candidate_shadow", "briefing_claim_shadow", "auspex_route_shadow",
                 "auspex_compaction_shadow", "extraction_check_shadow", "signal_referee_shadow",
                 "issue_merge_shadow"):
        try:
            mod = importlib.import_module(f"app.services.{name}")
        except Exception:  # noqa: BLE001 - a site without that shadow
            continue
        if hasattr(mod, "schedule"):
            mod.schedule = lambda *a, **k: False


def _take(label):
    """Calls recorded since the last take, tagged with the pipeline."""
    rows, CALLS[:] = list(CALLS), []
    for r in rows:
        r["pipeline"] = label
    return rows


async def daily_report(model, briefing_id):
    from app.database import get_database_instance
    from app.services.daily_report_service import get_daily_report_service
    db = get_database_instance()
    b = db.facade.get_desk_briefing_by_id(briefing_id, "admin")
    articles, incidents = b.get("articles") or [], b.get("incidents") or []
    last, events = {}, 0
    async for upd in get_daily_report_service().generate_synthesis(
            b.get("name") or "gate", articles, incidents, model=model):
        events += 1
        if isinstance(upd, dict):
            last = upd if upd.get("synthesis") or upd.get("type") in ("complete", "done") else {**last, **{k: v for k, v in upd.items() if k in ("synthesis", "themes", "priority_actions", "review")}}
    syn = last.get("synthesis") or ""
    review = last.get("review") or {}
    summ = review.get("summary") if isinstance(review, dict) else {}
    return {"events": events, "articles_in": len(articles), "synthesis_chars": len(syn),
            "themes": len(last.get("themes") or []), "priority_actions": len(last.get("priority_actions") or []),
            "review_errors": (summ or {}).get("errors"), "review_warnings": (summ or {}).get("warnings"),
            "sample": syn[:700]}


async def compose(model, topics):
    from app.database import get_database_instance
    from app.services import briefing_candidate_shadow, daily_briefing_compose_service as svc
    briefing_candidate_shadow.schedule = lambda *a, **k: False
    db = get_database_instance()
    bid, events, complete = None, [], {}
    try:
        async for evt in svc.compose_daily_briefing_stream(
                db, "admin", topics, model=model, honor_model=True, run_detection=False):
            events.append(evt)
            if evt.get("briefing_id"):
                bid = evt["briefing_id"]
            if evt.get("type") in ("complete", "error") or evt.get("stage") in ("complete", "error"):
                complete = evt
    finally:
        if bid:
            db.facade.delete_desk_briefing(bid, "admin")
    picked = None
    if bid:
        try:
            picked = None  # the briefing is gone; counts come from the events
        except Exception:  # noqa: BLE001
            pass
    stages = [e.get("stage") or e.get("type") for e in events]
    return {"events": len(events), "briefing_id": bid, "deleted": bool(bid), "stages": stages[-6:],
            "final": {k: v for k, v in complete.items() if k in ("type", "stage", "status", "message", "articles", "count", "selected")},
            "picked": picked}


async def topic_report(model, topic):
    from app.database import get_database_instance
    from app.services import topic_report_service as trs
    db = get_database_instance()
    captured = {}

    def _cap_run(**kw):
        captured["run"] = kw
        return True

    def _cap_exec(*a, **kw):
        captured["exec"] = {"args": [str(x)[:80] for x in a], "kw": {k: (v if k != "cards" else len(v)) for k, v in kw.items()}}
        return True

    async def _no_humanize(raw):
        return None

    db.facade.save_future_horizons_analysis = _cap_run
    db.facade.save_horizons_executive_summary = _cap_exec
    trs._humanize_report_prose = _no_humanize
    run_id = await trs._rerun_future_horizons_for_topic(topic, model)
    raw = (captured.get("run") or {}).get("raw_output") or {}
    scenarios = raw.get("scenarios") or []
    exec_summary = await trs.generate_executive_summary_for_run(run_id, topic, scenarios, model)
    text_all = json.dumps(raw)
    return {"run_id": run_id, "scenarios": len(scenarios), "raw_keys": sorted(raw.keys())[:12],
            "raw_chars": len(text_all), "disruption": len(raw.get("disruption_scenarios") or []),
            "exec_cards": len((exec_summary or {}).get("summaries") or []) if isinstance(exec_summary, dict) else None,
            "exec_chars": len(json.dumps(exec_summary)) if exec_summary else 0,
            "sample": (scenarios[0].get("description") or scenarios[0].get("narrative") or json.dumps(scenarios[0]))[:700] if scenarios else ""}


async def auspex(model, topic):
    from app.database import get_database_instance
    from app.services.auspex_service import get_auspex_service
    from app.ai_models import extract_json_response
    db = get_database_instance()
    ax = get_auspex_service()
    rows = db.facade._execute_with_rollback(__import__("sqlalchemy").text(
        "SELECT title, summary FROM articles WHERE topic = :t AND topic_alignment_score >= 0.6 "
        "ORDER BY publication_date DESC LIMIT 40"), {"t": topic}).fetchall()
    corpus = "\n".join(f"- {r[0]}: {(r[1] or '')[:300]}" for r in rows)
    system = "You are an analyst. Reply with JSON only."
    user = ("From these recent items, return JSON {\"themes\": [{\"name\", \"summary\", \"evidence\": [titles]}], "
            "\"outlook\": \"...\"} with 4 to 6 themes.\n\n" + corpus)
    content = await ax.generate_structured_analysis(system, user, model=model, temperature=0.7, max_tokens=3000)
    try:
        parsed = extract_json_response(content); ok = True
    except Exception:  # noqa: BLE001
        parsed, ok = {}, False
    chat_id = await ax.create_chat_session(topic=topic, user_id="gate", title="gate")
    chunks = []
    try:
        async for c in ax.chat_with_tools(chat_id, "What are the three most important developments this week, and what do they mean?", model=model, limit=30):
            chunks.append(c if isinstance(c, str) else json.dumps(c))
    finally:
        ax.delete_chat_session(chat_id)
    chat_text = "".join(chunks)
    return {"articles_in": len(rows), "json_ok": ok, "themes": len(parsed.get("themes") or []) if isinstance(parsed, dict) else None,
            "analysis_chars": len(content or ""), "chat_chars": len(chat_text), "chat_chunks": len(chunks),
            "sample": (content or "")[:500], "chat_sample": chat_text[-600:]}


PIPELINES = {"daily": daily_report, "compose": compose, "topic": topic_report, "auspex": auspex}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--pipelines", default="daily,compose,topic,auspex")
    ap.add_argument("--briefing-id", type=int, default=16)
    ap.add_argument("--topic", default="AI and Machine Learning")
    ap.add_argument("--compose-topics", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    from app.database import get_database_instance
    _silence_shadows()
    db = get_database_instance()
    compose_topics = [t for t in args.compose_topics.split("|") if t]
    if not compose_topics:
        row = db.facade._execute_with_rollback(__import__("sqlalchemy").text(
            "SELECT daily_briefing_topics FROM emerging_topics_settings WHERE id=1")).fetchone()
        compose_topics = (row[0] if row and row[0] else [])[:3] or [args.topic]
    results = []
    for run in range(1, args.runs + 1):
        for name in args.pipelines.split(","):
            fn = PIPELINES[name]
            started = time.time()
            try:
                if name == "daily":
                    out = await fn(args.model, args.briefing_id)
                elif name == "compose":
                    out = await fn(args.model, compose_topics)
                else:
                    out = await fn(args.model, args.topic)
                err = None
            except Exception as e:  # noqa: BLE001
                out, err = {}, repr(e)[:300]
            calls = _take(name)
            results.append({"model": args.model, "run": run, "pipeline": name, "seconds": round(time.time() - started, 1),
                            "error": err, "output": out, "calls": calls})
            sent = {json.dumps(c["sent"], sort_keys=True) for c in calls}
            fr = [c.get("finish_reason") for c in calls]
            ctoks = sum(c.get("completion_tokens") or 0 for c in calls)
            print(f"[{args.model} run {run}] {name:8} {round(time.time() - started):4}s calls={len(calls):2} "
                  f"out_tokens={ctoks:6} finish={sorted(set(map(str, fr)))} sent={sorted(sent)} "
                  f"{'ERROR ' + err if err else ''}", flush=True)
    out_path = Path(args.out or ROOT / "data" / f"gate_{args.model.replace('/', '_')}_{int(time.time())}.json")
    out_path.write_text(json.dumps(results, indent=1, default=str))
    print("wrote", out_path)


if __name__ == "__main__":
    asyncio.run(main())
