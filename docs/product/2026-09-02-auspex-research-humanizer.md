# Research reports now read less like a machine wrote them
_2026-09-02 · all sites with the research agent (Auspex)_

## What shipped

The research agent's reports now pass through the same AI-writing cleanup that
report bundles have had since May. After a report is written and its sources are
attached, a detector scans each section for the habits that mark machine prose —
lists of three where two things were meant, inflated vocabulary, walls of em
dashes — and rewrites the sections that fail, section by section. Citations are
protected: any rewrite that would lose a source link is thrown away and the
original wording kept.

## Why it matters

**Before:** the two research reports built for the Sunstar demo scored 72 and 81
detector hits. These are customer-facing documents; that register reads as
machine output to anyone who has seen much of it — including the prospects we
send them to.

**Now:** the same reports score 69 and 68, with every citation and heading
intact, and every future report gets the pass automatically. The cleanup is
honest about its limits: roughly a third of what the detector flags in these
documents is not slop (Japanese source titles, a deliberate heading style), and
the two habits that remain — rule-of-three padding and inflated vocabulary —
come from the writing step itself. Getting those lower means changing how the
reports are written, which changes their voice and deserves its own decision.

Who feels it: anyone who reads a research report from the platform, and the
person who no longer has to hand-edit one before sending it to a customer.

## Release notes (internal only)

- Pass runs inside the research agent's writing stage; progress streams as a
  "humanizing" step. Gated by the existing `WILEY_HUMANIZE` switch; any failure
  leaves the report unchanged.
- Sections are rewritten in chunks of up to 5,000 characters because the shared
  rewrite helper caps its output; References and Methodology sections, chart
  markers and short fragments are skipped.
- Live on sunstar, wiley and wbm; wileytest picks it up at its next quiet
  window; pearson excluded until its code is brought current.

## Limits and what's next

- The detector-driven pass cannot go much below ~65 hits on a long report; the
  rewrite model reintroduces habits at about the rate it removes them.
- The next lever is the writing prompt itself (adding the house no-slop rules to
  the report writer). Held back deliberately: it changes report voice and should
  be compared before/after on a real report first.
