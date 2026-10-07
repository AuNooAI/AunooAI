#!/usr/bin/env python3
"""Give a site's live analysis prompts the fixed output block.

docs/pipelines/08_INGEST_FIX_SPEC.md, WP6c. The analysis prompts end in a
fixed block after ``REQUIRED OUTPUT FORMAT:`` (app/analyzers/analysis_schema.py)
and PromptManager refuses edits that change it. A live prompt saved before
7 Oct 2026 ends in a free-text ``OUTPUT FORMAT`` section instead, so the
prompt screen could no longer save it. This saves one new version per
prompt that keeps the site's own instructions and replaces only that
section. ``content_analysis_auto`` is seeded from the bundled default when
the site has none.

Run from the tenant directory, before restarting onto the new code:
    .venv/bin/python scripts/migrate_analysis_prompt_schema.py --dry-run
    .venv/bin/python scripts/migrate_analysis_prompt_schema.py
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.analyzers import analysis_schema  # noqa: E402
from app.analyzers.prompt_manager import PromptManager  # noqa: E402
from app.analyzers.prompt_templates import PromptTemplates  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    store = os.path.join(root, "data", "prompts")
    if args.dry_run:
        # Read the files directly: constructing PromptManager creates folders.
        import json
        for prompt_type in analysis_schema.SCHEMA_PROMPT_TYPES:
            path = os.path.join(store, prompt_type, "current.json")
            cur = json.load(open(path)) if os.path.exists(path) else {}
            if not (cur.get("user_prompt") or "").strip():
                print(f"{prompt_type}: none on this site; would seed the bundled default")
                continue
            problem = analysis_schema.schema_problem(prompt_type, cur["user_prompt"])
            print(f"{prompt_type}: " + (f"{problem}; would save a migrated version" if problem
                                        else f"block is current (version {cur.get('version')})"))
        return 0
    pm = PromptManager(storage_dir=store)
    pm.initialize_defaults({analysis_schema.AUTO: PromptTemplates.DEFAULT_TEMPLATES[analysis_schema.AUTO]})
    for prompt_type in analysis_schema.SCHEMA_PROMPT_TYPES:
        cur = pm.get_current_version(prompt_type)
        problem = analysis_schema.schema_problem(prompt_type, cur.get("user_prompt") or "")
        if not problem:
            print(f"{prompt_type}: block is current (version {cur.get('version')})")
            continue
        print(f"{prompt_type}: {problem}")
        saved = pm.migrate_output_block(prompt_type)
        print(f"{prompt_type}: saved version {saved['version']} ({saved['hash']}), "
              f"schema {saved['schema_migration']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
