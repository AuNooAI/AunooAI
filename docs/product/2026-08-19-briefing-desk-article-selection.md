# Briefing Desk now picks the most relevant stories, not the most recent ones
_2026-08-19 · Briefing Desk → Compose Today's Briefing_

## What shipped

- The daily briefing now picks articles by how well they match your topics, not by which one was
  published most recently.
- Social media posts no longer appear in the daily news briefing.
- Every topic you have selected gets a fair share of the shortlist, so a busy topic can no longer
  crowd out a quiet one.
- The same story published by several outlets now appears once instead of three times.
- The briefing reliably fills to its target of 8 articles, 7 incidents and 5 emerging topics.
- If the AI editor fails or returns an incomplete answer, the briefing still comes out with the
  best available stories rather than a short or empty one.

## Why it matters

**Before:** the briefing sorted every candidate story by publication time and handed the newest
30 to the AI editor. It ignored the relevance score the system had already calculated for each
article. Since social posts are collected around the clock, they were almost always the newest
rows, so they went to the top.

On the customer site we tested against, the three top candidates the AI editor saw were Bluesky
posts about a city council election in Jacksonville, Florida. The system had already scored all
three as **completely irrelevant** to the topic they were filed under. The briefing showed them
first anyway.

**Now:** relevance is half the score and recency is a tenth of it. Freshness still breaks ties
between two equally good stories, but it can no longer beat a strong story with a weak one.

---

**Before:** with 18 topics selected, 11 of them got nothing into the shortlist at all. Four busy
topics took 26 of the 30 slots. One of the shut-out topics was the customer's own brand, which
had 31 eligible articles waiting, 21 of them strongly on topic.

**Now:** the shortlist rotates through your topics one story at a time. On the live run, every
topic with material got exactly two slots.

---

**Before:** the briefing came up short almost every day. Across nine runs this month it staged a
median of **2 articles against a target of 8**. Analysts filled the gap by hand — on the morning
of the 19th, the system found one article and the analyst added three more manually over the next
quarter of an hour.

Meanwhile the incidents section ran the other way, staging up to 18 against a target of 7, because
nothing limited what the AI returned.

**Now:** the first live run produced 8 articles, 7 incidents and 5 emerging topics — every section
exactly on target, with no manual additions.

---

**Before:** the same story arriving from three different outlets took three of the thirty
shortlist slots. The system only checked for repeat *outlets*, which does nothing when a wire
story is republished everywhere.

**Now:** 77 duplicate stories were merged on the live run before the AI editor saw anything.

---

**Before:** the non-streaming version of the compose feature returned an error every single time
it was called, because of a mismatch between what it sent and what the underlying service
accepted. Nothing in the interface used that path, so it went unnoticed.

**Now:** both paths share one configuration and produce identical results.

**Who feels the difference:** the analyst who opens Briefing Desk each morning. The job goes from
"the system found one usable story, now go find seven more" to "review eight and cut the ones you
disagree with".

## Release notes (copy-ready)

- Briefing Desk now ranks candidate articles by topic relevance rather than publication time.
  Recency remains a factor for breaking ties between comparable stories.
- Social media posts are excluded from the daily news briefing. They remain available in Brand
  Watcher.
- Every selected topic receives a fair share of the candidate shortlist.
- Stories syndicated across multiple outlets are now shown once.
- Briefings reliably fill to their target size. When the AI editor is unavailable or returns an
  incomplete selection, the briefing is completed from the highest-ranked remaining articles
  rather than left short.
- Relevance and confidence thresholds set in the request are now applied. They were previously
  ignored.
- A briefing that fails while being composed no longer leaves an empty draft behind.

## Demo / walkthrough

News Feed → **Briefing Desk** → **Compose Today's Briefing** → select topics → Compose.

Watch the progress line during the gather step. It now reports the shortlist and what was removed,
for example:

> Ranked 472 on-topic articles, shortlisted 30 across 16/18 topics (14 already shared in the last
> 7d, skipped) (77 duplicate stories merged)

Then check the staged articles. Each one carries its relevance score, and every article should
clearly belong to one of your selected topics.

For a before-and-after on the customer site, compare "Daily Briefing — 2026-08-19" (composed on
the old code, one article) with "Daily Briefing — 2026-08-19 (2)" (composed on the new code, eight
articles).

## Positioning notes

This closes an obvious credibility gap. A daily intelligence briefing that opens with a stranger's
social post about a local council election is hard to defend in a renewal conversation, whatever
the rest of the product does well. The fix is not a new capability, it is the product doing what
customers already believed it did.

It also makes the multi-topic story honest. Selling "monitor 18 topics" while the briefing
silently covered seven of them was a gap between the pitch and the behaviour. It now covers every
topic that has material.

Worth being careful how this is described. The relevance scoring already existed and was already
good — the briefing was throwing its output away. This is a defect being closed, not a new
scoring engine, and describing it as the latter invites the question of what the old one was doing.

## Limits and what's next

**The topic relevance scores themselves are wrong for a small share of articles.** In the live
shortlist, a story about an arms seizure in the Middle East scores 0.90 against "Brand Monitoring
Wiley", and a fusion-startup funding round scores 0.81 against "Scientific Publishers". Roughly 1
in 10 of the candidates for one brand topic did not mention that brand. That is the scoring step,
which sits upstream of the briefing, and no amount of better ranking downstream can fix it. This
is the next thing worth looking at.

**One brand topic will now go quiet.** "Brand Monitoring SAGE Publishing" had 128 candidates in the
last week on the customer site, and every one of them was a social post. Excluding social from the
news briefing means that topic contributes nothing here. Those posts still appear in Brand Watcher.
If a customer wants social coverage inside brand topics specifically, that is a small, contained
change — but it should be a deliberate choice, not a surprise.

**The emerging topics section will still come up short some days.** It filled to 5 on the live run,
but its candidate pool is whatever the detection step last produced, and the briefing does not
re-run detection by default. That is a separate piece of work.

**Not yet on every customer site.** The change is live on two sites. Eight others carry the
briefing feature but not this fix, and will keep the old behaviour until it is copied across. None
of them currently run a scheduled daily briefing.

**This work is not yet committed to version control.** It is running in the two production
checkouts and sitting uncommitted in the canonical one.
