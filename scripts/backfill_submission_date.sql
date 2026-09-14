-- One shape for articles.submission_date.
--
-- The column is text. PostgreSQL fills it with CURRENT_TIMESTAMP, which
-- prints as local time with the offset, e.g. 2026-08-28 13:00:24.580955+02.
-- Some writers stamped ISO "T...Z" (UTC), a bare date, or a naive time
-- instead; since "T" sorts after a space, same-day text comparisons
-- silently dropped rows. The writers were fixed on 2026-08-28
-- (app/utils/timestamps.py). This rewrites the rows written before that.
--
-- Every odd row parses as timestamptz (checked on bugfixing: 3,618 of
-- 3,618), so the conversion is exact. Empty strings become NULL like the
-- other blanks. One transaction; counts before and after.
--
-- Run:  psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -v ON_ERROR_STOP=1 \
--            -f scripts/backfill_submission_date.sql
BEGIN;

SELECT count(*) AS articles_to_fix FROM articles
 WHERE submission_date IS NOT NULL AND submission_date <> ''
   AND submission_date !~ '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?[+-]\d{2}(:\d{2})?$';

UPDATE articles SET submission_date = (submission_date::timestamptz)::text
 WHERE submission_date IS NOT NULL AND submission_date <> ''
   AND submission_date !~ '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?[+-]\d{2}(:\d{2})?$';

UPDATE articles SET submission_date = NULL WHERE submission_date = '';

UPDATE raw_articles SET submission_date = (submission_date::timestamptz)::text
 WHERE submission_date IS NOT NULL AND submission_date <> ''
   AND submission_date !~ '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?[+-]\d{2}(:\d{2})?$';

SELECT CASE WHEN submission_date ~ '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?[+-]\d{2}$' THEN 'stored shape'
            WHEN submission_date IS NULL THEN 'null'
            ELSE 'other: ' || left(submission_date, 30) END AS fmt,
       count(*)
  FROM articles GROUP BY 1 ORDER BY 2 DESC;

SELECT max(submission_date) AS newest,
       count(*) FILTER (WHERE submission_date >= to_char(now() - interval '24 hours', 'YYYY-MM-DD HH24:MI:SS')) AS last_24h
  FROM articles;

COMMIT;
