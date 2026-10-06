#!/usr/bin/env python3
"""Insert the brand-path hooks into a site's automated_ingest_service.py.

Thirteen versions of the ingest service ran across the monolith sites on
2026-10-06, so the brand path lives in app/services/brand_ingest_hooks.py and
this script adds the calls to it at lines every version shares. Each edit
must match exactly once, is marked "# brand-hook" and is skipped when already
present, so the script can run again safely. Nothing is written unless every
required edit matched.

    python3 scripts/brand_rollout/transform_ingest.py <site tree> [--apply]

Required edits (all sites): the hooks import, pre_decide at the top of
_process_single_article_async, relevance_override in
_score_article_relevance_async, analyze_or_skip, quality_or_skip,
save_enriched. Optional (only where the site has the code): the no-text guard
and the rejected-candidate ledger guard yield to an admitted brand item.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

MARK = "# brand-hook"
REL = "app/services/automated_ingest_service.py"


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


EDITS = [
    # (name, required, kind, anchor, payload)
    ("import", True, "replace_line", "import asyncio",
     "import asyncio\nfrom app.services import brand_ingest_hooks as _bhooks  " + MARK),
    ("pre_decide", True, "after_line", 'self.logger.debug(f"🔄 Processing article: {article_title}")',
     ["# brand-hook: settle decided rows, decide undecided ones once (BRAND_RELATION_DECISIONS)",
      '_bh = await _bhooks.pre_decide(self, article, topic, keywords, locals().get("ledger_ctx"))',
      'if _bh is not None and _bh.get("action") == "return":',
      '    return _bh["result"]']),
    ("relevance_override", True, "after_line", '"""Async version of relevance scoring"""',
     ["_bh_ov = _bhooks.relevance_override(self, article_data, topic)  " + MARK,
      "if _bh_ov is not None:",
      "    return _bh_ov"]),
    ("analyze_or_skip", True, "replace_text", "self._analyze_article_content_async(enriched_article, topic),",
     "_bhooks.analyze_or_skip(self, enriched_article, topic),  " + MARK),
    ("quality_or_skip", True, "replace_text",
     "quality_result = await self._quality_check_article_async(enriched_article)",
     "quality_result = await _bhooks.quality_or_skip(self, enriched_article)  " + MARK),
    ("save_enriched", True, "replace_text",
     "success = await self.async_db.update_article_with_enrichment(enriched_article)",
     "success = await _bhooks.save_enriched(self, enriched_article, topic)  " + MARK),
    ("no_text_guard", False, "replace_text",
     "if not (article.get('summary') or article.get('content')) or not article.get('title'):",
     "if not article.get('_brand_decision') and (not (article.get('summary') or article.get('content')) or not article.get('title')):  " + MARK),
    ("ledger_guard", False, "replace_text", "if ledger_hit is not None:",
     "if ledger_hit is not None and not article.get('_brand_decision'):  " + MARK),
]


def transform(src: str):
    """(new source, [(edit, status)], ok). All edits or none: a file that
    already imports the hooks module was transformed before and is left as is."""
    if "brand_ingest_hooks as _bhooks" in src:
        return src, [(name, "present") for name, *_ in EDITS], True
    lines = src.split("\n")
    report, ok = [], True
    for name, required, kind, anchor, payload in EDITS:
        if kind == "replace_line":
            hits = [i for i, l in enumerate(lines) if l.strip() == anchor and not l.startswith(" ")]
        else:
            hits = [i for i, l in enumerate(lines) if anchor in l]
        if len(hits) != 1:
            if required:
                ok = False
                report.append((name, f"REQUIRED anchor found {len(hits)} times"))
            else:
                report.append((name, f"not in this version ({len(hits)} matches), skipped"))
            continue
        i = hits[0]
        if kind == "replace_line":
            lines[i] = payload
        elif kind == "replace_text":
            lines[i] = lines[i].replace(anchor, payload)
        else:
            ind = _indent(lines[i])
            lines[i + 1:i + 1] = [ind + x for x in payload]
        report.append((name, "applied"))
    return "\n".join(lines), report, ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tree")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--source", help="read from this file instead of the tree's own (for canonical rebuilds)")
    args = ap.parse_args()
    path = os.path.join(args.tree, REL)
    src = open(args.source or path, encoding="utf-8").read()
    out, report, ok = transform(src)
    for name, status in report:
        print(f"  {name:20} {status}")
    if not ok:
        print(f"{path}: a required anchor did not match; nothing written.")
        return 2
    if args.apply:
        open(path, "w", encoding="utf-8").write(out)
        print(f"{path}: written.")
    else:
        print(f"{path}: dry run, all required edits match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
