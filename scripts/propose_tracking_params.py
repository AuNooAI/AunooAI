"""Propose tracking-parameter registry additions from stored URL variants.

The registry in ``app/collectors/url_identity.py`` says which query
parameters never identify a page. It is per publisher on purpose: a global
strip would merge two streamingmedia articles that differ only in
``ArticleID``. This script finds the publishers where the registry is still
missing something, so a person can review the evidence before anything is
added.

It reads articles from the last N days, groups them by host and path with
the query ignored, and inside each group keeps the members that share a
normalised title and a publication date within 48 hours. The query
parameter names that differ between such members are the proposal, with
counts and up to three example URL pairs per parameter. Parameters the
registry already strips are left out.

The script writes nothing to the database and never edits the registry
file. ``--apply-registry PATH`` only prints the JSON to add to that file.

Run from the tenant directory, so the ``.env`` there names the database:

    cd /home/orochford/tenants/wileytest.aunoo.ai
    .venv/bin/python scripts/propose_tracking_params.py --days 30 --json /tmp/proposals.json
    .venv/bin/python scripts/propose_tracking_params.py --topic "AI in Publishing"
    .venv/bin/python scripts/propose_tracking_params.py --apply-registry data/url_tracking_registry.json

``--db NAME`` overrides ``DB_NAME`` from the ``.env`` for a tenant whose
database has another name.

Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md, work package 30.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qsl, urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

#: Members of a host+path group count as the same story only when their
#: publication dates are this close. Two days covers a story updated
#: overnight; wider starts merging a story with its own follow-ups.
SAME_STORY_HOURS = 48
EXAMPLES_PER_PARAM = 3


def _host_and_path(url: str) -> Optional[Tuple[str, str]]:
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host, (parts.path or "/").rstrip("/") or "/"


def _param_names(url: str) -> frozenset:
    try:
        query = urlsplit(url).query
    except ValueError:
        return frozenset()
    return frozenset(n.lower() for n, _ in parse_qsl(query, keep_blank_values=True))


def _parse_when(value: Any) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s[:32])
    except ValueError:
        try:
            d = datetime.strptime(s[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def propose(rows: Iterable[Dict[str, Any]], *, hours: int = SAME_STORY_HOURS,
            examples: int = EXAMPLES_PER_PARAM) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Proposed parameters per host from article rows.

    Each row needs ``uri``, ``title`` and ``publication_date``. The result is
    ``{host: {param: {"count": n, "already_in_registry": bool, "examples":
    [[url_a, url_b], ...]}}}``. Pure: no database, no registry writes.
    Groups whose members do not share a title are not evidence of anything,
    which is what keeps streamingmedia's ``ArticleID`` out of the proposal.
    """
    from app.collectors.url_identity import load_registry
    from app.services.daily_briefing_ranking import normalize_title

    registry = load_registry()
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        uri = str(row.get("uri") or "").strip()
        hp = _host_and_path(uri)
        if not hp:
            continue
        groups[hp].append({
            "uri": uri,
            "title": normalize_title(row.get("title")),
            "when": _parse_when(row.get("publication_date")),
            "params": _param_names(uri),
        })

    out: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    window = timedelta(hours=hours)
    for (host, _path), members in groups.items():
        if len(members) < 2:
            continue
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                if not a["title"] or a["title"] != b["title"]:
                    continue
                if a["when"] and b["when"] and abs(a["when"] - b["when"]) > window:
                    continue
                if a["params"] == b["params"]:
                    continue
                for name in a["params"] ^ b["params"]:
                    entry = out[host].setdefault(name, {
                        "count": 0,
                        "already_in_registry": registry.is_tracking(host, name),
                        "examples": [],
                    })
                    entry["count"] += 1
                    if len(entry["examples"]) < examples:
                        entry["examples"].append([a["uri"], b["uri"]])
    return {h: dict(sorted(ps.items(), key=lambda kv: -kv[1]["count"])) for h, ps in out.items()}


def registry_snippet(proposals: Dict[str, Dict[str, Dict[str, Any]]]) -> Dict[str, Any]:
    """The ``hosts`` block to add to a registry file, new parameters only."""
    hosts = {}
    for host, params in proposals.items():
        names = sorted(n for n, p in params.items() if not p["already_in_registry"])
        if names:
            hosts[host] = names
    today = datetime.now(timezone.utc).strftime("%Y.%m.%d")
    return {"version": f"{today}-proposed", "hosts": hosts}


def _load_rows(db_name: Optional[str], days: int, topic: Optional[str]) -> List[Dict[str, Any]]:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
    if db_name:
        os.environ["DB_NAME"] = db_name
    from sqlalchemy import text
    from app.database import get_database_instance

    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    sql = ("SELECT uri, title, publication_date FROM articles "
           "WHERE uri LIKE 'http%' AND POSITION('?' IN uri) > 0 "
           "AND COALESCE(submission_date, publication_date) >= :since")
    params: Dict[str, Any] = {"since": since}
    if topic:
        sql += " AND topic = :topic"
        params["topic"] = topic
    # Rows without a query string cannot carry a tracking parameter, but
    # they are the other half of a pair, so load them for the same hosts.
    rows = get_database_instance().facade._fetchall_with_rollback(text(sql), params, mappings=True)
    hosts = {(_host_and_path(r["uri"]) or ("", ""))[0] for r in rows}
    hosts.discard("")
    out = [dict(r) for r in rows]
    if hosts:
        sql2 = ("SELECT uri, title, publication_date FROM articles "
                "WHERE uri LIKE 'http%' AND POSITION('?' IN uri) = 0 "
                "AND COALESCE(submission_date, publication_date) >= :since")
        params2: Dict[str, Any] = {"since": since}
        if topic:
            sql2 += " AND topic = :topic"
            params2["topic"] = topic
        for r in get_database_instance().facade._fetchall_with_rollback(text(sql2), params2, mappings=True):
            hp = _host_and_path(r["uri"])
            if hp and hp[0] in hosts:
                out.append(dict(r))
    return out


def _print_table(proposals: Dict[str, Dict[str, Dict[str, Any]]]) -> None:
    if not proposals:
        print("No URL-variant groups with a shared title found.")
        return
    print(f"{'host':40} {'parameter':24} {'pairs':>5}  registry  example")
    for host, params in sorted(proposals.items()):
        for name, p in params.items():
            flag = "yes" if p["already_in_registry"] else "no"
            ex = p["examples"][0] if p["examples"] else ["", ""]
            print(f"{host[:40]:40} {name[:24]:24} {p['count']:>5}  {flag:8}  {ex[0]}")
            if ex[1]:
                print(f"{'':40} {'':24} {'':>5}  {'':8}  {ex[1]}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", help="database name; overrides DB_NAME from .env")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--topic", help="limit to one topic")
    ap.add_argument("--json", help="write the proposals to this file")
    ap.add_argument("--apply-registry", metavar="PATH",
                    help="print the JSON to add to this registry file (never edits it)")
    args = ap.parse_args(argv)

    rows = _load_rows(args.db, args.days, args.topic)
    proposals = propose(rows)
    _print_table(proposals)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"days": args.days, "topic": args.topic, "rows": len(rows),
                       "proposals": proposals}, fh, indent=2)
        print(f"\nWrote {args.json}")
    if args.apply_registry:
        snippet = registry_snippet(proposals)
        print(f"\nTo apply, merge this into {args.apply_registry} under \"hosts\" and bump "
              f"\"version\" (this script does not edit the file):")
        print(json.dumps(snippet, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
