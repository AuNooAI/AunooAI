# aisocnews.com as a public site: Submit news, About and privacy, one contact form, the Aunoo look
_2026-08-29 · Market Monitor front page at aisocnews.com and aisoc.aunoo.ai (and its section pages, river and Analyst View)_

## What shipped

- **Submit news.** A button in the top bar. A reader sends us a link to a story we missed, with an optional note and email. The editors get it by email at once.
- **About and Privacy.** Linked from every footer. What the site is and who makes it, how the material is collected and sorted, the AI disclosure, a privacy notice, a disclaimer, and the imprint: Cyberfuturists is the trading name of Oliver Rochford Ltd, company 14480528, with its registered office.
- **One contact form.** The three forms at the foot of the page (news tip, missing vendor, trial) are one "Get in touch" form with a dropdown for what it is about.
- **The Aunoo look.** The pages use the same type and colours as the Aunoo product: DM Sans, the pink accent, the mauve greys, the same dark ground.
- **Smaller changes.** "By the numbers" moved to the bottom of the sidebar. Blurred blocks in the shared view say "Want more data?" with a "Get the full report" button. The Analysis section no longer shows when nothing is published. The Market Maturity Map caption says vendors are "mapped", not "placed".
- **During a restart** the site shows a "Back in a moment" page that reloads itself, instead of an error.

## Why it matters

The page went public under its own name this morning and had 8 or 9 real visitors by the evening, three of whom landed in a restart window and saw a raw error page. It also had no way for a reader to reach us, no statement of who runs it or what happens to a visitor's data, and a look of its own that did not match the product it is made with. Each of those is now closed:

- A reader who knows a story we missed can send it in two fields. The editors read every tip; what goes on the page stays our call, and the page says so.
- Anyone can see who publishes the site, that AI models do the sorting and summarising under human rules, what we keep about a visitor (a server log for 14 days, and what they type into a form), and whom to write to. That is what a public site needs to say, and it is what the EU AI Act asks for.
- The three stacked forms read as clutter; one form with a dropdown reads as one thing to do.
- A visitor who lands in the 10–15 seconds of a restart now sees a page that says so and reloads itself.

## Release notes (copy-ready)

- New: a Submit news button. Send us a link to a story about the market that is not on the page.
- New: an About page, linked from the footer, with how the site is made, the AI disclosure, a privacy notice and the imprint.
- Changed: one contact form at the foot of the page, with a dropdown for news tips, missing vendors and trial requests.
- Changed: the site now uses the Aunoo type and colours.
- Changed: "By the numbers" sits at the bottom of the sidebar; blurred blocks ask "Want more data?".
- Fixed: no empty Analysis section; no error page during a restart.

## Demo / walkthrough

- https://aisocnews.com/ — "Submit news" top right; "About · Privacy" in the footer.
- https://aisocnews.com/?view=v2&page=about — the About page.
- Foot of the front page — "Get in touch", pick what it is about from the dropdown.

## Positioning notes

The public page is now a complete site rather than a report with a domain: it says who stands behind it, how it is made, and how to reach the editors. The imprint and privacy notice are what a European reader expects to find before trusting a source. Matching the product's look ties the page to Aunoo for anyone who arrives from the product.

## Limits and what's next

- A news tip is a record for the editors, not an article. Nothing enters the page until someone reads the link. Landing tips automatically into the river is a follow-on.
- The About page's privacy notice describes the site as it is today: no cookies, no analytics. Adding analytics later means updating that notice first.
- The look matches what saas.aunoo.ai serves today. If the product's planned reskin ships, the page follows it through the same set of colour tokens.
- Counting visitors per site is possible from today's log lines on; earlier days cannot be split between aisocnews.com and aisoc.aunoo.ai.
