# The Findings page now says what changed, not what we collected
_2026-08-26 · Market Monitor — Findings_

## What shipped

- Findings are grouped into six themes: funding and ownership, product and launches, customers and partnerships, hiring and headcount, leadership and strategy, attention and narrative.
- The top of the page holds up to five findings that deserve attention now, rather than the newest five records.
- Each finding says how much it matters and **why it was rated that way**, in a clause you can read.
- Each finding says how many independent sources back it, and links to every one of them.
- A change announced only by the company itself is labelled a watch item, not a confirmed finding.
- Where nobody established when something happened, the page says "date not established" instead of showing the day we noticed it.
- An empty page now tells you which kind of empty it is.

## Why it matters

**A list of posts cannot tell you what changed.** The page showed collected posts and articles, newest first. That answers "what did the system pick up", which is a different question from "what happened in this market". A post is evidence. A finding is a conclusion with its evidence attached, and the two were being shown as the same thing.

Findings are now grouped by theme and ordered by rules you can see: newest first *within* materiality, materiality before recency, and better-evidenced findings ahead of thinner ones. No hidden relevance score.

**Nothing in this market is confirmed by anyone but the vendor, and the page now says so.** All 194 tracked changes rest on a single source, and 193 of those are the company's own announcement. That is a real and useful fact about the market — it means almost nothing here has been independently reported — and the page states it in a line rather than letting a reader assume otherwise.

Each finding carries its source count, and clicking through shows every record with whose voice it is: the company's own channel, an independent publisher, or a primary document. Where every source is the company itself, the drill-down says that in plain words.

**Materiality is a rule, shown, not a score.** A funding round or an acquisition is high — money or ownership changed hands. A partnership is medium, or high if it touches several monitored companies at once. Hiring is deliberately low, because every growing company is always hiring, so a job advert on its own says very little. The reason appears next to the rating, so you can disagree with it.

**"News page changed" is no longer a product launch.** One check found the page's own executive summary led with "Andesite: news page changed" — twelve words different on a news index, with no date — rated as a medium-importance product launch. Something changed on a page and we do not know what. Those are now rated as the weakest thing we collect, and they dropped out of the summary.

**An empty page tells you why it is empty.** Four different reasons, and they are not the same: collection has not finished; evidence is collected but nothing has read it yet; collection succeeded and genuinely nothing met the bar; or there are only watch items. The second one used to read as "no findings", which is the same mistake as reporting a zero from a collector that never ran.

## Release notes (copy-ready)

- Findings are now grouped into six themes and ordered by explicit rules rather than a relevance score.
- The page leads with up to five findings that warrant attention, excluding dismissed items and low-importance watch items.
- Every finding shows its importance rating with the reason for it, its independent source count, and a link to all its evidence.
- A change announced only by the company is shown as a watch item. The page states when nothing in the period is independently corroborated.
- Findings with no established event date say so, and show the first-observed date separately rather than in its place.
- Evidence links show whose voice each record is: the company's own channel, an independent publisher, or a primary document.
- Empty states distinguish incomplete collection, evidence awaiting review, and a genuine absence of findings.
- Website-change records are rated as the weakest signal rather than as product launches.

## Demo / walkthrough

Market Monitor → SOC Automation → Findings. The top section holds five findings; each shows theme, status, importance and the reason for it. Click a finding's evidence count to see every backing record and whose voice it is.

Filter by theme, importance, status or company; change the sort between Recommended, Newest event, Recently observed, Highest confidence and Company A–Z. Everything downloads as a spreadsheet.

## Positioning notes

The honest headline is a limitation, and it is worth leading with: nothing in this market has been independently reported. Almost every tracked change is a company talking about itself. That is not a shortcoming of the product — it is what the market looks like — and a tool that presents self-announcements as confirmed findings is the one to distrust.

## Limits and what's next

**We cannot yet build findings from news coverage.** That is the missing piece for "three articles about one funding round become one finding". The blocker is the data: of 22 third-party items on record for these companies, only **three** are genuinely from someone else — 11 are one vendor's own blog and 7 are employer reviews. There is no independently covered event to find.

We deliberately did not build it anyway. A vendor's own blog was being treated as an independent publisher, so a company's blog post plus its LinkedIn post about the same launch would have been presented as two sources agreeing — inventing exactly the false consensus this product exists to spot. The independence rule is fixed; the extractor waits for real coverage to exist.

**Some headlines are still the opening line of a post.** Where no sentence in an announcement clearly states the news, the finding keeps the post's opening line. That is deliberate — a guessed headline is worse than a dull one — but it reads poorly.

**Nobody has reviewed any of these findings.** Every one is machine-derived. The review state is recorded and currently reads "unreviewed" throughout.

**"New in this period", not "new since you last looked."** There is no per-person record of what you have already seen, so the page does not claim there is.

**Separately: earned coverage counts vendor blogs as third-party.** The attention figures shipped earlier today treat a company's own blog as somebody else covering it, which overstates them. Flagged, not yet changed.
