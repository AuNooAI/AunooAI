#!/usr/bin/env python3
"""Record of the keyword and topic configuration changed on 2026-08-04.

These live in the database, not in the repo, so without this file there is no
audit trail for them. The script is idempotent: --verify reports whether the
live rows still match, --apply re-asserts them. It is a record first and a
replay mechanism second.

Background
----------
config.json held a topic named "Brand Monitoring Springer " with a trailing
space. set_topic() stripped the name it was asked for while load_config() built
its keys straight from the file, so the two never matched and Springer's
articles were analysed under Wiley's configuration. Fixing that (see
normalize_topic_name in app/research.py) switched Springer's analysis on for the
first time and exposed how the keyword set behaved.

What changed, and why
---------------------
1. Removed "Springer" and "Graduate Texts in Mathematics".
   Bare "Springer" also names a mathematician, a talk-show host and Axel
   Springer, a different media company. It was collecting Tomb Raider, baseball
   and press-release spam. No other brand group here matches on a bare
   ambiguous token: Wiley uses "John Wiley Sons", never "Wiley".

2. min_relevance_threshold 0.3 -> 0.5.
   0.5 is where the relevance decision already flips. Across all five brand
   topics every reading marked relevant scores >= 0.5 and none below it does
   (relevance_classifier_service.DEFAULT_THRESHOLD). At 0.3 the extra band was
   enriched by an LLM and then discarded — 537 such articles for Springer
   against 111 kept.

3. Group renamed "Springer  - Brand Watch" -> "Springer - Brand Watch"
   (it had a double space).

4. Added "SPGDF", the OTC ticker. Found in a headline reading "Springer Nature
   AG & Co. KGaA (SPGDF) Q1 2026 Earnings Call Transcript". The group had no
   financial identifier; Wiley's carries WLYY. Frankfurt's SPG was deliberately
   NOT used — it is also Simon Property Group on the NYSE.

5. Quoted "Springer Nature" and "BioMed Central".
   The collector now preserves a lone quoted phrase, so these search for
   adjacent words. Measured on the firehose: Springer Nature 404 -> 259 matches;
   BioMed Central 145 -> 26 matches with precision 12% -> 35%. Other keywords
   were left unquoted because quoting loses real hits — "Springer Publishing"
   would drop from 445 matches to 3.

6. Removed "Springer Science+Business Media".
   The collector converts + to OR, so it searched "Springer Science OR Business
   Media" — 123,021 matches, and the query does not even return within 150s.
   The name is defunct anyway: the company became Springer Nature in 2015 and
   the phrase returns 0 matches in every form.

7. Rewrote ("open access")+("research") as "open access research" on wbm,
   wiley, wileytest and bugfixing. Same + -> OR problem: it searched "open
   access OR research", which times out because "research" alone matches a
   large share of the corpus. Plain terms are ANDed, which is what the
   parentheses were reaching for.

Not changed, but worth an owner's eye: "Peter Tugendhat" is in the keyword set
and could not be confirmed as a Springer person. "Derk Haank" is genuine but a
former CEO.

Usage:
    python scripts/keyword_config_2026_08_04.py --verify
    python scripts/keyword_config_2026_08_04.py --apply
"""

import argparse
import os
import re
import sys
import urllib.parse

import psycopg2

GROUP_NAME = "Springer - Brand Watch"
SPRINGER_TOPIC = "Brand Monitoring Springer"
THRESHOLD = 0.5

# Keyword -> should it be present?
EXPECTED_ABSENT = [
    "Springer",
    "Graduate Texts in Mathematics",
    "Springer Science+Business Media",
]
EXPECTED_PRESENT = [
    "SPGDF",
    '"Springer Nature"',
    '"BioMed Central"',
]
# Tenants carrying the open-access keyword fix.
OPEN_ACCESS_OLD = '("open access")+("research")'
OPEN_ACCESS_NEW = "open access research"


def connect(tenant=None):
    base = f"/home/orochford/tenants/{tenant}.aunoo.ai" if tenant else \
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = open(os.path.join(base, ".env")).read()
    m = re.search(r"^DATABASE_URL=.*?://([^:]+):([^@]+)@([^:/]+):(\d+)/(\S+)", env, re.M)
    u, p, h, pt, d = m.groups()
    return psycopg2.connect(user=u, password=urllib.parse.unquote(p), host=h,
                            port=int(pt), dbname=d.strip(), connect_timeout=10)


def springer_group_id(cur):
    cur.execute("SELECT id FROM keyword_groups WHERE topic = %s AND name ILIKE %s",
                (SPRINGER_TOPIC, "%Brand Watch%"))
    row = cur.fetchone()
    return row[0] if row else None


def check(apply_changes):
    problems = []
    conn = connect()
    cur = conn.cursor()
    # Only wbm carries the Springer brand group. The open-access keyword below is
    # on four tenants, so it is checked either way rather than skipped here.
    gid = springer_group_id(cur)
    if gid is None:
        print("no Springer brand-watch group on this tenant — checking the "
              "open-access keyword only")
    else:
        cur.execute("SELECT name, min_relevance_threshold FROM keyword_groups WHERE id=%s", (gid,))
        name, thr = cur.fetchone()
        if name != GROUP_NAME:
            problems.append(f"group name is {name!r}, expected {GROUP_NAME!r}")
            if apply_changes:
                cur.execute("UPDATE keyword_groups SET name=%s WHERE id=%s", (GROUP_NAME, gid))
        if float(thr) != THRESHOLD:
            problems.append(f"threshold is {thr}, expected {THRESHOLD}")
            if apply_changes:
                cur.execute("UPDATE keyword_groups SET min_relevance_threshold=%s WHERE id=%s",
                            (THRESHOLD, gid))

        cur.execute("SELECT keyword FROM monitored_keywords WHERE group_id=%s", (gid,))
        have = {k for (k,) in cur.fetchall()}
        for kw in EXPECTED_ABSENT:
            if kw in have:
                problems.append(f"{kw!r} is present and should not be")
                if apply_changes:
                    cur.execute("DELETE FROM monitored_keywords WHERE group_id=%s AND keyword=%s",
                                (gid, kw))
        for kw in EXPECTED_PRESENT:
            if kw not in have:
                problems.append(f"{kw!r} is missing")
                if apply_changes:
                    cur.execute("INSERT INTO monitored_keywords (group_id, keyword, created_at) "
                                "VALUES (%s, %s, now())", (gid, kw))

    cur.execute("SELECT count(*) FROM monitored_keywords WHERE keyword=%s", (OPEN_ACCESS_OLD,))
    if cur.fetchone()[0]:
        problems.append(f"{OPEN_ACCESS_OLD!r} still present (should be {OPEN_ACCESS_NEW!r})")
        if apply_changes:
            cur.execute("UPDATE monitored_keywords SET keyword=%s WHERE keyword=%s",
                        (OPEN_ACCESS_NEW, OPEN_ACCESS_OLD))

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
    ap.add_argument("--verify", action="store_true", help="report drift without changing anything")
    args = ap.parse_args()
    if not (args.apply or args.verify):
        ap.error("pass --verify or --apply")
    sys.exit(check(args.apply))
