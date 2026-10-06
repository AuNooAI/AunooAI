#!/usr/bin/env python3
"""Add reviewed profile entries to a site's bw_brands rows.

Reads eval/brand_relevance/profiles/<site>.json and, for each brand named
there by display name, adds the listed brand_keywords, product_keywords and
config list entries (original_names, aliases, ambiguous_aliases,
exclude_context, mention_context, owned_domains, non_press_domains,
news_keyword_excludes). Only adds: an entry already present (compared after
normalisation) is skipped and nothing is removed or replaced, so explicit
tenant rules are never overwritten. Default is a dry run; --apply writes.

    cd /home/orochford/tenants/sunstar.aunoo.ai
    .venv/bin/python scripts/brand_profile_apply.py eval/brand_relevance/profiles/sunstar.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.services.brand_profile import norm  # noqa: E402

LIST_CONFIG_KEYS = ("original_names", "aliases", "products", "collection_skip", "ambiguous_aliases", "exclude_context",
                    "mention_context", "owned_domains", "non_press_domains", "news_keyword_excludes")


def _list(v):
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.strip():
        try:
            p = json.loads(v)
            return p if isinstance(p, list) else [v]
        except ValueError:
            return [v]
    return []


def merge(current, additions):
    have = {norm(x).strip() for x in current}
    added = [x for x in additions if norm(x).strip() and norm(x).strip() not in have]
    return list(current) + added, added


def plan_for(row, spec):
    changes = {}
    for col in ("brand_keywords", "product_keywords"):
        # These columns feed the legacy name filter and other modules; new
        # names belong in config.aliases / config.products instead.
        if spec.get(col):
            new, added = merge(_list(row[col]), spec[col])
            if added:
                changes[col] = (new, added)
    cfg = row["config"] or {}
    if isinstance(cfg, str):
        cfg = json.loads(cfg or "{}")
    new_cfg, cfg_added = dict(cfg), {}
    for k, vals in (spec.get("config") or {}).items():
        if k not in LIST_CONFIG_KEYS:
            raise SystemExit(f"config key {k!r} is not a list field this script may extend")
        merged, added = merge(_list(cfg.get(k)), vals)
        if added:
            new_cfg[k] = merged
            cfg_added[k] = added
    if cfg_added:
        changes["config"] = (new_cfg, cfg_added)
    return changes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("profile_file")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    spec = json.load(open(args.profile_file))
    from app.database import get_database_instance
    conn = get_database_instance()._temp_get_connection()
    try:
        total = 0
        for name, bspec in spec["brands"].items():
            rows = conn.execute(text("""SELECT id, display_name, brand_keywords, product_keywords, config
                                          FROM bw_brands WHERE enabled AND lower(display_name) = lower(:n)"""),
                                {"n": name}).mappings().all()
            if len(rows) != 1:
                print(f"{name}: {len(rows)} enabled rows; skipped (needs exactly one)")
                continue
            row = rows[0]
            changes = plan_for(row, bspec)
            if not changes:
                print(f"{name}: nothing to add")
                continue
            for col, (_, added) in changes.items():
                print(f"{name}: {col} + {added}")
                total += len(added) if isinstance(added, list) else sum(len(v) for v in added.values())
            if args.apply:
                conn.execute(text("""UPDATE bw_brands SET
                        brand_keywords = COALESCE(CAST(:bk AS jsonb), brand_keywords),
                        product_keywords = COALESCE(CAST(:pk AS jsonb), product_keywords),
                        config = COALESCE(CAST(:cfg AS jsonb), config),
                        updated_at = NOW()
                      WHERE id = :id"""), {
                    "id": row["id"],
                    "bk": json.dumps(changes["brand_keywords"][0], ensure_ascii=False) if "brand_keywords" in changes else None,
                    "pk": json.dumps(changes["product_keywords"][0], ensure_ascii=False) if "product_keywords" in changes else None,
                    "cfg": json.dumps(changes["config"][0], ensure_ascii=False) if "config" in changes else None})
        if args.apply:
            conn.commit()
            print(f"Applied {total} addition(s).")
        else:
            print(f"Dry run: {total} addition(s). Re-run with --apply to write them.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
