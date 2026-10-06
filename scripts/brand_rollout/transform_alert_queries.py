#!/usr/bin/env python3
"""Add the shared earned rule to Brand Watcher's news sentiment alert and
digest queries in a site's file (brand_watcher_monitor.py, bw_digest_service.py).

After every line ``AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4``
inside an f-string query, adds ``AND {_bcov_earned()}`` with the same indent,
and defines _bcov_earned() before the file's first top-level function. A line
whose query is not an f-string is reported and left alone. A file that already
defines _bcov_earned is left as is.

    python3 scripts/brand_rollout/transform_alert_queries.py <tree> <relative file> [--apply]
"""
import argparse
import os
import re
import sys

CUT = "AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4"
HELPER = '''

def _bcov_earned() -> str:
    """The shared earned-news rule (brand_coverage): analysed, not social, not
    this brand's own publishing; TRUE with BRAND_RELATION_DECISIONS off."""
    from app.services.brand_coverage import alert_earned_sql
    return alert_earned_sql("a", "bac")

'''


def transform(src):
    if "def _bcov_earned" in src:
        return src, ["already present"], True
    lines = src.split("\n")
    report, out, added = [], [], 0
    for i, l in enumerate(lines):
        out.append(l)
        if l.strip() == CUT:
            j = i
            while j >= 0 and not re.search(r'text\(\s*f?"""', lines[j]):
                j -= 1
            if j < 0 or 'f"""' not in lines[j]:
                report.append(f"line {i + 1}: query is not an f-string, left alone")
                continue
            out.append(l[: len(l) - len(l.lstrip())] + "AND {_bcov_earned()}")
            added += 1
    if not added:
        return src, report + ["no cut-off lines found"], True
    text_ = "\n".join(out)
    m = re.search(r"^(def |async def |class )", text_, re.M)
    if not m:
        return src, report + ["no top-level function to place the helper before"], False
    text_ = text_[: m.start()] + HELPER.lstrip("\n") + "\n" + text_[m.start():]
    return text_, report + [f"{added} queries"], True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tree"); ap.add_argument("file"); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    path = os.path.join(a.tree, a.file)
    src = open(path, encoding="utf-8").read()
    new, report, ok = transform(src)
    print(f"{path}: " + "; ".join(report))
    if ok and a.apply and new != src:
        open(path, "w", encoding="utf-8").write(new)
        print("  written")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
