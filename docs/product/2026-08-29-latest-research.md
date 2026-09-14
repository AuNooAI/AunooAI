# Latest research: what the analyst firms say, on the front page
_2026-08-29 · Market Monitor front page (aisocnews.com, aisoc.aunoo.ai) and the Collection view_

## What shipped

- A **Latest research** section at the bottom of the front page, with its own page (`?section=research`).
- **Reports vendors cite.** When a vendor announces it was named in a Gartner, Forrester, KuppingerCole, IDC, GigaOm or other analyst report, the page names the report and lists every vendor that cited it, with the position they were given ("LMNTRIX (Major Player)") and a link to each announcement.
- **From the analyst firms.** Posts from the firms' own public pages — Forrester's security blog and KuppingerCole's research listing to start — that mention the market, labelled Research, Blog or Webinar.
- **Analyst feeds** card in Collection → Overview: the list of firm feeds read for the market, with add and remove.

## Why it matters

The reports themselves sit behind paywalls, so "what do the analysts think of this market" had no place on the page. Two things about a report are public: the vendors it names say so, loudly, and the firms publish blogs and research listings. The section is built from those two traces and links out to each of them; nothing is licensed or republished.

For a reader, the value is in the grouping. On 29 August the 90-day view shows the 2026 Gartner Hype Cycle for Security Operations cited by five vendors (Dropzone AI, Backline AI, Simbian, Prophet Security, Qevlar), the IDC MarketScape for Worldwide MDR/MXDR naming LMNTRIX a Major Player, Gartner's Innovation Insight: AI SOC Agents, and KuppingerCole's "123 AI SOC Vendors: Why So Many? Can They All Survive?". Who got named, and by whom, is a market signal on its own.

For an operator, nothing new is paid for. Citations are read from records already collected. The firm feeds ride the same reader as the vendor blogs.

## Release notes (copy-ready)

- New front-page section, Latest research: analyst reports vendors have been named in, grouped by report, with the vendors and their positions; plus the analyst firms' public posts that mention the market.
- Forrester's security blog and KuppingerCole's research listing are read by default; more feeds can be added per market in Collection → Overview.
- Every item links to its source. Reports behind paywalls are named, not reproduced.

## Demo / walkthrough

- https://aisocnews.com/?days=90 — Latest research is the last section. "All N →" opens the section page.
- https://aisocnews.com/?section=research&days=90 — every report and post in the period.
- Explore → Market Monitor → Collection → Overview → Analyst feeds: the feeds read for the market; add a firm and a feed URL, or remove one.

## Positioning notes

Competing market pages either buy the reports and cannot show them, or ignore analysts altogether. This is the honest public shape of the analyst layer: the report titles, the vendors named, the positions, the links. It sits well next to the Market Maturity Map, which is our own placement rather than an analyst's.

## Limits and what's next

- Gartner's blogs and newsroom refuse this server (HTTP 403), so Gartner appears only through vendor citations. That is where Gartner dominates anyway (52 mentions in the corpus against 4 for IDC and 3 for Forrester).
- Detection is rule-based: a firm name plus a report family or a recognition verb. It misses a citation that names neither ("IDC examines the rise of…" is caught; "our conversation with Gartner" is not) and cannot tell two same-year Hype Cycles apart when a post names only "the 2026 Hype Cycle" — such a post joins the one report of that family the corpus knows, or stays on its own when there are two.
- In the shared (public) view a post that names vendors outside the public roster is left out, the same rule as everywhere on the page. KuppingerCole's "123 AI SOC Vendors" is visible in the full view only for that reason.
- Dates are publication dates, so a report burst from June shows in the 90-day view, not the 30-day one.
- Next: follow the individual analysts on X and Bluesky through the follow list (their research notes' titles are often the only public trace); a report drilldown listing every citing record.
