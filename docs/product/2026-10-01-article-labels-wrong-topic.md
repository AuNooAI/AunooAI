# Articles no longer carry another topic's labels
_1 October 2026 · topic feeds, labels and filters on every monitoring site; repair on Wiley's site_

Audience note: this fixes a fault Wiley's readers could see, but it isn't a feature. Use the
release note below when someone asks. Don't send the root-cause section to a customer.

## What shipped
- Each article now keeps the labels of the topic it's filed under. Before, an article found by
  two topics could end up filed under one and labelled by the other.
- Wiley's articles from the last 30 days that had picked up the wrong labels are being labelled
  again for their own topic.

## Why it matters
**Before.** One article is often found by several topics. Each topic's AI step labels it from
that topic's own list, such as "Deal announced" for M&A or "Escalation" for Geopolitical
Hotspots. Only one topic can own the article. But when a second topic looked at it later
without scoring it higher, the article stayed with the first topic and took the second topic's
labels. Readers saw articles like an Iran war story under intralogistics, labelled "Military
Activity". Category and signal filters miscounted too, because they counted labels that didn't
belong to the topic.

**How often.** On Wiley's site, about 1 in 50 approved articles in the second half of September
had another topic's labels. Before a partial fix on 16 September, it was about 1 in 14.

**Now.** A topic's score, ownership and labels move together: when a topic doesn't take the
article, it leaves the labels alone. New articles stay consistent from today, on each site once
it has restarted with the fix.

**Who notices.** Analysts filtering a topic by category or future signal, and anyone reading
topic-level counts in briefings and reports.

## Release notes (copy-ready)
- Fixed: an article found by several topics could show labels (category, future signal,
  sentiment) from a different topic. Each article now carries its own topic's labels.
- Wiley: articles from the last 30 days that were affected have been labelled again.

## Demo / walkthrough
None. The difference shows only when you compare an article's labels with its topic.

## Positioning notes
None. This is a correctness fix.

## Limits and what's next
- **Older Wiley articles keep their wrong labels.** We repaired the last 30 days only: 684
  articles. About 8,000 older ones still carry another topic's labels, because a full repair
  would re-run the AI step and the relevance check on all of them.
- **The repair removed 200 articles from their topics.** Of the 684 repaired, 484 were confirmed
  and relabelled. The other 200 had been filed under a topic that never wanted them: they had
  borrowed another topic's score. Examples are a legal-tech alliance under Geopolitical Hotspots
  and a hotel sale under AI and Machine Learning. They were removed, which is correct, but they
  weren't moved to the topic that did want them. A few relevant ones, such as a Wiley earnings
  story, are now missing from Wiley's brand topic.
- **Other sites aren't measured or repaired yet.** wiley, panaya, wbm, oviva, sunstar and abm have
  the fix for new articles once restarted, but nobody has measured how many older articles they
  have with the wrong labels.
- **Relevance scores vary between passes.** The same topic scored the same article anywhere from
  0.3 to 0.8 on different passes. That's a separate issue, and it affects which topic gets an
  article in the first place.
