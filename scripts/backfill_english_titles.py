"""One-off: give existing non-English article titles an English headline.

Walks the articles table, keeps rows whose title does not look English (see
app/utils/title_translation.looks_english), asks the cheap translation model
in batches of 40, and writes the English headline to ``title`` with the
collected one moved to ``original_title``. Rows that already carry an
original_title are skipped, so the script is safe to re-run.

Run from the tenant tree as the service user:

    cd /home/orochford/tenants/<site>.aunoo.ai
    sudo -u orochford env PYTHONPATH=$PWD .venv/bin/python scripts/backfill_english_titles.py [--days 30] [--dry-run] [--limit N]
"""
import argparse
import json
import logging
import sys
import time

from dotenv import load_dotenv
load_dotenv(".env")
logging.basicConfig(level=logging.WARNING)
logging.getLogger("app.utils.title_translation").setLevel(logging.INFO)

from sqlalchemy import text  # noqa: E402
from app.database import get_database_instance  # noqa: E402
from app.utils.title_translation import looks_english, same_headline, _default_model, _clean_model_title  # noqa: E402

BATCH = 40


def translate_batch(model, titles):
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles))
    messages = [
        {"role": "system", "content": (
            "You translate news headlines into English. For each numbered headline reply with the "
            "English headline. Keep names, brands and numbers as they are. If a headline is already "
            "English, return it exactly as given. Respond ONLY with a JSON object mapping the number "
            "(as a string) to the English headline, e.g. {\"1\": \"...\", \"2\": \"...\"}."
        )},
        {"role": "user", "content": numbered},
    ]
    raw = model.generate_response(messages)
    raw = raw if isinstance(raw, str) else str(raw or "")
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < 0:
        return {}
    try:
        parsed = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        try:
            import json_repair
            parsed = json_repair.loads(raw[start:end + 1])
        except Exception:
            return {}
    out = {}
    for k, v in (parsed or {}).items():
        try:
            idx = int(str(k).strip()) - 1
        except ValueError:
            continue
        if 0 <= idx < len(titles) and isinstance(v, str):
            out[idx] = _clean_model_title(v)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30, help="only articles submitted in the last N days (0 = all)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = get_database_instance()
    where = "original_title IS NULL AND title IS NOT NULL"
    params = {}
    if args.days:
        where += " AND submission_date::timestamptz > now() - (:days || ' days')::interval"
        params["days"] = str(args.days)
    rows = db.facade._fetchall_with_rollback(
        text(f"SELECT uri, title FROM articles WHERE {where} ORDER BY submission_date DESC"), params, mappings=True)
    todo = [(r["uri"], r["title"]) for r in rows if not looks_english(r["title"])]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(rows)} candidate rows, {len(todo)} titles look non-English", flush=True)
    if args.dry_run:
        for uri, t in todo[:20]:
            print("  ", t[:90])
        return

    model = _default_model()
    changed = unchanged = failed = 0
    t0 = time.time()
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        titles = [t for _, t in chunk]
        try:
            result = translate_batch(model, titles)
        except Exception as e:
            print(f"batch {i // BATCH}: model error {e}", flush=True)
            failed += len(chunk)
            continue
        for j, (uri, original) in enumerate(chunk):
            english = result.get(j)
            if not english or len(english) > max(300, 4 * len(original)):
                failed += 1
                continue
            if same_headline(english, original):
                unchanged += 1
                continue
            db.facade._execute_with_rollback(
                text("UPDATE articles SET title = :t, original_title = :o WHERE uri = :u AND original_title IS NULL"),
                {"t": english, "o": original, "u": uri})
            changed += 1
        db.facade.connection.commit()
        print(f"[{time.strftime('%H:%M:%S')}] {min(i + BATCH, len(todo))}/{len(todo)} changed={changed} unchanged={unchanged} failed={failed}", flush=True)
    print(f"DONE changed={changed} unchanged={unchanged} failed={failed} in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    sys.exit(main())
