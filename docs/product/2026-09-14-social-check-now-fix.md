# Social posts keep their own words after a manual "check now"
_2026-09-14 · Keyword monitor, Social tab_

## What shipped

Pressing "check now" on a social keyword group now does exactly what the scheduled run
does. Posts from Reddit, Bluesky, X, Instagram and TikTok are scored for relevance and
sentiment by the cheap social evaluator and shown as written, translated to English when
they are not in English.

## Why it matters

Until today a manual run pushed those posts through the news pipeline instead. Its
analyzer replaced the post with a one-line description of the post and threw the original
text away, so the Social tab mixed real posts with paraphrases of posts, and each such
post cost a full news enrichment call. On oviva that was 18 posts; on sunstar it was 76
of today's 1,200.

## What did not change

Posts already rewritten keep their description. New collections, manual or scheduled,
keep the text.

## Where it is live

bugfixing, oviva, sunstar, wiley and wileytest, deployed 14 September 2026.
