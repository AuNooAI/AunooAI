"""Daily quality report for one market page: lint, drift, digest.

Prints one JSON object. /home/orochford/bin/market_quality_daily.sh runs it for
every market site and emails the combined result.

- lint: the page as a reader sees it, checked for the faults our own code
  has produced — a company named twice, a summary that repeats its headline,
  one vendor spelled two ways, leftover brackets, "All 1".
- drift: today's review against the week before — how often Jev objects, how
  often the corrector changes a reading, how many items are held, how many
  news items have no checked headline, and whether the review ran at all.
- digest: what is new on the page since yesterday, with the items that were
  corrected, sit near the threshold, or are featured marked.

    .venv/bin/python scripts/market_quality_daily.py --market 2
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from sqlalchemy import text  # noqa: E402

from app.database import get_database_instance  # noqa: E402

#: A rate at least this many times the week's rate, on at least MIN_ITEMS
#: items, is drift.
DRIFT_FACTOR = 2.0
MIN_ITEMS = 8
NEAR_THRESHOLD = 0.9


def _page_html(market_id: int, section: str = "") -> str:
    import time

    from app.routes.market_monitor_routes import _market_report_token

    port = os.getenv("PORT", "10004")
    exp = int(time.time()) + 3600
    url = (f"http://127.0.0.1:{port}/api/market-monitor/markets/{market_id}/"
           f"report.html?public=1&exp={exp}&token={_market_report_token(market_id, exp)}"
           f"{section}")
    req = urllib.request.Request(url, headers={"X-Forwarded-Proto": "https"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", "replace")


#: Where the words of an item on the page may come from (market_assessment.
#: shown_on_page): the checked loop, an outside publisher's own title, our
#: own counts, or a word-for-word quote. "analysis" is our bylined monthly
#: piece: prose around cited facts, the one text not checked by Jev.
_ALLOWED_SOURCES = {"checked", "publisher", "data", "quote", "analysis"}


def provenance(market_id: int) -> list:
    """Every item a reader sees must say where its words came from."""
    problems = []
    for section in ("", "&section=moves", "&section=launches", "&section=cases",
                    "&section=social"):
        try:
            raw = _page_html(market_id, section)
        except Exception:  # noqa: BLE001 — the lint reports pages that fail
            continue
        for m in re.finditer(r'<(article class="n-story[^"]*"|div class="n-social")([^>]*)>',
                             raw):
            src = re.search(r'data-src="([^"]*)"', m.group(0))
            value = src.group(1) if src else ""
            if value not in _ALLOWED_SOURCES:
                head = re.search(r"<h[23][^>]*>(.*?)</h[23]>", raw[m.end():m.end() + 2000], re.S)
                label = html.unescape(re.sub(r"<[^>]+>", "", head.group(1))).strip() if head else "?"
                problems.append(f"item with {'no source' if not value else value + ' text'}"
                                f"{' on ' + section.split('=')[-1] if section else ''}: {label[:80]}")
    return sorted(set(problems))


def _page_text(market_id: int, section: str = "") -> str:
    import time

    from app.routes.market_monitor_routes import _market_report_token

    # A signed link, as the app's Share button makes: most markets are not
    # public, and the signed view is the shared view a reader gets.
    port = os.getenv("PORT", "10004")
    exp = int(time.time()) + 3600
    url = (f"http://127.0.0.1:{port}/api/market-monitor/markets/{market_id}/"
           f"report.html?public=1&exp={exp}&token={_market_report_token(market_id, exp)}"
           f"{section}")
    req = urllib.request.Request(url, headers={"X-Forwarded-Proto": "https"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", "replace")
    raw = re.sub(r"<style.*?</style>|<script.*?</script>", " ", raw, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))


def _squash(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def lint(conn, market_id: int, devs) -> list:
    problems = []
    vendors = [r[0] for r in conn.execute(text("""
        SELECT b.display_name FROM bw_market_brands mb JOIN bw_brands b ON b.id = mb.brand_id
         WHERE mb.market_id = :m"""), {"m": market_id}).fetchall()]
    page, ours = "", ""
    for section in ("", "&section=moves", "&section=launches", "&section=cases",
                    "&section=voices", "&section=social"):
        try:
            got = _page_text(market_id, section)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"page{section or ' (front)'} did not render: {exc}")
            continue
        page += " " + got
        # Voices and Social quote other people's posts; how they spell a
        # vendor is not ours to fix.
        if section not in ("&section=voices", "&section=social"):
            ours += " " + got
    for d in devs:
        head = d.get("headline") or ""
        # "AquilaI: Aquila I partners with…"
        m = re.match(r"^([^:]{2,40}):\s+(.*)$", head)
        if m and _squash(m.group(2)).startswith(_squash(m.group(1))[:6]):
            problems.append(f"company named twice: {head[:90]}")
        # What the page would show under the headline, by the page's own rule.
        from app.services.market_report_html import _summary_unless_duplicate
        shown = (_summary_unless_duplicate(d) or "").lower()
        hw = set(re.findall(r"[a-z0-9]+", head.lower()))
        sw = set(re.findall(r"[a-z0-9]+", shown))
        if sw and len(hw & sw) / len(sw) >= 0.75:
            problems.append(f"summary repeats headline: {head[:90]}")
    for name in vendors:
        variants = {m.group(0) for m in re.finditer(
            # Not a domain name: "panaya.com" is how the web spells it.
            rf"(?<![\w.]){re.escape(name)}(?![\w]|\.[a-z])", ours, re.I)}
        variants.discard(name)
        odd = {v for v in variants if v.lower() == name.lower() and v != name
               and not v.isupper() and not v.islower() or v in (name.lower(),)}
        if odd:
            problems.append(f"vendor spelled more than one way: {name} / {', '.join(sorted(odd))}")
    for pattern, label in ((r"All 1 →", '"All 1" link'),
                           (r"\((?:A|An|was) [^)]{2,40} company\)", "operator note in brackets"),
                           # Where a value belongs, not in a sentence ("None
                           # sell fewer missed detections").
                           (r"[:·]\s*(None|null|undefined|NaN)\b", "empty value printed"),
                           (r"\{[a-z_]+\}", "template placeholder printed")):
        for m in re.finditer(pattern, page):
            problems.append(f"{label}: …{page[max(0, m.start() - 40):m.end() + 20]}…")
            break
    return sorted(set(problems))


def _rates(conn, market_id: int, since, until) -> dict:
    row = conn.execute(text("""
        SELECT count(*) FILTER (WHERE review_verdict IS NOT NULL) AS reviewed,
               count(*) FILTER (WHERE review_verdict = 'signal') AS signals,
               count(*) FILTER (WHERE review_check ? 'kind') AS checked,
               count(*) FILTER (WHERE jsonb_array_length(COALESCE(review_check->'objections', '[]'::jsonb)) > 0) AS objected,
               count(*) FILTER (WHERE (review_check->>'corrected')::boolean) AS corrected,
               count(*) FILTER (WHERE review_check ? 'held') AS held,
               count(*) FILTER (WHERE review_verdict = 'signal' AND review_headline IS NULL) AS no_headline
          FROM bw_market_articles
         WHERE market_id = :m AND reviewed_at >= :a AND reviewed_at < :b
    """), {"m": market_id, "a": since, "b": until}).mappings().first()
    return dict(row)


def drift(conn, market_id: int) -> tuple:
    now = datetime.now(timezone.utc)
    today = _rates(conn, market_id, now - timedelta(days=1), now)
    week = _rates(conn, market_id, now - timedelta(days=8), now - timedelta(days=1))
    problems = []
    # A comparison needs a week of checked reviews behind it.
    comparable = week["checked"] >= MIN_ITEMS
    if not today["reviewed"]:
        problems.append("the review did not read any post in the last 24 hours")
    if today["signals"] and not today["checked"]:
        problems.append(f"{today['signals']} news items reviewed in 24 hours, none checked by Jev")
    for key, label in (("objected", "Jev objections"), ("corrected", "corrections"),
                       ("held", "held items"), ("no_headline", "news items without a checked headline")):
        base = (week[key] / week["signals"]) if week["signals"] else 0.0
        rate = (today[key] / today["signals"]) if today["signals"] else 0.0
        if comparable and today["signals"] >= MIN_ITEMS and rate > max(0.05, DRIFT_FACTOR * base):
            problems.append(f"{label}: {today[key]} of {today['signals']} today "
                            f"({rate:.0%}) against {base:.0%} over the week before")
    return problems, {"last_24h": today, "week_before": week}


def digest(devs, lead_uri: str) -> list:
    since = (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat()
    out = []
    for d in devs:
        if d.get("event_type") in ("significant_hiring", "headcount_change"):
            continue
        if str(d.get("date") or "") < since:
            continue
        marks = []
        conf = d.get("review_confidence")
        if conf is not None and conf < NEAR_THRESHOLD:
            marks.append(f"near threshold {conf:.2f}")
        if d.get("corrected"):
            marks.append("corrected")
        if any(e.get("uri") == lead_uri for e in d.get("evidence") or []):
            marks.append("FEATURED")
        vendor = ", ".join(v.get("vendor") or "" for v in d.get("vendors") or [])
        out.append(f"{d.get('date')} · {d.get('event_type_label')} · {vendor}: "
                   f"{d.get('headline')}" + (f"  [{'; '.join(marks)}]" if marks else ""))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", type=int, required=True)
    args = ap.parse_args()
    from app.services import market_assessment as ma

    with get_database_instance()._temp_get_connection() as conn:
        name = conn.execute(text("SELECT name FROM bw_markets WHERE id = :m"),
                            {"m": args.market}).scalar()
        result = ma.material_developments(conn, args.market, 30)
        devs = result["developments"]
        corrected = {r[0] for r in conn.execute(text("""
            SELECT article_uri FROM bw_market_articles
             WHERE market_id = :m AND (review_check->>'corrected')::boolean"""),
            {"m": args.market}).fetchall()}
        for d in devs:
            d["corrected"] = any(e.get("uri") in corrected for e in d.get("evidence") or [])
        lint_problems = lint(conn, args.market, devs) + provenance(args.market)
        held_out = [f"{d.get('event_type_label')} · "
                    f"{', '.join(v.get('vendor') or '' for v in d.get('vendors') or [])}: "
                    f"{d.get('headline')} (confidence {d.get('review_confidence')})"
                    for d in result.get("held_out") or []]
        drift_problems, rates = drift(conn, args.market)
    lead_uri = ""
    try:
        front = _page_text(args.market)
        m = re.search(r"Featured development · \S+ (.{20,120}?) ", front)
        lead_text = m.group(1) if m else ""
        for d in devs:
            if lead_text and (d.get("headline") or "").startswith(lead_text[:40]):
                lead_uri = ((d.get("evidence") or [{}])[0]).get("uri") or ""
    except Exception:  # noqa: BLE001
        pass
    print(json.dumps({"market": name, "market_id": args.market,
                      "lint": lint_problems, "drift": drift_problems, "rates": rates,
                      "digest": digest(devs, lead_uri), "held_out": held_out},
                     default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
