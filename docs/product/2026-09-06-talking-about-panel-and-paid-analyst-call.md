# The front page says what the market is talking about, readers can book a paid call, and the consensus and horizons reports are public pages
_2026-09-06 · aisocnews.com — the public AI-in-the-SOC market page, its report pages, and the booking page_

## What shipped

- **"What the market is talking about."** A new card in the sidebar. "Being
  discussed" names the subjects with the most coverage in the last seven
  days. "Emerging" names the subjects whose coverage is bunched into this
  week compared with the last month, each with a multiplier. Every
  subject links to a page of its articles.
- **Consensus and Three Horizons as pages of the site.** The consensus
  analysis (where the coverage agrees, where it splits, every source
  cited, categories folded so you scan four headlines) and the three
  horizons scan (now, next, later) sit in the section menu after
  Research firms. Each keeps its earlier runs, so September's reading
  stays readable in December.
- **Tracking over time.** The market is enrolled in the Forecast Tracker:
  the horizons scan is the forecast, and once a month the tracker
  re-reads the coverage and scores each scenario against what happened.
- **Schedule an inquiry.** A button in the top bar, a line in the contact
  form and a short link at aisocnews.com/inquiry lead to a page where a
  reader books a 30 minute ($250) or 60 minute ($450) call with Oliver.
  They pay by card on Stripe's page, then pick a time on a Google
  Calendar booking page.
- **Smaller changes.** "Latest research" is now "Research firms". Every
  analysis piece carries the site's standard AI disclosure at its foot.

## What was published and withdrawn

The site's first analysis piece went live in the evening and was pulled
within the hour. Three of its fourteen citations pointed at the wrong
article or claimed more than the article said, and the prose read as
machine-written despite five rewrites. It is not on the site. A guard now
reads every citation in a piece against its source before the piece can
be approved, and refuses approval while one does not hold. The next piece
goes out only after a person has read every source.

## Why it matters

**The page told you what happened; now it also tells you what people are
talking about.** The developments list is a stream of events. The card
does the summing up once a day: on 6 September it named the CrowdStrike
agentic SOC launch (21 of its 25 articles this week, 2.7 times the
month's pace), Prophet Security's evaluation content, TryHackMe's SOC
training and OpenAI's GPT-6 Astra. Each name is a page of the articles
behind it, so the claim is checkable in one click.

**The subjects come from the headlines, not from a fixed list.** Once a
day we hand a model the month's headlines and ask it to group the ones
about the same specific thing and name each group from those headlines
only. It cannot add a company or an event the headlines do not contain.
The first version grouped by machine similarity instead and put GPT-6
Astra, an award, an Air Force contract and a sales job in one "subject";
that approach is gone.

**The reports are the same ones the analyst sees.** Until today the
consensus and horizons analyses were operator downloads. Now they are
pages a reader can open, in the site's own type and colours, with every
run kept. A skeptical reader can check what the coverage agreed on and
which sources said it.

**A reader with a question has somewhere to take it.** A paid call is a
clearer offer than a contact form for a buyer weighing a shortlist: a
price, a length, a card payment and a calendar slot, with a confirmation
mail and a Stripe invoice.

## Release notes (copy-ready)

- New: "What the market is talking about" in the sidebar, with "Being
  discussed" and "Emerging" lists, refreshed daily. Click any subject for
  its articles.
- New: the Consensus analysis and Three Horizons scan are pages of the
  site, in the section menu, with earlier runs kept.
- New: "Schedule an inquiry": book and pay for a 30 or 60 minute analyst
  call, then choose a time on the calendar.
- Changed: "Latest research" is now "Research firms".
- Changed: analysis pieces carry the site's AI disclosure at the foot.

## Demo / walkthrough

- https://aisocnews.com/ — sidebar, second card, under the Market
  Maturity Map. Click a subject name.
- https://aisocnews.com/?view=v2&page=consensus — categories fold to
  their headline; "Expand all categories" opens them.
- https://aisocnews.com/?view=v2&page=horizons — the S-curve, the
  scenarios and the executive-summary cards; earlier runs in the bar.
- https://aisocnews.com/inquiry — the booking page.

## Positioning notes

The subjects card makes the page read like a briefing rather than a
feed, and it is the first thing on the site that says "this is rising".
The public reports show the working behind the front page. The paid call
turns the page from a free reference into the front door of an advisory
practice, priced per conversation rather than per subscription.

## Limits and what's next

- There is no analysis piece on the site. The withdrawn one stays as a
  draft in the database with its revisions; a replacement needs a person
  to open every source and to write, not rewrite, the prose.
- The subjects are recomputed from scratch every day and are not linked
  across days; the rise is measured inside each day's own month of
  coverage. The model's idea of a subject varies from run to run: we take
  two samples a day and keep the fuller one, but a small subject can
  appear one day and be missing the next.
- The consensus and horizons runs read the newest 90 records, which on
  6 September were all from 3 to 5 September, so the first runs describe
  Fal.Con week rather than the month. The monthly refresh will widen that.
- The first tracker assessment is a baseline with no post-forecast
  evidence yet; the "is this bearing out" reading arrives with the
  second month's run.
- The booking flow is live but Stripe's own webhook delivery is unproven
  until the first sale; the flow was verified with a signed synthetic
  event. No sales tax or VAT is collected, which is the operator's
  decision. Marking a call booked or refunded is done by hand.
