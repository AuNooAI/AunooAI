#!/bin/bash
# One-screen data quality report for a monolith site.
#
#   sudo scripts/data_quality_check.sh <site> [days]      e.g.  sudo scripts/data_quality_check.sh sunstar 14
#
# Reads the site's database as the postgres user and its service journal. Changes nothing.
# The numbers mirror docs/DATA_QUALITY_REVIEW_POV_SITES_2026-10-05.md so a week-on-week
# comparison is like for like. "News" = rows without social metadata.
set -u
site="${1:?site short name, e.g. sunstar}"
days="${2:-14}"
db="$site"; [ "$site" = "bugfixing" ] && db="test"
unit="$site.aunoo.ai.service"
since="to_char(now()-interval '$days days','YYYY-MM-DD')"
news="(social_meta is null or social_meta::text='null')"
social="(social_meta is not null and social_meta::text<>'null')"
q() { sudo -u postgres psql -d "$db" -X -At -F ' | ' -c "$1" 2>&1; }
hdr() { printf '\n## %s\n' "$1"; }

printf '# Data quality: %s, last %s days, %s\n' "$site" "$days" "$(date '+%Y-%m-%d %H:%M')"

hdr "Volume and outcomes (news rows: total / approved / rejected by relevance / enriched; social rows: total / on-brand)"
q "select
  (select count(*) from articles where left(submission_date,10) >= $since and $news) news,
  (select count(*) from articles where left(submission_date,10) >= $since and $news and ingest_status='approved') approved,
  (select count(*) from articles where left(submission_date,10) >= $since and $news and ingest_status='filtered_relevance') rejected,
  (select count(*) from articles where left(submission_date,10) >= $since and $news and category is not null) enriched,
  (select count(*) from articles where left(submission_date,10) >= $since and $social) social,
  (select count(*) from articles where left(submission_date,10) >= $since and $social and topic_alignment_score>=0.4) social_onbrand"

hdr "Per topic: news / approved / social / on-brand social (top 15 by volume)"
q "select topic,
  count(*) filter (where $news) news,
  count(*) filter (where $news and ingest_status='approved') approved,
  count(*) filter (where $social) social,
  count(*) filter (where $social and topic_alignment_score>=0.4) onbrand
  from articles where left(submission_date,10) >= $since group by 1 order by 2 desc, 4 desc limit 15"

hdr "Keywords that produce the most rejected news rows (rows / approved) — loose body matching is normal, zero approvals over weeks is not"
q "select k.keyword, count(*) rows, count(*) filter (where a.ingest_status='approved') approved
  from keyword_article_matches m join articles a on a.uri=m.article_uri
  join monitored_keywords k on k.id = split_part(m.keyword_ids,',',1)::int
  where left(m.detected_at::text,10) >= $since and $news group by 1 order by 2 desc limit 10"

hdr "Social rows missing metadata the product needs (platform / rows / without sentiment / without author role)"
q "select coalesce(social_meta->>'platform','?') platform, count(*) rows,
  count(*) filter (where sentiment is null) no_sentiment, count(*) filter (where author_role is null) no_role
  from articles where left(submission_date,10) >= $since and $social group by 1 order by 2 desc"

hdr "Posts stored as news (reddit, x, bluesky URLs without social metadata) — should be 0"
q "select count(*) from articles where left(submission_date,10) >= $since and $news and uri ~ '^(https?://)?(www\.)?(reddit\.com|x\.com|twitter\.com|bsky\.app)/'"

