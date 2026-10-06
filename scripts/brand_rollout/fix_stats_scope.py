#!/usr/bin/env python3
"""Move Brand Watcher /stats' earned-news rule into the subquery where the
classification row (bac) is in scope. Idempotent; refuses if the anchor is
missing. Usage: fix_stats_scope.py <site tree> [--apply]"""
import os, sys
tree = sys.argv[1]; apply = "--apply" in sys.argv
p = os.path.join(tree, "app/routes/brand_watcher_routes.py"); s = open(p, encoding="utf-8").read()
if "_bcov.earned_news_scoped_sql('a2', 'bac')" in s:
    print(f"{tree}: already fixed"); sys.exit(0)
a = """                WHERE COALESCE(bac.relevance_score, a2.topic_alignment_score) >= 0.4
                {brand_filter}
                GROUP BY bac.article_uri
            ) cc ON a.uri = cc.article_uri
            WHERE a.publication_date >= :start AND a.publication_date <= :end
              -- earned coverage only: social posts and the brand's own publishing
              -- are excluded here. The article list is deliberately wider (it keeps
              -- owned rows, flagged), so these counts can sit below the list length;
              -- owned_articles below says by how much.
              AND {_EARNED_NEWS}
            {topic_filter}"""
b = """                WHERE COALESCE(bac.relevance_score, a2.topic_alignment_score) >= 0.4
                -- earned coverage only: social posts and the brand's own publishing
                -- are excluded here. The article list is deliberately wider (it keeps
                -- owned rows, flagged), so these counts can sit below the list length;
                -- owned_articles below says by how much. Applied inside the
                -- subquery, where the classification row (bac) is in scope: the
                -- brand-scoped rule reads bac.brand_id (6 Oct: the outer
                -- placement failed with "missing FROM-clause entry for table bac"
                -- once brand labels were active).
                AND {_bcov.earned_news_scoped_sql('a2', 'bac')}
                {brand_filter}
                GROUP BY bac.article_uri
            ) cc ON a.uri = cc.article_uri
            WHERE a.publication_date >= :start AND a.publication_date <= :end
            {topic_filter}"""
import re
# Older sites carry a different comment between the WHERE and the rule; match
# the code and any comment lines in between.
rx = re.compile(r"""(                WHERE COALESCE\(bac\.relevance_score, a2\.topic_alignment_score\) >= 0\.4
)(                \{brand_filter\}
                GROUP BY bac\.article_uri
            \) cc ON a\.uri = cc\.article_uri
            WHERE a\.publication_date >= :start AND a\.publication_date <= :end
)((?:              --[^\n]*\n)*)              AND \{_EARNED_NEWS\}
(            \{topic_filter\})""")
m = list(rx.finditer(s))
if len(m) != 1:
    print(f"{tree}: anchor found {len(m)} times; nothing written"); sys.exit(2)
mm = m[0]
comments = "".join("  " + ln + "\n" for ln in mm.group(3).splitlines())
new = (mm.group(1) + comments +
       "                -- Applied inside the subquery, where the classification row (bac) is in scope:\n"
       "                -- the brand-scoped rule reads bac.brand_id (6 Oct: outside it failed with\n"
       "                -- \"missing FROM-clause entry for table bac\" once brand labels were active).\n"
       "                AND {_bcov.earned_news_scoped_sql('a2', 'bac')}\n" + mm.group(2) + mm.group(4))
if apply:
    import shutil, time
    shutil.copy2(p, f"/var/tmp/brand_rollout/backup/{os.path.basename(tree.rstrip('/'))}-brand_watcher_routes.py.{time.strftime('%H%M%S')}")
    open(p, "w", encoding="utf-8").write(s[:mm.start()] + new + s[mm.end():]); print(f"{tree}: fixed")
else:
    print(f"{tree}: anchor matches; dry run")
