#!/usr/bin/env python3
"""Keyword monitor edits for the brand rollout, at lines every site version shares.

provenance  the provider query that returned an article travels into the
            pipeline as ``_collection_query`` (collection evidence for the brand
            decision). Three edits, applied together or not at all.
partial     a keyword check whose ingest pipeline had failures returns
            success=False, status "partial", with the count, instead of success.

Marked "# brand-hook"; a file that already has both is left alone.

    python3 scripts/brand_rollout/transform_keyword_monitor.py <tree> [--apply]
"""
import argparse
import os
import sys

MARK = "# brand-hook"
REL = "app/tasks/keyword_monitor.py"


def provenance(lines):
    if any("_collection_query" in l for l in lines):
        return lines, "present"
    sig = [i for i, l in enumerate(lines) if "async def auto_ingest_pipeline(" in l and "suppress_notifications: bool = False" in l]
    call = [i for i, l in enumerate(lines) if "articles, topic, topic_keywords, suppress_notifications=True" in l]
    smeta = [i for i, l in enumerate(lines) if "'social_meta': article.get('social_meta')," in l]
    kwt = any("keyword_text = keyword['keyword']" in l for l in lines)
    if not (len(sig) == len(call) == len(smeta) == 1 and kwt):
        return lines, f"skipped (sig {len(sig)}, call {len(call)}, social_meta {len(smeta)}, keyword_text {kwt})"
    lines = list(lines)
    lines[sig[0]] = lines[sig[0]].replace("suppress_notifications: bool = False",
                                          "suppress_notifications: bool = False, collection_query: Optional[str] = None", 1)
    lines[call[0]] = lines[call[0]].replace("suppress_notifications=True",
                                            "suppress_notifications=True, collection_query=keyword_text", 1)
    ind = lines[smeta[0]][: len(lines[smeta[0]]) - len(lines[smeta[0]].lstrip())]
    lines.insert(smeta[0] + 1, ind + "'_collection_query': collection_query,  " + MARK)
    return lines, "applied"


def partial(lines):
    if any('"status": "partial"' in l for l in lines):
        return lines, "present"
    init = [i for i, l in enumerate(lines) if l.strip() == "total_auto_ingest_errors = 0"]
    fail = [i for i, l in enumerate(lines) if 'logger.error(f"Auto-ingest pipeline failed: {e}", exc_info=True)' in l]
    ret = [i for i, l in enumerate(lines) if '"keywords_processed": processed_keywords' in l]
    if not (len(init) == len(fail) == len(ret) == 1):
        return lines, f"skipped (init {len(init)}, fail {len(fail)}, return {len(ret)})"
    r = ret[0]
    start = r
    while start > 0 and lines[start].strip() != "return {":
        start -= 1
    if r - start > 4 or '"success": True' not in "".join(lines[start:r]):
        return lines, "skipped (return block not recognised)"
    lines = list(lines)
    ind = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
    block = [
        ind + "# Work that failed inside the ingest pipeline makes the check partial,  " + MARK,
        ind + "# not a success: the group shows the count and the articles stay queued.",
        ind + "if total_auto_ingest_errors:",
        ind + "    return {",
        ind + '        "success": False,',
        ind + '        "status": "partial",',
        ind + '        "error": (f"Partial: {total_auto_ingest_errors} article(s) failed in processing"',
        ind + '                  + (f", {auto_ingest_failed_batches} batch(es) failed outright" if auto_ingest_failed_batches else "")',
        ind + '                  + "; they stay queued for retry."),',
        ind + '        "new_articles": new_articles_count,',
        ind + '        "keywords_processed": processed_keywords,',
        ind + '        "auto_ingest_errors": total_auto_ingest_errors,',
        ind + "    }",
    ]
    lines[start:start] = block
    f = fail[0]
    find = lines[f][: len(lines[f]) - len(lines[f].lstrip())]
    lines[f + 1:f + 1] = [find + "total_auto_ingest_errors += 1  " + MARK, find + "auto_ingest_failed_batches += 1"]
    i0 = init[0]
    iind = lines[i0][: len(lines[i0]) - len(lines[i0].lstrip())]
    lines.insert(i0 + 1, iind + "auto_ingest_failed_batches = 0  " + MARK)
    return lines, "applied"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tree"); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    path = os.path.join(a.tree, REL)
    src = open(path, encoding="utf-8").read()
    lines = src.split("\n")
    lines, p1 = provenance(lines)
    lines, p2 = partial(lines)
    new = "\n".join(lines)
    print(f"{path}: provenance {p1}; partial {p2}")
    if "Optional" not in src.split("class ")[0] and "collection_query: Optional" in new:
        print("  Optional is not imported in this file; nothing written")
        return 2
    compile(new, path, "exec")
    if a.apply and new != src:
        open(path, "w", encoding="utf-8").write(new)
        print("  written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
