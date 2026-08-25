# Every vendor fact now says where it came from
_2026-08-25 · Market Monitor vendor pages, vendor lists and filters, Brand Watcher social feed_

**Status: built, not switched on.** The code is committed to the canonical tree but nothing is
deployed, and every new read path sits behind a flag that is currently off. Customers see no
change today. This document describes what turning it on does, so the decision to turn it on can
be made with the trade-offs visible.

## What shipped

- Every company fact on a vendor page — headcount, funding, country, founding year — now records
  which source said it and on what date, and keeps every previous reading.
- A newer, better source can replace a value from the original spreadsheet. Until now the
  spreadsheet value was permanent.
- Blank cells in that spreadsheet stop being shown as a headcount of zero.
- A social post that names two vendors now gets a separate rating for each one, instead of both
  vendors sharing whichever rating was worked out last.
- A vendor's own marketing posts are separated from what other people said about them, and are
  no longer counted in how positively the vendor is being discussed.
- The vendor timeline distinguishes "the vendor announced this" from "someone independent
  confirmed it", and counts sources rather than articles.
- Generated summaries are checked against the underlying data. Any number in the text that is
  not in the evidence is flagged before anyone reads it.
- The market's RSS feed now carries the current Aunoo logo. It previously had no logo at all.

## Why it matters

**A number with no source is a number you cannot defend.** Before, a vendor page said "310
people" and nothing else. An analyst asked where that came from and had to go and find out. Now
the page says which source counted them and when it was read, and offers the full history of
that field. This matters most in the moment a customer disagrees with a figure.

**The spreadsheet used to win forever.** The SOC Automation vendor list was imported from a
workbook in April. Every list, filter and page has read those values ever since, and readings
collected afterwards went into a table nothing displayed. Fifteen vendors currently have a
better, more recent headcount than the imported one — 7ai is 145 rather than 122, exaforce is
128 rather than 102. Turning this on shows those instead.

**Zero was being reported as a fact.** Seven vendors had a blank headcount cell in the original
workbook, which the system stored as `0` and filters treated as a real number. A search for
"vendors with fewer than ten staff" returned 24 companies; seven of them were companies whose
headcount we simply never learned. It now returns 17, and those seven show as unknown.

**One post, two vendors, one opinion.** A post comparing two SOC vendors used to carry a single
relevance and sentiment score shared between them. Whichever vendor was assessed second
inherited the first one's verdict. Each vendor now gets its own.

**A vendor praising itself was counted as praise.** Vendor LinkedIn posts sat in the same feed as
independent commentary and fed the same sentiment totals. For one vendor in the current data
that is 65 of its own posts against 5 external mentions. Those 65 are still visible — an analyst
wants to see what a vendor is claiming — but they no longer move the sentiment figure.

**Silence is reported as a gap, not as a finding.** Where nothing has been collected about a
company, the page now says that no coverage was collected rather than implying nobody discussed
it. Where mentions have been found but not yet assessed, they are counted separately instead of
being treated as neutral opinion.

## Release notes (copy-ready)

- Vendor facts now show their source and the date they were read, with full history per field.
- Newer sources can now update vendor details that previously stayed fixed at their imported value.
- Missing headcounts now show as unknown instead of zero, so filters no longer match on them.
- Social posts mentioning several vendors are now rated separately for each vendor.
- Vendor's own posts are labelled as their claims and excluded from sentiment scoring.
- Vendor timeline entries show whether an event is the vendor's announcement or independently
  confirmed.
- Market RSS feeds now carry the Aunoo logo.

## Demo / walkthrough

Market Monitor → a market → click any vendor. The new **Current profile** panel sits above the
existing charts and lists each fact with the source and date beneath it. Where the imported
workbook still disagrees, the old value appears alongside as "import said 122".

Below it, **Events** shows the vendor's timeline with a marker per entry saying whether it is the
vendor's own claim or independently corroborated, and **Coverage** splits the vendor's own posts
from external mentions with an explicit count of what has and has not been assessed.

The existing headcount chart and funding panel are unchanged.

## Positioning notes

The gap this closes is a credibility one. Competitive intelligence products are routinely
challenged on individual figures, and the usual answer is a refresh date on the whole record
rather than a source per field. Being able to say "LinkedIn company profile, 20 August, and here
is what it said before" is a different conversation from "the data is from August".

It also removes a specific embarrassment: a page confidently displaying a headcount of zero for a
funded company because a spreadsheet cell was blank.

## Limits and what's next

**Nothing is live.** The flags are off and the code is not deployed. Enabling it is a deliberate
step, and it changes visible results — filter counts move, and one vendor's country changes.

**Twine Security moves from Israel to the United States** when this is turned on, because a
LinkedIn reading outranks the workbook. That is the intended mechanism, and it is a real
assertion about a company that should be checked by someone who knows before it is shown to
customers.

**Two vendors are missing their funding totals.** Intezer and Prophet Security lost hand-entered
figures during this work (a database mistake, documented in the engineering log). The sources are
known and recorded in a review task; restoring them needs an analyst to decide the total, because
the sources cite individual rounds rather than a total.

**Sentiment coverage is thin.** Only a handful of external mentions have been assessed so far, so
sentiment figures will show as unavailable for most vendors rather than wrong. Widening that
means running the assessment step over the backlog, which costs model calls.

**Generated summaries are not turned on.** The checking machinery is built and tested, but the
step that writes the prose is deliberately disabled. Only the underlying facts are exposed.

**Two timeline sources are not running.** News coverage and social conversation spikes both need
inputs that are not reliable yet — the first needs relevance scoring, the second needs enough
history to know what a normal volume looks like. Both are registered and switched off rather than
producing weak output.
