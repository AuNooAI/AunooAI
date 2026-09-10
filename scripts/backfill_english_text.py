"""One-off: English text for existing non-English summaries and social posts.

Companion to backfill_english_titles.py. Walks the articles table, keeps rows
whose ``summary`` does not look English (app/utils/title_translation.
looks_english_text), asks the cheap translation model in batches, and writes
the English text to ``summary`` with the collected text moved to
``original_summary``. A social post whose title is the head of its body gets
its title from the same translation when the title is still untranslated.
Rows that already carry an original_summary are skipped, so the script is
safe to re-run.

Run from the tenant tree as the service user:

    cd /home/orochford/tenants/<site>.aunoo.ai
    sudo -u orochford env PYTHONPATH=$PWD .venv/bin/python scripts/backfill_english_text.py [--days 30] [--dry-run] [--limit N]
"""
import argparse
import json
import logging
import re
import sys
import time

from dotenv import load_dotenv
load_dotenv(".env")
logging.basicConfig(level=logging.WARNING)

from sqlalchemy import text  # noqa: E402
from app.database import get_database_instance  # noqa: E402
from app.utils.title_translation import (  # noqa: E402
    looks_english_text, looks_english, same_headline, _default_model, _strip_wrapping_quotes,
    _headline_from_text, TEXT_TRANSLATE_LIMIT, SOCIAL_TITLE_LIMIT,
)

BATCH = 8  # posts are longer than headlines; keep well under the model's reply cap


def translate_batch(model, texts):
    numbered = "\n\n".join(f"### {i + 1}\n{t}" for i, t in enumerate(texts))
    messages = [
        {"role": "system", "content": (
            "You translate social media posts and news text into English. For each numbered text "
            "reply with its English translation. Keep @handles, #hashtags, URLs, names, brands and "
            "numbers exactly as they are. If a text is already English, return it exactly as given. "
            "Respond ONLY with a JSON object mapping the number (as a string) to the English text, "
            "e.g. {\"1\": \"...\", \"2\": \"...\"}."
        )},
        {"role": "user", "content": numbered},
    ]
    raw = model.generate_response(messages)
    raw = raw if isinstance(raw, str) else str(raw or "")
    start = raw.find("{")
    if start < 0:
        return {}
    end = raw.rfind("}")
    body = raw[start:end + 1] if end > start else raw[start:]
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        try:
            import json_repair
            parsed = json_repair.loads(body)
        except Exception:
            return {}
    if not isinstance(parsed, dict):
        return {}
    out = {}
    for k, v in parsed.items():
        try:
            idx = int(str(k).strip()) - 1
        except ValueError:
            continue
        if 0 <= idx < len(texts) and isinstance(v, str):
            out[idx] = _strip_wrapping_quotes(v)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30, help="only articles submitted in the last N days (0 = all)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = get_database_instance()
    where = "original_summary IS NULL AND summary IS NOT NULL AND summary <> ''"
    params = {}
    if args.days:
        where += " AND submission_date::timestamptz > now() - (:days || ' days')::interval"
        params["days"] = str(args.days)
    rows = db.facade._fetchall_with_rollback(
        text(f"SELECT uri, title, original_title, summary FROM articles WHERE {where} ORDER BY submission_date DESC"),
        params, mappings=True)
    todo = [dict(r) for r in rows if not looks_english_text(r["summary"])]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(rows)} candidate rows, {len(todo)} summaries look non-English", flush=True)
    if args.dry_run:
        for r in todo[:20]:
            print("  ", (r["summary"] or "")[:90].replace("\n", " "))
        return

    model = _default_model()
    changed = unchanged = failed = titles = 0
    t0 = time.time()
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        sources = [(r["summary"].strip()[:TEXT_TRANSLATE_LIMIT]) for r in chunk]
        try:
            result = translate_batch(model, sources)
        except Exception as e:
            print(f"batch {i // BATCH}: model error {e}", flush=True)
            failed += len(chunk)
            continue
        for j, r in enumerate(chunk):
            original = r["summary"].strip()
            english = result.get(j)
            if not english or len(english) > max(1500, 4 * len(sources[j])):
                failed += 1
                continue
            if same_headline(english, original):
                unchanged += 1
                continue
            if len(original) > TEXT_TRANSLATE_LIMIT:
                english += " …"
            sets = {"s": english, "os": original, "u": r["uri"]}
            sql = "UPDATE articles SET summary = :s, original_summary = :os"
            title = (r["title"] or "").strip()
            prefix, head = "", title
            m = re.match(r"^(@\S+:\s*)(.*)$", title, flags=re.S)
            if m and original.startswith(m.group(2).rstrip(" ….")):
                prefix, head = m.group(1), m.group(2)
            if head and not r["original_title"] and not looks_english(head) \
                    and original.startswith(head.rstrip(" ….")):
                shown = english if same_headline(head, original) else \
                    _headline_from_text(english, max(SOCIAL_TITLE_LIMIT, len(head)))
                sql += ", title = :t, original_title = :ot"
                sets.update({"t": prefix + shown, "ot": title})
                titles += 1
            db.facade._execute_with_rollback(text(sql + " WHERE uri = :u AND original_summary IS NULL"), sets)
            changed += 1
        db.facade.connection.commit()
        print(f"[{time.strftime('%H:%M:%S')}] {min(i + BATCH, len(todo))}/{len(todo)} changed={changed} "
              f"(titles {titles}) unchanged={unchanged} failed={failed}", flush=True)
    print(f"DONE changed={changed} titles={titles} unchanged={unchanged} failed={failed} in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    sys.exit(main())
