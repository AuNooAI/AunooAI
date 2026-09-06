# The front page says what the market is talking about, and readers can book a paid call with the analyst
_2026-09-06 · aisocnews.com — the public AI-in-the-SOC market page, its topic pages, and a new booking page_

## What shipped

- **The first analysis piece**, drafted for approval: "The agentic SOC is
  a feature now. What that leaves for the specialists." It reads the
  month's coverage through two of our own reports and sets them against
  our vendor tracking.
- **Two public reports.** The Consensus analysis (where the coverage
  agrees, where it splits, with every source cited) and the Three
  Horizons scan (what is happening now, next, and later) are pages of the
  site, linked from the footer. Each keeps its earlier runs, so a reader
  can open September's reading in December and see what held.
- **Tracking over time.** The market is enrolled in the Forecast Tracker:
  the horizons scan is the forecast, and once a month the tracker re-reads
  the coverage and scores each scenario against the events that followed.

- **"What the market is talking about."** A new card in the sidebar with two
  short lists. "Being discussed" names the five subjects with the most
  coverage in the last seven days. "Emerging" names the subjects whose
  coverage is bunched into this week compared with the last month, each
  with a multiplier showing how far above the month's pace it is. Every
  subject links to a page listing its articles.
- **Schedule an inquiry.** A button in the top bar, a line in the contact
  form and a short link at aisocnews.com/inquiry lead to a page where a
  reader books a 30 minute ($250) or 60 minute ($450) call with Oliver
  about a vendor or the market. They pay by card on Stripe's page, then
  pick a time from a Google Calendar booking page. This part is built and
  tested but is switched off until three settings are filled in (see the
  last section), so readers do not see it yet.

## Why it matters

**Before, the page told you what happened; now it also tells you what
people are talking about.** The developments list is a stream of events. A
reader who wants to know what the conversation is this week had to read
the whole river and work it out. The card does that once a day: on 6 Sep
it names Fal.Con 2026, the 7AI funding round and CrowdStrike's agentic SOC
announcements as the week's subjects, and shows CrowdStrike's launch
coverage running at about twice the month's pace. Each name is a page of
the articles behind it, so the claim is checkable in one click.

**The subjects come from the headlines, not from a fixed list.** Once a
day we hand a model the month's headlines and ask it to group the ones
that are about the same specific thing, an event, a launch, a report, a
deal, and to name each group from those headlines only. It cannot add a
company or an event the headlines do not contain, and it leaves out the
chatter, job adverts and stock-ticker posts rather than forcing them into
a group. The first version grouped by machine similarity instead, and the
operator caught it: one "subject" mixed OpenAI's GPT-6 Astra, an award, an
Air Force contract and a sales job. That approach is gone.

**A reader with a question now has somewhere to take it.** Until today the
only way to reach Oliver from the site was the contact form. A paid call is
a clearer offer for a buyer weighing a shortlist or a vendor checking a
claim: a price, a length, a card payment and a calendar slot, with a
confirmation mail and a Stripe invoice.

## Release notes (copy-ready)

- New: "What the market is talking about" in the sidebar, with "Being
  discussed" and "Emerging" lists, refreshed daily. Click any subject for
  its articles.
- New (pending activation): "Schedule an inquiry" — book and pay for a 30
  or 60 minute analyst call, then choose a time on the calendar.
- The About page's privacy notice now covers what happens to your details
  when you book a call.

## Demo / walkthrough

- https://aisocnews.com/ — sidebar, second card, under the Market Maturity
  Map. Click a subject name.
- https://aisocnews.com/?view=v2&topic=1 — one subject as a page.
- https://aisocnews.com/inquiry — the booking page. Shows "Booking is not
  available right now" until it is configured.
- https://aisocnews.com/?view=v2&page=about — "Booking a call" under
  Privacy.

## Positioning notes

The subjects card makes the page read like a briefing rather than a feed.
It is also the first thing on the site that says "this is rising", which
is the question an analyst gets asked most. The paid call turns the page
from a free reference into the front door of an advisory practice, priced
per conversation rather than per subscription.

## Limits and what's next

- The analysis piece is a draft until Oliver approves it. Its consensus
  figures describe one week of coverage (3 to 5 September), and the piece
  says so.
- The reports name vendors from the coverage, including vendors outside
  the free roster, the same way the editorial pieces do. That is a
  decision, not an oversight.
- The first tracker assessment is a baseline; the "is this bearing out"
  reading needs the second month's run.

- The subjects are recomputed from scratch every day. Yesterday's list and
  today's are not linked, so there is no "still rising since Tuesday"; the
  rise is measured inside each day's own month of coverage. That is
  deliberate for now.
- The model's idea of what counts as a subject varies from call to call.
  We take two samples a day and keep the fuller one, but a small subject
  with three articles, such as the 7AI funding round, can appear one day
  and be missing the next. Expect the top two or three to be stable and
  the tail to move.
- In the public view a subject is dropped when its name or sentence
  mentions a vendor outside the free view, and the list is topped up from
  the next subject down. A subject's page says how many of its articles
  are not shown for that reason.
- "Emerging" only lists subjects that are not already in "Being
  discussed"; when every rising subject is also a most-discussed one, the
  rise shows as a marker on that row and the Emerging list is left out.
- The booking flow is off until the two Google Calendar booking links are
  set; Stripe is fully configured and was exercised with one live session
  that was expired without a charge. One real purchase and refund should
  follow before the button goes public.
- No sales tax or VAT is collected on the call price. That is a decision
  for the operator, not a gap in the code.
- Marking a call as booked or refunded is done by hand in the database;
  there is no admin screen yet.
