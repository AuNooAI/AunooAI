# aisocnews.com gets its design system, and a dark mode
_2026-09-08 · aisocnews.com: front page, section pages, analysis pieces, Analyst View, news river, Consensus, Three horizons, briefing and booking pages_

## What shipped
- Every page on aisocnews.com now follows one written design system: the same type, colours, spacing and controls throughout.
- A light and dark theme, switched with one button in the top bar. The choice is remembered on that device.
- Reading text (story summaries, quotes, analysis pieces) is set in a serif; headlines, labels and numbers stay in the sans. A reader can tell a claim from a measurement at a glance.
- Each section keeps its own colour on the box cap, the title and the story badges: Market moves, Product launches, Hiring, Case studies, Thought leadership, Social, Research firms.
- Where a story came from is shown in its own bounded strip under the headline, rather than as grey run-on text.
- The Analyst View's evidence, vendor list and method now sit inside the page as boxes you open, instead of as separate white cards floating below it.
- Web addresses typed into the contact form are tidied up automatically. `example.com` becomes `https://example.com`.

## Why it matters
Before, the site had grown page by page. The front page, the Analyst View and the river each had their own spacing, button styles and heading treatments, and the two standing reports (Consensus, Three horizons) used a different accent colour from the rest of the site. There was no dark option.

Now one spec, `aunoo-aisocnews-design-system.md`, governs every page, and the site's stylesheet is the spec's values written out. A reader moving from the front page to a section page to the Analyst View sees the same shell, the same controls and the same reading type. Anyone extending the site has a document to work from rather than a page to copy.

Who feels it:
- **Readers** get a calmer page, a dark theme for evening reading, and clearer sourcing on every story.
- **Cyberfuturists** get a consistent, recognisable surface for the publication, and a written standard for future pages.
- **Anyone maintaining the site** changes a value once in the token layer and every page follows.

## Release notes (copy-ready)
- New design across aisocnews.com: one type scale, one colour system, one set of controls on every page.
- Light and dark themes, switched from the top bar. Your choice is remembered in your browser.
- Story summaries, quotes and analysis pieces are now set in a reading serif; headlines, labels and figures stay in the sans.
- Each section carries its own colour on the cap, the title and the story badges.
- Sourcing sits in its own strip under each story.
- The Analyst View's evidence, tracked vendors and method are boxes inside the page.
- Web addresses typed into the contact form are completed for you.

## Demo / walkthrough
1. Open https://aisocnews.com/. The page ground is dark, the content sits on one light panel.
2. Click the sun or moon icon at the right of the top bar. The whole page switches theme, including the Market Maturity Map and the charts. Reload: the choice sticks.
3. Scroll to any section box. The 2px cap, the title and the small story badges share that section's colour. Under each headline, the grey "Source" strip shows where the story came from.
4. Open Analyst View from the top bar. Scroll past the developments to "Evidence", "Tracked vendors" and "How this was measured". Each opens in place as a box on the same panel.
5. Open Consensus or Three horizons from the section row. The report body follows the same colours and the same theme toggle.
6. Open News river. The day groups sit in one box under the masthead, with the same period selector as the front page.

## Positioning notes
This is presentation, not a new capability. It matters for the publication story: aisocnews.com is meant to read as an edited news front page with visible sourcing, and the design now carries that argument consistently. The provenance strip and the section colours are the visible form of "every claim shows where it came from", which is what sets the site apart from a vendor-written feed.

## Limits and what's next
- Only aisocnews.com is affected. The Aunoo product screens, the Brand Watcher sites and the emailed reports keep their existing look.
- One filled button per view is a deliberate rule from the spec. On the front page that button is Submit news. "Schedule an inquiry", "Request a trial" and "Get the full report" are now links, not buttons. If the paid call needs more prominence, that is a design decision to make against the spec, not a bug.
- The Three horizons chart keeps its own pink and green gradient. It is drawn by a shared report renderer and was left alone.
- Heading text was not changed. Some card titles are still in title case ("Market Maturity Map", "Influence and Influencers") although the spec asks for sentence case.
- The theme choice is stored per browser. Nothing is stored on the server.
- The design-system document still lists "theme choice doesn't persist" as a known gap. It now persists on the live site; the doc needs that line updated.
- The signed-in full-briefing page is styled but was not checked visually in this release, because the check ran without a login.
