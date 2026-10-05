# Typed judgment tools on the MCP server, and the Jev evaluation behind them
_2026-09-19 · MCP server on bugfixing only; everything else in this day's work is internal_

**Audience note.** Most of this day's work is internal measurement: shadow columns and
tables that record a second opinion from TypeSafe's Jev model beside our own pipeline's
decisions, without changing anything a customer sees. That part has no product surface and
is documented for engineers in `docs/changes.md`. The one customer-facing piece is three
new tools on the MCP server, described below. Nothing here is deployed beyond the
bugfixing site, and none of it is committed yet.

## What shipped
- Assistants connected to the MCP server can ask for a typed judgment: give a piece of
  state and a set of yes/no, multiple-choice or rated questions, and get a probability per
  answer instead of prose.
- They can also hand over a list of articles and one yes/no question ("is this a funding
  round?") and get a probability per article, sorted.
- A "which tool should I use?" pre-pass: the assistant describes what it wants in plain
  words and gets the best-fitting tool or playbook from the catalogue, with a fit score, or
  "none" when no tool is needed.

## Why it matters
Before, an assistant using our MCP server had to reason about a batch of articles in its
own words and parse its own answer, which is slow, costs LLM tokens, and gives no
confidence figure. Now it gets a calibrated probability per article in under a second, at
a cost of a few thousandths of a cent per call. The tool-suggestion step addresses the
other complaint about a 27-tool catalogue: assistants pick the wrong tool or call several.
In a five-request test it sent a social question to the social tool, a greeting to no tool
at all, and a "which of these twenty are funding rounds" request to the article judge.

Who feels it: anyone driving the bugfixing site from Claude or another MCP client, and the
analysts who read the results.

## Release notes (copy-ready)
- New MCP tools: `typed_judgment`, `judge_articles` and `suggest_tool` on the bugfixing
  site. Typed questions in, probabilities out, metered like any other tool call.
- `list_capabilities` now tells an assistant to call `suggest_tool` first when it is unsure
  which tool fits.

## Demo / walkthrough
From an MCP client connected to the bugfixing site: call `list_capabilities`, then
`suggest_tool` with a plain-language request, then the tool it names. For the article
judge, pass up to 40 article URIs from a search result and one yes/no question.

## Positioning notes
This is the first place a customer touches a decision model rather than an LLM through
our product. It supports the "narrative primitives, typed and measurable" story rather than
adding a new one.

## Limits and what's next
- Bugfixing only. The other sites' MCP servers do not have the tools; adding them is a
  copy of two files and a registration line per site.
- The model reads state literally and cannot do arithmetic or compare dates. Questions
  that depend on either need the answer pre-computed in the state.
- The tool-suggestion log records what was suggested but not yet what the client called
  next; joining the two is the next step for measuring it.
- The internal shadows behind this (relevance gate, briefing curation, citation check,
  reranking, issue merging, extraction checks, Auspex routing and compaction, observer
  agents) are record-only. None of them changes a decision yet. The evaluation report is
  the artifact at https://claude.ai/artifact/TeeJpWWJzQeBZTYiFsHHt3.
