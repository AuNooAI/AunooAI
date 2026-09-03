# Newsletters built from approved articles only, a stricter gate for market topics, and a Consensus tab that survives a cut-off answer
_2026-09-03 · Auspex Newsletter Generator, article relevance gate on Market Monitoring topics, Trend Convergence Consensus tab_

## What shipped
- The newsletter generator only uses articles the relevance gate approved. It no longer
  reads the whole pile of collected material, most of which the gate had already rejected.
- The newsletter's "deep dive" picks its subject by real source quality. A press-release
  site no longer counts as NPR because its domain contains the letters "npr".
- The instruction text "USE THE PRE-GENERATED ANALYSIS" no longer appears in newsletters.
- Newsletters keep articles collected this week even when the story was first published
  earlier, and the deep dive sits under its own heading instead of starting a new title
  in the middle of the page.
- On Market Monitoring topics, the AI relevance auditor now checks every article. The
  fast classifier can no longer wave through a war report because it read like news.
- The Consensus tab no longer crashes when the AI's answer was cut off before it finished.

## Why it matters
**Newsletter content.** Before, a newsletter for the SOC Automation market topic on the
bugfixing site opened with agentic SOC coverage and then wandered through gaming, car
auctions, museum heists and a section of market-size press releases. The generator was
reading 1,177 articles labelled with the topic, and 1,334 of that week's 1,658 labelled
articles were ones the relevance gate had already rejected. Now it reads only approved
articles: 135 for the same topic and week, producing 8 sections instead of 24, all of
them about security operations or the AI risk stories around it. An analyst who asks
Auspex for a newsletter gets one about the topic they chose.

**Deep dive choice.** The deep dive is meant to land on the section with the strongest
sources. The source check matched fragments of names, so "openpr.com" scored as NPR and
"app.com.pk" as AP, and seven OpenPR press releases beat the real story. Names are now
matched as whole domain labels. In the rerun the deep dive landed on the accountability
gap in autonomous security operations, sourced from practitioner and trade press.

**Prompt leak.** The writing prompt told the model to copy the pre-written analysis into
the deep dive. Some models copied the instruction as well. The analysis now goes straight
into the template under its own heading, so there is nothing to copy.

**Market-topic relevance.** Before, 25 of the 140 approved articles in the SOC Automation
topic that week were Iran, Hormuz, Ukraine and Gaza coverage. Vendor names such as
"PRE Security" and "Command Zero" matched any article containing those common words, and
the gate then trusted a fast classifier that was trained on theme topics like
Geopolitical Hotspots and had never seen a market topic. It rated the war reports as
relevant with near certainty and skipped the AI auditor. Now market topics always go to
the auditor, which is told which market and which vendors it is judging for. A re-run over
that week rejected 30 articles: all 25 geopolitics pieces and five strays, and kept 110,
including every vendor and practitioner piece. Those 30 were re-gated the same day.

**Consensus tab.** A Patent Cliffs consensus run on the wileytest site came back cut off.
The recovery step closed the half-written answer, one category arrived without its
confidence block, and the page reading it crashed with a blank tab. Two things changed:
the server now drops any half-written category before it reaches the page, and the page
itself tolerates missing sections. The cut-off happened because that site still capped
this model at 4k output tokens; it now has the same 64k cap as the other sites.

Who feels it: analysts using Auspex newsletters and the Consensus tab, and anyone reading
a Market Monitoring topic's approved feed, alerts or reports.

## Release notes (copy-ready)
- Auspex newsletters are built only from articles that passed the relevance check.
- The newsletter deep dive picks its subject from genuine high-quality sources.
- Removed stray instruction text that could appear above the newsletter deep dive.
- Newsletters include articles collected this week regardless of original publish date.
- Market Monitoring topics: every article is now checked by the AI relevance auditor,
  which removes unrelated news that shares a word with a vendor name.
- Trend Convergence: the Consensus tab handles an incomplete AI answer instead of going blank.

## Demo / walkthrough
On bugfixing, open Explore, pick the "Market Monitoring SOC Automation" topic, open Auspex
and choose Newsletter Generator. The result has eight sections and a deep dive under
"The Deep Dive — …". Chat sessions 296 and 297 in Auspex hold the two verification runs.
On wileytest, open Trend Convergence for Patent Cliffs and the Consensus tab; the cached
run from 3 September shows its second category with an empty confidence block rather
than a blank tab.

## Positioning notes
This closes the most visible objection to the newsletter feature, that it read like a
general news digest rather than a topic brief. It also makes the Market Monitoring
product's approved feed trustworthy enough to drive reports and alerts, which the market
report pipeline relies on.

## Limits and what's next
- Social posts are not "approved" articles, so they are no longer in newsletters. Turning
  them back on is a one-line change if wanted.
- Cached consensus runs are served as stored. The Patent Cliffs run keeps its half
  category until its 24-hour cache expires.
- The SOC Automation keyword list still contains the vendor names that match common
  words. The gate now rejects what they bring in, but each rejection costs an AI call.
  Quoting or dropping "System Two Security", "PRE Security", "Command Zero" and
  "AI security operations" would cut most of the noise before the gate.
- On other topics the fast classifier still skips the auditor when it is confident. Any
  new topic family that is not a trained theme will need the same exemption.
