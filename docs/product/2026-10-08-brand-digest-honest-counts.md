# Brand Watcher digest: correct counts, labelled time windows, and why each story names the brand
_2026-10-08 · Brand Watcher daily and weekly adverse-media digest email, sentiment alerts, brand report_

## What shipped
- The digest now says what part each brand plays in a story, such as being named in a ruling
  or mentioned in passing.
- Every sentiment figure in the digest now names its time window: last day or last 7 days.
- News sentiment counts each article once. Before, an article with several topic labels was
  counted once per label.

## Why it matters

**Readers can see why a story is in a brand's section.** Oviva's digest on 8 October put a story
about the UK advertising regulator under Juniper. The story's summary was about weight-loss drug
advertising in general, so the link looked like a mistake. It wasn't. The article says the
regulator ruled against Juniper and two other firms. The digest now says that: "…made three
further rulings against MedExpress, Juniper and the Care Pharmacy for promoting
prescription-only medicines to the public." When a brand isn't named in an article at all, the
digest now says the coverage is about the sector. A comms analyst can then decide at a glance
whether to act, without opening the article.

**Two figures no longer seem to contradict each other.** The same email gave Juniper's news
sentiment as 0, then two lines later showed an alert saying -25. Both were right. The first
covered the last day and the second covered the last 7 days, but neither said so. A reader
had no way to tell, and a digest that seems to contradict itself loses trust in every figure
it shows. Each figure now carries its window.

**Counts match the articles a reader can see.** Our system files each article under one or more
topic labels, such as "Legal & Regulatory" or "Media & Advertising". The sentiment count added
up labels, not articles. So the Juniper alert reported 5 negative articles out of 20 when there
were 2 out of 8. In that case the overall score was the same by coincidence. Over the last
week, though, the label count moved brand scores by up to 13 points. On one customer site, a
brand scored +56 by the old count and +43 by the right one. Alerts that fire once enough
articles have been scored could also fire early, on too few real articles.

## Release notes (copy-ready)
- The digest now says what part a brand plays in each story behind an alert, or says the
  coverage is about the sector when the brand isn't named.
- Sentiment figures in the digest now show their time window (last day / last 7 days).
- Fixed: news sentiment counted an article once per topic label. Counts and scores now reflect
  each article once, so some brand scores will shift by a few points.

## Demo / walkthrough
The changes appear in the next daily or weekly digest email. They also appear in the brand
report's employee-review line. There is no new screen.

## Positioning notes
Customers who use this as an early warning act on what the email tells them. A brand section
that explains its own stories, with figures that agree with each other, can be forwarded to a
comms lead without someone checking it first.

## Limits and what's next
- Alerts sent before 8 October keep their old, inflated counts in the alert history. The digest
  shows only the time window for those alerts, not the counts.
- The brand's part in a story comes from the article text we store. When we don't have the full
  text, the digest falls back to saying the brand isn't named.
- Five sites (abbott, bwtemplate, ibaset, interroll, pbm) were not running. They get the fix
  when they next start, and nobody has seen it run on them yet.
- Brand scores will move by a few points on sites where articles carry several topic labels.
  This is the correction, not a new trend. Anyone tracking a score over time should know this.