hdr "Duplicates: same title on different URLs (groups / extra rows) and press-release wires (rows / approved)"
q "select (select count(*) from (select title from articles where left(submission_date,10) >= $since and $news and title is not null group by title having count(*)>1) d) dup_groups,
  (select coalesce(sum(n-1),0) from (select count(*) n from articles where left(submission_date,10) >= $since and $news and title is not null group by title having count(*)>1) d) extra_rows,
  (select count(*) from articles where left(submission_date,10) >= $since and $news and uri ~ '(prtimes|prnewswire|businesswire|globenewswire|presseportal|atpress|openpr|newswire)') wire_rows,
  (select count(*) from articles where left(submission_date,10) >= $since and $news and ingest_status='approved' and uri ~ '(prtimes|prnewswire|businesswire|globenewswire|presseportal|atpress|openpr|newswire)') wire_approved"

hdr "Deal listings: rejected by the rule (last 7 days, journal) / still approved (should be 0)"
printf '%s rejected | ' "$(sudo journalctl -u "$unit" --since "7 days ago" --no-pager 2>/dev/null | grep -c 'Deal listing rejected')"
q "select count(*) from articles where left(submission_date,10) >= $since and $news and ingest_status='approved' and (uri ~* '(dealigg|slickdeals|dansdeals|ozbargain|hotukdeals|dealnews|bensbargains|mydealz|hip2save|9to5toys|retailmenot|couponfollow)' or title ~* '(best deal|deal alert|promo codes?|coupon|\\d+ ?% off)')"

hdr "Top source domains of approved news (owned vendor blogs show up here)"
q "select split_part(regexp_replace(uri,'^https?://(www\.)?',''),'/',1) domain, count(*) approved
  from articles where left(submission_date,10) >= $since and $news and ingest_status='approved' group by 1 order by 2 desc limit 8"

hdr "Non-English groups: rows / translated (title in English, original kept)"
q "select a.topic, count(*) rows, count(*) filter (where original_title is not null) translated
  from articles a join keyword_groups g on g.topic=a.topic
  where g.language is not null and g.language<>'en' and left(a.submission_date,10) >= $since and $news group by 1 order by 2 desc limit 8"

hdr "Enrichment failures and rows stuck without a status"
q "select coalesce(ingest_status,'(null)') status, count(*) from articles where left(submission_date,10) >= $since and $news and (ingest_status is null or ingest_status not in ('approved','filtered_relevance')) group by 1 order by 2 desc"

hdr "Observer pool, last 3 days (enriched news / on-brand social)"
q "select count(*) filter (where $news and category is not null) news_enriched,
  count(*) filter (where $social and topic_alignment_score>=0.4) social_onbrand
  from articles where left(submission_date,10) >= to_char(now()-interval '3 days','YYYY-MM-DD')"

hdr "Collector groups not checked in the last 24 hours, or carrying an error"
q "select id, name, to_char(last_checked_at,'MM-DD HH24:MI') last_check, left(coalesce(last_error,''),60) err
  from keyword_groups where is_active and (last_checked_at < now()-interval '24 hours' or coalesce(last_error,'')<>'') order by id"

hdr "RSS feeds with an error"
q "select id, left(url,60) url, is_active, left(coalesce(last_error,''),50) err from rss_feeds where coalesce(last_error,'')<>'' order by id"

hdr "Collector errors in the service journal, last 7 days (count / provider / message)"
sudo journalctl -u "$unit" --since "7 days ago" --no-pager 2>/dev/null \
  | grep -E "collectors\.[a-z_]+ - ERROR" \
  | sed -E 's/.*collectors\.([a-z_]+) - ERROR - (.{0,70}).*/\1: \2/' | sort | uniq -c | sort -rn | head -8

hdr "Phantom guard (CJK groups): results dropped because the page lacked the term, last 7 days"
sudo journalctl -u "$unit" --since "7 days ago" --no-pager 2>/dev/null | grep -c "the search term is not on the page"

hdr "Story labels (only on sites with the duplicates build)"
if q "select 1 from information_schema.columns where table_name='articles' and column_name='duplicate_of'" | grep -q 1; then
  q "select count(*) filter (where duplicate_of is not null) copies, count(*) filter (where source_type='press_release') press_releases from articles where left(submission_date,10) >= $since"
else
  echo "not built on this site"
fi
