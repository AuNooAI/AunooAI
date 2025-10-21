-- Fix trailing spaces in topic names
-- Date: 2025-10-21
-- Issue: Topic names like "Patent Cliffs " have trailing spaces causing search failures

-- Step 1: Show affected topics
SELECT DISTINCT topic, LENGTH(topic) as len, LENGTH(TRIM(topic)) as trimmed_len
FROM articles
WHERE topic != TRIM(topic)
ORDER BY topic;

-- Step 2: Update articles table to trim all topic names
UPDATE articles
SET topic = TRIM(topic)
WHERE topic != TRIM(topic);

-- Step 3: Verify the fix
SELECT COUNT(*) as remaining_with_spaces
FROM articles
WHERE topic != TRIM(topic);

-- Expected result: 0 articles with trailing/leading spaces
