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
- A busy keyword is collected in full instead of being refused.
- The collection settings say which controls do nothing, and the group "Auto-Processing" switch
  now works.
- A new topic cannot be saved with an empty label list by accident.

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
about 3,500 a day for one keyword. We rewrote 24 of the 25 AI keywords so each phrase must appear
together with its pair. The 23 measured first return between 25 and 1,067 articles a day each,
over 24 hours on 7 October; the 24th returns about 1,540. The collector also refuses a keyword
that is still too broad, and says so. Before, it kept the newest few hundred results and skipped
the rest without telling anyone.

**Busy keywords collected in full.** A keyword with many phrases could be refused even when no
single phrase was too broad. One AI investment keyword was refused for its 2 October window: its
eight phrases together returned more than 2,100 articles in a day, but the busiest phrase on its
own returned about 1,500. The collector now searches such a keyword in smaller groups of phrases.
It is the same search, so the keyword means what it did. That keyword finished its 2 October
window the same evening.

**Settings that say what they do.** Four collection settings (quality control, save approved
only, temperature and max tokens) were shown and saved but never used. The daily request limit
was never enforced. They are now labelled "not used" and "not enforced", so nobody tunes a dial
that does nothing. The per-group "Auto-Processing" switch was also ignored before. It now works:
switched off, a group's articles are stored without the relevance check or analysis. No group on
any site has it off today.

**No topics that silently skip analysis.** A topic saved with an empty label list (for example
no sentiment values) gets its articles stored but never analysed. The topic forms now refuse that
save and say which list is empty. An admin can still save it on purpose.

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
- Keywords with many phrases are collected in full instead of being refused.
- Unused collection settings are labelled "not used"; the daily request limit is labelled
  "not enforced".
- The per-group Auto-Processing switch now takes effect.
- Topics cannot be saved with an empty label list unless analysis is switched off on purpose.

## Demo / walkthrough
None prepared. To check by hand on bugfixing:
- Ask Auspex about a brand topic and look for social posts among the cited sources.
- In Gather, open a keyword group's settings. The four unused controls are marked "(not used)",
  and the relevance threshold slider is always visible.
- On the health page, the request counter is labelled "NewsAPI Requests Today" and reads "limit
  not enforced".

## Positioning notes
None. These close gaps in our own pipeline; they are not a feature to sell against a competitor.

## Limits and what's next
- Only bugfixing has this. Every other customer site needs three database changes first, then
  the code, then a prompt update.
- The catch-up is still running. On bugfixing, 56 news keywords were still working through
  windows going back to 2 October at 16:32; each catches up when its group's turn comes round.
- The broad AI keyword ("AI") is still collected as it was; it fits under the new limit. One
  keyword in the geopolitical group (number 190) is still refused as too broad and needs narrowing.
- The daily request limit is labelled, not replaced. Per-provider quotas are the planned follow-on.
- Reading the full article page during analysis is built but switched off, pending a test on
  300 articles.
- The saas changes (importer recovery, topic classifier) are built and tested, not deployed.
