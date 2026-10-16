# Briefings written through the Aunoo connector now check themselves for machine prose
_16 October 2026 · Aunoo MCP connector (Claude and other assistants connected to a customer site)_

## What shipped
- A new connector tool, `check_ai_tells`, that scans a draft for the written habits that mark
  text as machine-generated and returns each one with the fix to apply.
- The four briefing playbooks (topic briefing, deep dive, keyword scan, brand briefing) now
  tell the assistant to run that check on its draft, fix only what was flagged, and check
  again before handing the briefing over.
- Live on every customer site that runs the connector.

## Why it matters
When a customer asks Claude for a weekly topic briefing through the Aunoo connector, Claude
pulls the articles, the sentiment split and the story mix from the site, then writes the
briefing itself. Until today nothing checked that prose. It read the way model prose reads:
"the supply chain landscape", "underscoring its focus", four bold pseudo-headings in a
400-word note. A reader spots that in a line and trusts the rest of the briefing less.

Asking the model to write less like a machine does not fix this. The instruction is vague,
and small or mid-sized models ignore it or trade one habit for another. What does work is a
list. The new tool runs 31 fixed rules over the draft, no model involved, and hands back the
exact phrases that fired, where they are, and what to put instead. Editing a named list of
spans is a task any model does well.

We measured it on a real briefing from the bugfixing site. The first draft of a 337-word
battery-industry briefing had 13 flags: four bold pseudo-headings counted twice, two inflated
words, two trailing "highlighting the importance" clauses, and one note about markdown.
Editing only those spans brought it to one flag, and that one was the markdown note, which
the tool no longer raises for chat replies because chat is written in markdown.

Who feels it: the analyst or executive reading the briefing gets a note that reads like a
colleague wrote it. The customer admin gets this without a prompt change, a model change or a
setting.

## Release notes (copy-ready)
- Briefings written through the Aunoo connector are now checked for machine-writing habits
  before they reach you. The assistant fixes the flagged phrases and checks again.
- The check is rule-based and runs on the site, so it adds no model cost and no noticeable
  delay.
- Assistants can also call the check directly on any text, with a setting for whether the
  text will be read as markdown, HTML or plain text.

## Demo / walkthrough
In Claude with the Aunoo connector attached, run the "topic briefing" playbook for a topic
with coverage in the last week. In the tool trace you will see the data calls, then a
`check_ai_tells` call on the draft, then usually one more after the edits. The returned
briefing has real headings rather than bold lines and no "landscape" or "underscore".

## Positioning notes
Most monitoring tools that add an AI summary ship whatever the model writes. This puts a
deterministic editor between the model and the reader, using the same detector that already
cleans our Wiley reports and deep-research output. It is a small, concrete answer to "your AI
summaries sound like AI".

## Limits and what's next
- The check is only as good as its 31 rules. It does not catch invented facts, wrong numbers
  or a dull structure. The citation rules in the playbooks still carry that load.
- It covers the four prose playbooks. The three that build a visual artifact (voices,
  consensus, horizons) render the site's own stored text and are not checked.
- It depends on the assistant following the playbook instruction. A user who asks for a
  briefing in their own words, outside a playbook, gets the check only if the assistant
  chooses to call it. The tool description invites that, but we have not measured how often
  it happens.
- Two rules can fire on one phrase (a bold pseudo-heading trips both the heading rule and the
  bold rule), so the raw count overstates the editing work. The span list is the honest
  measure.
- Two of the ten sites (sunstar, wbm) run an older playbook set without the brand briefing,
  so they carry the check on three playbooks, not four.
