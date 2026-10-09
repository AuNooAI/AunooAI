# The model that writes your reports is changing, and two report failures are fixed on the way
_2026-10-09 · Daily briefings, topic reports, Auspex, and every model picker · bugfixing only, not yet serving_

**Status note.** Live on the bugfixing site only, since 22:19 on 9 October. No customer site
has it; wiley and wileytest wait until bugfixing has run a day of real briefings and chats on
the new model. Do not send the release notes until the "Propagation" section of
`docs/changes.md` for this date lists the customer sites.

## What shipped
- The AI that writes daily briefings, topic reports and Auspex answers moves from Claude
  Sonnet 4.5 to Claude Sonnet 5.5. Amazon stops serving Sonnet 4.5 on 8 April 2027.
- A daily briefing can no longer go to review with no themes and no decision points. When the
  model's reply is cut off, the briefing says so and falls back to a plain summary instead.
- A topic report no longer fails, or loses its six executive summary cards, because the model
  wrapped its answer in prose or left a stray comma in it.
- Sonnet 5.5 appears in every model picker. Sonnet 4.5 stays selectable until April.

## Why it matters
**The model change.** Before: every customer-facing piece of writing ran on a model with an
end date, and no quota increase was possible from 8 October. Now: the same pipelines run on
Sonnet 5.5, and we tested them before switching. Each of the four report pipelines ran twice on
the new model with the fact-checking reviewer also on the new model. Every run finished, nothing
was cut off, and every reply parsed first time. Who feels it: nobody should, which is the point.
Analysts get the same reports from a model that will still exist next year.

**Briefings with nothing in them.** Before: when the model ran out of room mid-answer, the
briefing desk accepted a fragment and showed a briefing with no themes and no decision points,
and the log said the synthesis had completed. We saw this happen in testing on the new model.
Now: the system notices the cut-off, writes a one-line placeholder summary, and records why.
The analyst sees a briefing that is obviously incomplete rather than one that is quietly empty.
We also doubled the room the model has for that answer.

**Topic reports that failed on punctuation.** Before: the Future Horizons section of a topic
report read the model's answer strictly. A trailing comma ended the whole report; a summary
wrapped in a sentence of preamble lost its six cards and the deck shipped without them. Now:
both readers repair the answer and only accept it when the parts the deck needs are there.

## Release notes (copy-ready) — hold until the switch is live
- Daily briefings, topic reports and Auspex now run on Claude Sonnet 5.5.
- Sonnet 5.5 is available in the AI model pickers; Sonnet 4.5 remains available until April 2027.
- A daily briefing whose AI synthesis is cut short now shows a clear placeholder instead of an
  empty set of themes.
- Topic reports recover from malformed AI replies instead of failing or dropping the executive
  summary cards.

## Demo / walkthrough
- Any AI model picker (News Feed header, the Tune modals, Future Horizons): "Claude Sonnet 5.5"
  is listed first among the Claude models.
- Explore → Future Horizons → a topic report: the executive summary cards are present after a
  rerun. There is no visible change when things go right; the change is that they keep going right.

## Positioning notes
None for the model switch. A customer does not buy a model name, and we do not lead with one.
The honest point for a buyer who asks is that we test a model on their actual report pipelines
before we move them to it, and we read the output size and cost from our own usage ledger rather
than the vendor's page.

## Limits and what's next
- Not live anywhere yet. Bugfixing's restart is queued; wiley and wileytest wait until bugfixing
  has run a day of real briefings and chats on the new model and the ledger shows the cost.
- Cost: Sonnet 5.5 is a third cheaper per token than Sonnet 4.5 but writes about 1.65 times as
  many tokens for the same text (measured on the same briefing: about 3 characters a token
  against about 5). Output will cost roughly 10% more than today; input about a third less. We
  have not yet measured a full day.
- Sonnet 5.5 is more willing than 4.5 to return slightly broken JSON on long answers. We fixed
  the three readers the tests hit. Other report paths that read the model's answer strictly have
  not been audited yet.
- Amazon's content filter blocked one repair step on a briefing about military AI during
  testing. The briefing kept its previous version and nothing was lost, but sites that cover
  defence topics may see more of this. Not seen on Sonnet 4.5.
- Two problems found and not yet fixed: on wileytest, about 100 AI calls a day have been
  stopping at exactly 1,500 tokens for weeks (most likely the contradiction check in Strategic
  Intelligence, which then reports "no contradictions" with no error); and each topic report
  generates its executive summary twice and pays for it twice.
