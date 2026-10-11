# Vendors appear in their own brand colours
_1 October 2026 · Market Monitor and Brand Watcher on the demo site (bugfixing)_

## What shipped
- Each of the 49 vendors we track in the "AI in the SOC" market now has its own brand colour.
- Market Monitor charts draw each vendor in that colour, and vendor names in lists and tables
  carry a small dot of it.
- Brand Watcher's brand list, comparison charts and reports use the same colours.

## Why it matters
**Before:** no vendor had a colour. Brand Watcher drew every vendor in the same grey, so a
you-versus-competitor chart showed two grey bars. Market Monitor used one fixed colour for all
vendors in a chart, so a share-of-voice bar chart was a column of identical bars.

**Now:** a reader can follow a vendor across views by its colour. Torq is teal on the
share-of-voice chart, in the "most active" table and in the public report, and the colour is
the one Torq uses on its own website. Analysts and buyers who know these vendors spot them
faster.

## Release notes (copy-ready)
- Market Monitor shows each vendor in its own brand colour, in charts, tables and the shared
  report.
- Brand Watcher comparisons now use each vendor's brand colour instead of grey.

## Demo / walkthrough
Open Explore, then Market Monitor, then the Analysis tab. Scroll to "Share of voice": each bar
is in its vendor's colour. The "Most active vendors" table at the top shows a coloured dot by
each name. The Market Maturity Map keeps its own colours, which show each vendor's stage.

## Positioning notes
None. This makes the market views easier to read, but it does not answer a competitor gap or a
customer objection.

## Limits and what's next
- **Some vendors look alike.** Many AI-SOC startups use similar blues and purples, and a few use
  exactly the same colour: Twine and Bricklayer, Huntbase and Wirespeed, Simbian and Secure.com.
  The vendor's name always sits beside its colour.
- **Some colours were adjusted.** We lightened or darkened 17 of the 49 colours so they read on
  both light and dark screens. For example, Twine's bright lime became a darker olive.
- **Colour still means something else in some views.** The Maturity Map colours vendors by
  stage, the coverage timeline by article type, and the headcount chart by up or down. We left
  those as they are.
- **The share-of-voice pie** used colours chosen for colour-blind readers. Brand colours now
  replace them, so two vendors in the pie may be hard to tell apart for some readers.
- **Only the demo site has this,** and only for the 49 enabled vendors. Disabled vendors and
  other markets keep the old look.
