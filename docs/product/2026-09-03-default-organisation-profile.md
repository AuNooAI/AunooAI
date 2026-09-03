# Analyses now use your organisation profile by default
_2026-09-03 · Foresight (all tabs and the Executive Summary), Auspex chat, Topic Reports_

## What shipped
- Every analysis, executive summary and Auspex conversation is written from your organisation's profile unless you pick a different one. Before, leaving the profile picker empty produced generic output with no company context.
- The Foresight page opens with your default profile already selected.
- The Topic Reports executive summary no longer describes every customer as an academic publisher.

## Why it matters
An analyst on the sunstar site generated a day's worth of Consensus and Future Horizons reports and only later noticed none of them mentioned Sunstar's priorities, competitors or markets. The picker had started empty, and the platform treated "no profile" as "no context" rather than "the customer's own profile". The same gap applied silently to the Executive Summary cards and to every Auspex chat, which has no picker at all.

Now the profile flagged as the default on the site is the fallback everywhere. The cache and the run history record which profile was used, so an operator can see it after the fact.

## Release notes (copy-ready)
- Analyses, executive summaries and Auspex chats now default to your organisation profile when none is chosen.
- The Foresight page pre-selects your default profile.
- Fixed: Topic Report executive summaries used a fixed academic-publisher description regardless of customer.

## Demo / walkthrough
Foresight, open in a fresh browser: the Organizational Profile box shows the site's default profile. Generate any tab and the recommendations reference the profile's concerns and competitors.

## Positioning notes
None. This closes a correctness gap rather than adding capability.

## Limits and what's next
- A site with no profile flagged as default still gets generic output. Oviva is in that state today: its default is the stock "Generic Enterprise" profile.
- The Auspex chat still has no way to pick a profile other than the default.
- Sites running older code (ibaset, pearson) do not have this yet.
