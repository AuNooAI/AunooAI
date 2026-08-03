# Reports now pass a release gate before they reach a customer
_2026-08-03 · Wiley Horizons quarterly deliverables: deck, HTML report, executive letter_

## What shipped

- Every report build now runs through an automated quality gate before anyone can send it.
  The gate checks that every number and organisation name in the report appears in the
  articles it cites, that no internal settings or system terms leak into the text, that no
  deadline is already in the past, and that nothing renders broken.
- A second, AI-based review reads every report the way a careful editor would: it flags
  claims the sources do not support, wording that reads as a gap in our coverage, and —
  learned the hard way this quarter — any case where the customer's own former companies
  are described as unrelated third parties.
- The deck, the web report, and the executive letter for a quarter are now guaranteed to
  describe the same analysis. Each one prints the identity of the analysis it was built
  from, and they cannot silently drift apart between exports.
- A written review checklist ships in the product documentation, covering the three checks
  only a human can do: read the letter as the customer would, verify the team's credentials
  exactly, and sign off on anything the automated gate flagged.
- The executive letter is now judged against a customer-approved reference letter before it
  ships. A draft that reads worse than the standard — abstract openings, thin detail — is
  rejected and rewritten against the judge's critique. In its first live run the gate
  rejected a draft scoring 4 out of 10 and shipped the rewrite, which scored 8.
- The Q3 2026 package was rebuilt under this gate and delivered: 237-slide deck, web
  report, and executive letter, all from one analysis, all passing every check.

## Why it matters

Before: a quarterly report went out with a headline figure inflated tenfold, an invented
"82% consensus" badge, and the customer's own retired imprint listed as a struggling
competitor. Each error was findable by reading carefully — but nobody's job was to read
that carefully, every time, across 237 slides and three formats.

Now that reading happens on every build, by machine and by an AI reviewer, with a short
human checklist for the rest. The analyst who signs the report knows what was checked; the
customer contact stops being the person who finds the mistakes.

## Release notes (copy-ready)

- Automated pre-delivery checks on every report: figures and names verified against cited
  sources, internal terms blocked, dates validated, rendering verified.
- AI editorial review on every report, with findings logged for analyst sign-off.
- Deck, web report, and letter are built from one analysis and say so — no more
  mismatched versions.
- Published review checklist for the human sign-off steps.

## Demo / walkthrough

Forecast Tracker → Topic Reports → generate. The gate runs automatically; findings appear
in the logs and are stored with the report build. The last page of the deck and the bottom
of the web report show the "Analysis Provenance" identifiers that prove the artifacts
match.

## Positioning notes

This backs the "expert human oversight on every output" claim with a mechanism a customer
can be shown: three layers, each with a named owner (machine checks, AI reviewer, human
checklist). Credibility defence, not a new competitor claim.

## Limits and what's next

- The gate is advisory: it flags, a human decides. Nothing physically blocks sending a
  flagged report — wiring the gate into the send button is the obvious follow-on.
- The figure checks read article titles and summaries, not full text, so a figure that
  appears only deep in an article's body can be flagged as unsourced. The reviewer
  dispositions these.
- The AI reviewer over-flags some allowed constructs (about 9 advisory warnings on a clean
  letter in testing, zero errors); its findings need the human pass, by design.
- Closed later the same day: the gate now also covers Brand Watcher's customer outputs —
  digest emails, alert emails, incident report summaries (checked against their own
  evidence), and emailed account reports — on every site that sends them. Newsletters
  remain uncovered.
