# Auspex answers the question you asked
_2026-10-11 · Auspex chat on bugfixing, wiley and wileytest_

Most of today's work was on the test suite and has no customer surface. This note covers the
three fixes a customer can feel, all in the Auspex chat. The suite work is in `docs/changes.md`.

## What shipped
- Paste a link to an article and Auspex reads that article, not the site's front page.
- Follow-up questions phrased as "what about ..." get an answer from the coverage instead of a
  "no articles found" refusal.
- When the first search comes back thin, the second, more structured search now runs as
  designed instead of falling back to a plain keyword match.

## Why it matters
**Links.** Before, every URL a user pasted lost its path before lookup, so "what does this
Reuters story say?" fetched reuters.com and Auspex answered about the homepage. Now it fetches
the story. Anyone who uses the chat to check or summarise a specific article feels this one.

**"What about" questions.** Before, any phrase after "about" was treated as a company or
person's name, even in lower case. "What about battery recycling costs?" made Auspex demand
those exact words in a headline or summary, and when they were not there it told the user,
over thirty relevant articles, that nothing mentioned "battery recycling costs". Now a name
has to look like a name. Analysts asking ordinary follow-up questions feel this one.

**The second search.** When the semantic search finds fewer than ten articles, Auspex asks a
model to plan a structured search by category, sentiment and date. The plan comes back as
JSON. A formatting quirk in how we read it broke any plan written compactly rather than
spread over lines, and the chat quietly fell back to matching the user's words as keywords.
Now the plan is read as written. Users on topics with thin coverage get the search they were
promised.

## Release notes (copy-ready)
- Auspex now looks up the exact article behind a pasted link.
- Follow-up questions such as "what about X" are answered from the coverage rather than
  treated as a search for a company called X.
- The structured fallback search runs reliably when the first search finds little.

## Demo / walkthrough
Open Auspex on any topic. Paste a full article URL with a question ("what does this say?")
and the answer now refers to that article. Then ask a plain follow-up beginning "what about"
and compare with the old refusal.

## Positioning notes
None. These restore behaviour the product already claimed; nothing new to position.

## Limits and what's next
- The fixes are live on all eight sites that run Auspex: bugfixing, wiley, wileytest, abm,
  oviva, panaya, sunstar and wbm.
- Named-entity detection is still pattern-based. A lower-case company name ("what about
  dropzone") is no longer treated as an entity, which is the safer default, but it also means
  it is not searched by name; the brand-name fallback covers tracked brands only.
- A fourth fix, to how two internal logging tables store JSON, has no customer surface and is
  documented in `docs/changes.md`.
