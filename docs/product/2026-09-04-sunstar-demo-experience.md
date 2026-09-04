# The Sunstar workspace is ready for its first customer login
_2026-09-04 · sunstar.aunoo.ai — brand feed accuracy, page speed, research assistant, user access_

## What shipped
- The Sunstar brand feed no longer shows the wrong Sunstars. Posts about a
  Delhi hotel chain, a Turkish beach resort, a Japanese stationery maker and
  Philippine newspapers — all named Sunstar — were crowding the feed. The AI
  that scores social posts now knows which company Sunstar is, and a blocklist
  catches the known look-alikes before any AI is involved.
- Analysis pages open instantly. The Narratives and Highlights views used to
  spend up to two minutes re-running AI analysis on every first visit of the
  day; they now show the saved analysis immediately, and the Generate button
  refreshes on demand. The Anticipate tabs are being pre-filled the same way,
  so every tab shows finished analysis instead of an empty "generate" screen.
- The research assistant speaks Sunstar's language. A "Sunstar Strategic
  Analyst" mode reads every question through the company's own frame: where
  the science on oral health and whole-body health actually stands, what
  competitors claim beyond their evidence, and how the four key markets
  differ. It also knows not to pitch tooth regeneration, which the customer
  has said is not relevant to them.
- The customer contact has his own login. First sign-in asks him to set his
  own password, then lands him on the configured dashboard — no setup wizard,
  no empty screens.

## Why it matters
A prospect's first unaccompanied login is the product demo they give
themselves. Before this work, that login risked a feed of hotel promotions
under the brand's name, a two-minute spinner on the analysis pages, and a
generic AI assistant. Now the feed is clean (checked by hand: the surviving
posts are the company's own campaigns, product launches and executives), the
pages open at once, and the assistant answers like an analyst who was briefed.

## Release notes (copy-ready)
- Fixed: social posts about unrelated companies sharing a brand's name no
  longer appear in the brand feed. The AI scoring now uses the brand's
  description, and known look-alikes are filtered outright.
- Improved: the Narratives, Highlights and Anticipate views load saved
  analysis instantly instead of regenerating it on every visit. Generating a
  fresh analysis remains one click.
- Improved: the research assistant offers a company-specific analyst mode
  that frames answers around the customer's strategic questions.

## Demo / walkthrough
Log in as the customer contact: the password-change page, then the dashboard.
Open Explore → Narratives (instant), Anticipate → any tab (instant, cached),
and the Auspex assistant → prompt picker → "Sunstar Strategic Analyst".

## Positioning notes
None beyond readiness: this is the difference between "demo went well" and
"the customer poked around alone and it held up".

## Limits and what's next
The look-alike filter and analyst prompt are per-customer configuration —
each new customer site needs its own version of both (a few minutes of setup
each). The instant-loading fix is code and reaches other customer sites as it
propagates; the pre-filled analyses are per-site and regenerate on their own
schedules after this first fill.
