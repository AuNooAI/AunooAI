# The topic report's Word download is an executive summary again
_2026-08-03 · Topic Reports — Word (.docx) export · Wiley and Wiley Test_

## What shipped
Downloading a topic report as Word now gives you the executive summary: about 500 words, five
sections, ready to forward. Since mid-June it had been giving you a transcript of the slide
deck instead — roughly 32,000 words for a six-topic report.

Anyone who does want the whole thing in Word can still have it, on a separate download.

## Why it matters
The Word file exists so a report can be emailed to someone who will not open a 250-slide deck.
That is the entire point of it. For about seven weeks it was the opposite: every slide's
content typed out in order, including labels that only make sense on a slide — "CARD 3 OF 6",
"YOUR WINDOW", "Based on scenarios". Nobody was going to send that to an executive.

The summary is back to the format people recognise: the bottom line, what happened this
quarter, the headline tail risk, what it means for Wiley, and what to watch next quarter.

Two related problems were found and fixed on the way, both of which had been quietly damaging
the output:

- **A topic was being dropped from every export.** Topics with a display name — "Scientific
  Publishing" instead of "Scientific Publishers - General Monitoring" — were looked up under
  the wrong name and silently left out. Reports covered five topics where six were selected.
  The slide deck was never affected, only the Word, HTML and Markdown exports.
- **The executive summary itself could vanish without any error.** The AI step that writes the
  letter sometimes returns output the system cannot read. When that happened the letter was
  dropped, everything else was kept, and the report was marked successful. The result was a
  one-paragraph "executive summary". It now gets a second attempt, which recovered it in nine
  seconds on the very next run — and the failure turned out to be reliable, not a fluke.

## Release notes (copy-ready)
- The Word download for a topic report is the executive summary again, not a transcript of the
  slides. The full transcript is still available as a separate download.
- Fixed: reports were silently omitting any topic that has a display name configured.
- Fixed: the executive summary letter could be dropped without an error if the AI step returned
  unreadable output. It is now retried.

## Demo / walkthrough
Open a topic report and choose the Word download. You should get a short document headed
"Wiley Horizons — Executive Summary" with the period underneath, five sections of prose, and
the AunooAI sign-off. For everything in Word, use the full download instead.

If a report has never had its summary generated, the first Word download builds it, which takes
a few minutes. It saves as it goes, so if the download times out, asking again returns the
finished document.

## Positioning notes
This is the artefact that travels. The deck gets presented once; the summary gets forwarded.
Worth checking before any customer sees a report, because a bad Word export undoes the
impression the deck makes.

## Limits and what's next
The summary is the letter only — around 500 words. An earlier version also carried expert view,
cross-cutting themes, a decision framework and per-topic summaries. Those were removed in June
on client feedback that the layered structure "reads as cluttered for C-level", and that
decision has been left alone. If the fuller shape is wanted back, that is a deliberate reversal
to discuss, not a bug to fix.

The HTML and Markdown exports still resolve topics by display name, so they can still drop one.
The Word export is unaffected. Worth closing, and roughly an hour for an AI including deploy.
