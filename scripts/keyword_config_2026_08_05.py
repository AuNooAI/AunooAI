#!/usr/bin/env python3
"""Record of the keyword and brand configuration changed on 2026-08-05.

These live in the database, so without this file there is no audit trail. Run
with --verify to report drift, --apply to re-assert. Tenant-aware: each check
only runs where the row exists, so the same script is valid on every tenant.

Why any of this changed
-----------------------
An adverse-media digest reported a "Product & Innovation coverage spike" for
Wiley whose driver articles were journal papers Wiley itself published, and the
Explore view showed Gaza ceasefire coverage filed under "AI & Content Licensing".
Both trace to the same mechanic: a collector treats an unquoted multi-word
keyword as an AND of its words anywhere in a document, not as a phrase.
"training data deal" matched 9,370 articles, because a ceasefire story contains
"deal" and the other words turn up in the body somewhere.

The generator was the source. app/routes/brand_watcher_routes.py:suggest_keywords
asked a model for keywords "specific enough to avoid false positives" and never
mentioned quoting, so suggestions came back bare. That is fixed in code (the
handler now quotes multi-word suggestions after the call). This file records the
data those earlier runs left behind.

1. AI & Content Licensing (wileytest, group 26)
   12 keywords -> 10, every one phrase-quoted. Three were replaced with the term
   actually used in print ("content licensing", "text and data mining",
   "AI licensing"); two were removed because no phrasing of them works —
   "training data deal" (9,370 loose, 0 as a phrase) and "collective licensing
   AI" (returns collectible license plates). Threshold 0.2 -> 0.5.
   Group reach: 92,057 matches -> 593.

2. Brand keywords with no brand-distinctive word (abm, wileytest, pbm)
   "Signal AI" matched 51,175 articles — everything containing "signal" and
   "AI". Quoted, 278. Also "Feedly AI" 24,897 -> 629, "Health sciences
   publications" 25,260 -> 38. "Blackbird AI" became "Blackbird.AI": quoting it
   as written returns 0, the dotted company name returns the real 5.
   "Elsvier Journals" was a typo matching nothing; corrected. "Science journals"
   removed — 1,498 even quoted, and not a name of Elsevier.
   Elsevier - Brand Watch threshold 0.2 -> 0.5.

3. Every remaining multi-word brand/social keyword (wbm, wileytest, bugfixing,
   pbm) — 180 rows. 119 were measured individually and quoted where the phrase
   form still found articles (combined reach 11,067 -> 3,408). The other 61 were
   quoted deliberately knowing it silences them: their phrase form returns
   nothing, so the loose form was a broad brand net rather than a search for the
   term. That is a real loss of reach, chosen for precision.

4. bw_brands (wbm, brand id 6)
   display_name 'Springer ' -> 'Springer', slug 'springer-' -> 'springer'.
   Not cosmetic: timeline_rollup.resolve_scope_for_topic strips the topic name
   before looking it up against display_name, so it searched for 'Springer' while
   the row held 'Springer ' and Springer's timeline fell back to topic scope.
   bw_official_sources also builds its queries and the group name
   f"{display_name} - Brand Watch" from the raw value.

Thresholds are 0.5 because that is where the relevance decision already flips:
across 3,649 readings on AI & Content Licensing, every article marked relevant
scores >= 0.5 and none below it does.

Usage:
    python scripts/keyword_config_2026_08_05.py --verify
    python scripts/keyword_config_2026_08_05.py --apply
"""

import argparse
import os
import re
import sys
import urllib.parse

import psycopg2

# (database, group name fragment) -> expected threshold. Scoped by tenant because
# only wileytest's groups were raised: its AI & Content Licensing and Elsevier
# groups sat at 0.2, the lowest anywhere. wbm's brand groups run at 0.3 and are
# not asserted here — that is a pre-existing setting, not something this change
# touched, and an audit script should not quietly move it.
THRESHOLDS = {
    ("wileytest", "AI & Content Licensing"): 0.5,
    ("wileytest", "Elsevier - Brand Watch"): 0.5,
}
# keywords that must not exist any more, with the reason
GONE = {
    "training data deal": "9,370 loose, 0 as a phrase",
    "collective licensing AI": "returns collectible license plates",
    "Science journals": "1,498 even quoted; not an Elsevier term",
    "Elsvier Journals": "typo, matched nothing",
    "Blackbird AI": "replaced by \"Blackbird.AI\"",
}
BRANDY = "(g.name ILIKE '%Brand Watch%' OR g.name ILIKE '%Social%' " \
         "OR g.topic = 'AI & Content Licensing')"


