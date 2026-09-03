# Reports written from your organisation's point of view, and two Foresight fixes
_2026-09-03 · Foresight (Future Horizons, Consensus, Executive Summary), Auspex chat, Explore news feed, brand-site provisioning_

## What shipped
- Every analysis, executive summary and Auspex conversation is written from your organisation's profile unless you choose a different one. Before, an empty profile picker produced generic output with no company context.
- The Foresight page opens with your default profile already selected.
- The Future Horizons tab no longer shows a download button for a topic that has never had a Future Horizons run. Before, it borrowed the newest Consensus run and the download failed with "not found".
- The narratives on the Explore news feed are built once per topic per day and reused for the rest of the day, instead of being rebuilt every time a new article arrives.
- New brand-monitoring sites get the customer's organisation profile at setup time, with the setup script asking for description, industry, markets, competitors and priorities.
- Topic Report executive summaries no longer describe every customer as an academic publisher.

## Why it matters
**Profile.** An analyst on the sunstar site generated a day's worth of Consensus and Future Horizons reports and only later noticed none of them mentioned Sunstar's priorities, competitors or markets. The picker had started empty, and the platform treated "no profile" as "no context" rather than "the customer's own profile". The same gap applied silently to the Executive Summary cards, which never received the chosen profile, and to every Auspex chat, which has no picker at all. Now the profile flagged as the site's default is the fallback everywhere, the run history records which profile was used, and the sunstar reports from that afternoon were regenerated with the Sunstar profile.

**Download button.** The Horizons tab was handed the most recent analysis of any kind when it had nothing of its own. It now only shows its own kind of result, and offers Generate when there is none.

**Narratives.** On a site with a steady flow of social posts the narratives were rebuilt on almost every visit, one AI call per topic and a wait of ten to twenty seconds each, because the saved copy was tied to whichever article was newest. It is now tied to the topic and the date range. Opening the feed again the same day is instant; the regenerate button still forces a fresh build.

**Provisioning.** A new brand site used to inherit only the stock "Generic Enterprise" profile. With the fallback above, that meant generic reports until someone added a profile by hand. The setup script now creates the customer's profile and makes it the default, so a site is analysing from the customer's perspective from its first report.

Who feels it: analysts and demo audiences on every site, most of all on dedicated brand sites where the profile is the whole point.

## Release notes (copy-ready)
- Analyses, executive summaries and Auspex chats default to your organisation profile when none is chosen.
- The Foresight page pre-selects your default profile.
- Fixed: the Future Horizons "Download interactive HTML" button appeared, and failed, on topics with only a Consensus analysis.
- Improved: news feed narratives load from cache for the rest of the day after their first build.
- New brand-monitoring sites are created with the customer's organisation profile in place.
- Fixed: Topic Report executive summaries used a fixed academic-publisher description regardless of customer.
- Fixed: the profile-create API returned a placeholder instead of the new profile's id.

## Demo / walkthrough
Foresight in a fresh browser: the Organizational Profile box shows the site's default profile. Generate any tab and the recommendations reference the profile's concerns and competitors. Pick a topic with a Consensus run but no Future Horizons run and open the Future Horizons tab: you see Generate, not a download button. Explore, news feed: open the narratives once, reload the page, they appear immediately.

## Positioning notes
The organisation profile is what makes a report about the customer rather than about the topic. Making it the default everywhere, and seeding it at provisioning, closes the gap between "we tailor analysis to you" and what a fresh site actually did.

## Limits and what's next
- A site with no profile flagged as default still gets generic output. The template itself keeps the stock default on purpose; the setup script supplies the customer's.
- The Auspex chat still has no way to pick a profile other than the default.
- Narratives refresh once a day per topic. An article that arrives at noon is not in that day's narratives unless someone clicks regenerate. The highlights panel on the same page still uses the old newest-article rule.
- Sites running older code (ibaset, pearson) have the narratives fix only. The Future Horizons download fix does not apply to wiley, wileytest, ibaset or pearson, which run older code with the same fault.
