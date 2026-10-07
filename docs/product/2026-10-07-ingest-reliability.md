# Fewer lost articles, social posts in search, steadier analysis
_7 October 2026 · Collection, article analysis, Auspex search and the monitoring agents (bugfixing only so far)_

Most of this work is internal plumbing that customers never see directly. This note covers the
parts a customer would notice. It is not yet copy for external use: only bugfixing runs the new
code, and the other customer sites have not been updated.

## What shipped
- Social posts that passed the relevance check can now be found by Auspex's search.
- The incident and real-time signal views now use relevant social posts as evidence.
- The AI keyword group collects what its keywords say, instead of everything that mentions AI.
- Article analysis no longer stores a blank label when the model answers badly.
- Failed steps are retried or reported, instead of leaving articles half-processed.

## Why it matters
**Social posts in search.** A social post could be scored relevant and shown on the Social tab,
yet Auspex's search never found it. We never computed its search fingerprint (an "embedding").
On bugfixing that was 2,234 relevant posts. Now all of them have one, and new posts get one
after they are scored. Analysts asking Auspex about a topic get the social conversation as well
as the news.

**Social evidence for the agents.** The incident tracker and the real-time signals view read only
articles with a category, and social posts never get one. They now take posts that passed the
relevance check and were not flagged as false positives. On bugfixing that added 885 posts from
the last 14 days. We do not invent categories for them.

**AI keywords that mean what they say.** A keyword like "AI regulation, antitrust, lawsuit, plus
AI" reached the news source as "any of these words", so it matched nearly every AI story: up to
about 3,500 a day for one keyword. We rewrote 23 of the 25 AI keywords so each phrase must appear
together with its pair. They now return between 25 and 1,067 articles a day each, measured over
24 hours on 7 October. The collector also refuses a keyword that is still too broad and says so.
Before, it kept the newest few hundred results and skipped the rest without telling anyone.

**Cleaner labels.** When the AI analysis step returned a sentiment that is not on the topic's
list, we stored a blank. It now asks again, and records a failure if the answer is still wrong.
The automated analysis also stopped asking for two fields it never kept (political bias and
factuality).

**Nothing silently half-done.** Articles whose relevance check failed, or whose search
fingerprint failed, are now retried on a schedule. They appear on the health page when they need
a person.

## Release notes (internal only until all sites are updated)
- Auspex search now includes relevant social posts.
- Incident tracking and real-time signals now use relevant social posts as evidence.
- AI topic keywords narrowed to match their intended meaning.
- Analysis retries invalid labels instead of storing blanks.
- Failed processing steps are retried and shown on the health page.

## Demo / walkthrough
None prepared. To check by hand on bugfixing, ask Auspex about a brand topic and look for social
posts among the cited sources.

## Positioning notes
None. These close gaps in our own pipeline; they are not a feature to sell against a competitor.

## Limits and what's next
- Only bugfixing has this. Every other customer site needs three database changes first, then
  the code, then a prompt update.
- Two AI keywords are unchanged. One is still too broad after narrowing (about 1,540 articles a
  day), and the other ("AI") is the whole topic. Both need a decision.
- Reading the full article page during analysis is built but switched off, pending a test on
  300 articles.
- The saas changes (importer recovery, topic classifier) are built and tested, not deployed.
