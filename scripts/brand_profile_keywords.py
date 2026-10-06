#!/usr/bin/env python3
"""Bring brand groups' search terms in line with the brand profile.

docs/BRAND_RELEVANCE_SPEC.md: collectors must search with the configured
company names, products and language variants. Each brand topic's keyword
groups are compared with its effective profile (app/services/brand_profile.py)
and the missing names are proposed:

- names in a script without spaces (Japanese, Chinese, Korean, Thai) go to the
  brand's groups whose language is not English; Latin-script names go to its
  English or unspecified groups; a brand with one group gets everything;
- multi-word Latin names are quoted, because TheNewsAPI reads a space as AND
  and a proper noun should match as a phrase;
- short or ambiguous names (BrandProfile.collection_terms) are never added;
- a name that contains an already-searched name as a whole word is skipped,
  because the shorter search already returns it (quota matters);
- a name the site searches only inside a longer qualified term is skipped:
  that narrowing is an explicit tenant rule.

Nothing is removed. Default is a dry run; --apply inserts the proposed rows.
Run from the site's tree so its .env names its database:

    cd /home/orochford/tenants/sunstar.aunoo.ai && .venv/bin/python scripts/brand_profile_keywords.py
    ... --apply            # after reviewing the list
    ... --brand "Lion Corporation"
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.services import brand_profile as bp  # noqa: E402
from app.services.brand_coverage import brand_topics  # noqa: E402


def _bare(term: str) -> str:
    return bp.norm(term).strip().strip('"').strip()


def _covered(term: str, existing) -> bool:
    import re
    for e in existing:
        if not e or e == term:
            continue
        if bp._is_spaced_script(e):
            if re.search(r"(?<![0-9a-z])" + re.escape(e) + r"(?![0-9a-z])", term):
                return True
        elif e in term:
            return True
    return False


def _narrowed(term: str, existing) -> bool:
    import re
    pat = re.compile(r"(?<![0-9a-z])" + re.escape(term) + r"(?![0-9a-z])") if bp._is_spaced_script(term) else None
    for e in existing:
        if not e or e == term or len(e) <= len(term):
            continue
        if (pat.search(e) if pat else term in e):
            return True
    return False


def _query_form(term: str) -> str:
    t = term.strip()
    if bp._is_spaced_script(t) and " " in t and not t.startswith('"'):
        return f'"{t}"'
    return t


def _is_latin(term: str) -> bool:
    return bp._is_spaced_script(term)


def propose(conn, only_brand: str | None = None):
    rows, registry = bp.load_rows(conn)
    # Older sites have no keyword_groups.language column: every group is then
    # "language unspecified" and takes Latin-script names.
    has_language = bool(conn.execute(text("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'keyword_groups' AND column_name = 'language'
           AND table_schema = ANY(current_schemas(false))""")).first())
    plan = []
    for r in rows:
        if only_brand and bp.norm(r["display_name"]) != bp.norm(only_brand):
            continue
        prof = bp.build_profile(r, registry.get(int(r["id"]), ()))
        lang = "language" if has_language else "NULL AS language"
        groups = conn.execute(text(f"""
            SELECT id, name, topic, {lang} FROM keyword_groups WHERE topic = ANY(:t) ORDER BY id
        """), {"t": brand_topics(prof.display_name)}).mappings().all()
        if not groups:
            continue
        existing = {}
        for g in groups:
            existing[g["id"]] = {_bare(k) for (k,) in conn.execute(text(
                "SELECT keyword FROM monitored_keywords WHERE group_id = :g"), {"g": g["id"]})}
        all_existing = set().union(*existing.values())
        latin_groups = [g for g in groups if (g["language"] or "en").lower().startswith("en")] or list(groups)
        other_groups = [g for g in groups if not (g["language"] or "en").lower().startswith("en")] or list(groups)
        for term in prof.collection_terms():
            if _bare(term) in all_existing:
                continue
            # A search for a name already covers longer names that contain it
            # as a whole word ("Sunstar" returns "Sunstar Group"), so adding
            # those only spends provider quota.
            if _covered(_bare(term), all_existing):
                continue
            # The site already searches this name only inside a longer,
            # qualified term ('"Second Nature" weight'): a deliberate narrowing,
            # an explicit tenant rule the bare name must not undo.
            if _narrowed(_bare(term), all_existing):
                continue
            targets = latin_groups if _is_latin(term) else other_groups
            if len(groups) == 1:
                targets = list(groups)
            for g in targets[:1]:
                plan.append({"brand": prof.display_name, "group_id": g["id"], "group": g["name"],
                             "language": g["language"], "keyword": _query_form(term)})
    return plan


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="insert the proposed keywords")
    ap.add_argument("--brand", help="only this brand (display name)")
    args = ap.parse_args()
    from app.database import get_database_instance
    conn = get_database_instance()._temp_get_connection()
    try:
        plan = propose(conn, args.brand)
        if not plan:
            print("Nothing to add: every brand group already searches its profile's names.")
            return 0
        for p in plan:
            print(f"{p['brand']:<28} group {p['group_id']:<4} {p['group']:<40} [{p['language'] or '-'}]  + {p['keyword']}")
        print(f"\n{len(plan)} keyword(s) proposed.")
        if not args.apply:
            print("Dry run. Re-run with --apply to insert them.")
            return 0
        now = datetime.now(timezone.utc).isoformat()
        for p in plan:
            conn.execute(text("""
                INSERT INTO monitored_keywords (group_id, keyword, created_at)
                SELECT :g, :k, :c WHERE NOT EXISTS (
                    SELECT 1 FROM monitored_keywords WHERE group_id = :g AND keyword = :k)
            """), {"g": p["group_id"], "k": p["keyword"], "c": now})
        conn.commit()
        print(f"Inserted {len(plan)} keyword(s).")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
