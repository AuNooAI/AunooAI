# The shared market link is now a briefing, not a database report
_27 August 2026 · Market Monitor — the link an operator sends to somebody outside_

## What shipped

- The sharing link opens on a one-screen market briefing. The detail behind it is still
  there, folded into three sections a reader opens if they want it.
- Stories say where they came from in plain words: "the company's own announcement" or
  "the company's claim, nobody else has said it".
- Every story links to the records behind it, not just one.
- Readers can switch the reporting period between 7, 30 and 90 days, change how dense the
  news list is, and subscribe to the market as a feed.
- A sidebar shows who moved this period and what people outside these companies are
  saying, quoted.

## Why it matters

**The reader is not the person who runs Aunoo.** They are whoever the operator sends the
link to — a buyer comparing suppliers, an analyst covering the category, an investor
watching it. Before, they landed on a page written for an operator: fourteen sections of
tables, and language like "no comparable prior-period reading" and "partly collected".
Now they land on a briefing and can open the tables if they want to check something.

**A company announcing its own product is not missing evidence.** Every story used to say
"the vendor announced it; no independent source", which reads as a hole in what we know.
It is not a hole — nobody outside a company can confirm that the company shipped
something. That wording sat on 138 of this market's 198 events. It now separates two
genuinely different things: a company stating a fact about itself, which is the record,
and a company making a claim about a customer or an investor who has not spoken yet, which
is one side of a story.

**A short bar was reading as a collapse.** The last bar on the weekly coverage chart
showed 41 against about 170 for a full week, because the week was three and a half days
old. Those bars are now hatched and say so, so nobody reads a partial week as a downturn.

**Our internal notes were reaching customers.** The report printed collection engineering
notes verbatim, including one about a data provider's API that mentioned internal field
names. A reader outside the company cannot act on any of that. Those now have a plain
reader-facing version, and job-collection caveats moved off the briefing entirely.

## Release notes (copy-ready)

- The shared market report now opens as a briefing, with the full analysis, vendor list and
  methodology available in three expandable sections.
- Stories show where each one came from and link to every supporting record.
- Reporting period can be switched between 7, 30 and 90 days from the page itself.
- Market news can be read at three densities, and each market is available as a feed.
- Weekly coverage bars that are still filling are marked, so a partial week is not mistaken
  for a decline.
- A company's own announcement about itself is now treated as the record for that fact,
  rather than as an uncorroborated claim.

## Demo / walkthrough

Market Monitor → a market → **Share** → open the link. The briefing is the whole first
screen. Click **Top News / Headlines / River** to change density, **7 / 30 / 90 days** to
change the period, or **RSS** to subscribe. The three sections at the foot — the analysis,
the vendors, the method — hold everything that used to be printed inline.

## Positioning notes

The objection this closes is "your tool tells me what it collected, not what happened".
The briefing answers the second question and keeps the first one one click away. The
evidence wording is the differentiator worth naming in a demo: most competing tools present
a vendor press release and an independent report as the same kind of fact, and this one
does not.

## Limits and what's next

- **No funding movement.** Our funding source gives us each company's stage, not the size or
  date of individual rounds, so the briefing cannot say "$163M was raised this month" or
  name the largest raise. That needs a different data source.
- **No change in open roles.** Most companies have been checked once, so we can report how
  many roles are open but not how many are new. This fills in on its own as checks
  accumulate.
- **Staff numbers are a floor.** Companies that publish a size range instead of a number are
  left out rather than guessed at.
- **Most findings have one source**, so the "More" list usually shows one link. That is the
  state of the market's coverage, not a limit of the page.
- **A vendor's own name still prefixes some headlines** where we could not attach the story
  to a company record. It reads awkwardly and is a change to how stories are extracted, not
  to the page.