def connect():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = open(os.path.join(base, ".env")).read()
    m = re.search(r"^DATABASE_URL=.*?://([^:]+):([^@]+)@([^:/]+):(\d+)/(\S+)", env, re.M)
    u, p, h, pt, d = m.groups()
    return psycopg2.connect(user=u, password=urllib.parse.unquote(p), host=h,
                            port=int(pt), dbname=d.strip(), connect_timeout=10)


def check(apply_changes):
    problems = []
    conn = connect()
    cur = conn.cursor()

    # 1-3: every brand/social keyword searched as a phrase, not loose words.
    cur.execute(f"""
        SELECT k.id, g.name, k.keyword FROM monitored_keywords k
        JOIN keyword_groups g ON g.id = k.group_id
        WHERE g.is_active AND {BRANDY}
          AND k.keyword NOT LIKE '"%%"' AND k.keyword ~ '\\s'
          AND k.keyword !~ '[|+()]' AND k.keyword !~ '\\y(AND|OR|NOT)\\y'
    """)
    loose = cur.fetchall()
    for kid, gname, kw in loose:
        problems.append(f"{gname}: {kw!r} searches as loose words")
        if apply_changes:
            cur.execute("UPDATE monitored_keywords SET keyword=%s WHERE id=%s",
                        (f'"{kw}"', kid))

    for kw, why in GONE.items():
        cur.execute("SELECT count(*) FROM monitored_keywords WHERE keyword=%s", (kw,))
        if cur.fetchone()[0]:
            problems.append(f"{kw!r} is present again ({why})")
            if apply_changes:
                cur.execute("DELETE FROM monitored_keywords WHERE keyword=%s", (kw,))

    cur.execute("SELECT current_database()")
    dbname = cur.fetchone()[0]
    for (want_db, frag), want in THRESHOLDS.items():
        if want_db != dbname:
            continue
        cur.execute("SELECT id, min_relevance_threshold FROM keyword_groups "
                    "WHERE name ILIKE %s OR topic = %s", (f"%{frag}%", frag))
        for gid, thr in cur.fetchall():
            if thr is None or float(thr) != want:
                problems.append(f"group {frag!r} threshold is {thr}, expected {want}")
                if apply_changes:
                    cur.execute("UPDATE keyword_groups SET min_relevance_threshold=%s "
                                "WHERE id=%s", (want, gid))

    # 4: brand names carry no stray whitespace.
    try:
        cur.execute("SELECT id, name, display_name FROM bw_brands "
                    "WHERE display_name <> btrim(display_name) OR name ~ '-$'")
        for bid, name, disp in cur.fetchall():
            problems.append(f"bw_brands id={bid}: {disp!r}/{name!r} has stray whitespace")
            if apply_changes:
                cur.execute("UPDATE bw_brands SET display_name=%s, name=%s WHERE id=%s",
                            (" ".join(disp.split()), re.sub(r"-+$", "", name or ""), bid))
    except Exception:
        conn.rollback()  # tenant has no bw_brands

    if apply_changes:
        conn.commit()
        print(f"applied {len(problems)} correction(s).")
    elif problems:
        print("live configuration does NOT match this record:")
        for p in problems:
            print(f"  - {p}")
    else:
        print("live configuration matches this record.")
    conn.close()
    return 1 if (problems and not apply_changes) else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="re-assert the recorded state")
    ap.add_argument("--verify", action="store_true", help="report drift, change nothing")
    args = ap.parse_args()
    if not (args.apply or args.verify):
        ap.error("pass --verify or --apply")
    sys.exit(check(args.apply))
