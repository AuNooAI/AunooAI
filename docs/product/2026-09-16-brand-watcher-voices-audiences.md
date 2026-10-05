# Voices: cleaner audiences, profiled posters, and nothing on the page that is not for the reader
_2026-09-16 · Brand Watcher → Voices, on oviva.aunoo.ai_

## What shipped
- On a health brand, people weighing up the programme are counted with patients. There is no separate Customers row.
- Posts whose text shows no role are grouped as Bystanders, with a plain description of what that means.
- A "Profile posters" button builds an account profile for every poster in the window that lacks one, and the table reloads with the results.
- Exclude terms added to a brand now clean up posts that were already collected, not only new ones.
- The per-audience digest no longer prints internal quality-check notes, error text or model names, and it recovers when the AI returns an unusable answer.

## Why it matters
**One Patients row.** Before, a health brand could show a Customers audience with one or two posts and a net sentiment of -100. That figure looked like a finding. It was a taxonomy artefact: the same role list serves publishers and software vendors, where "customer" is the right word, and the odd post about paying for a treatment landed there. Now an analyst reading Oviva's page sees patients, clinicians and the brand's own voice, which is the comparison the view was built for.

**Bystanders.** A large "Unidentified" row read as a gap in the data. Most of those posts are jokes aimed at third parties, shared discount codes or study summaries. Calling them Bystanders says what they are: commentary from the sidelines, kept in the counts but not mistaken for an audience.

**Profile posters.** Oviva's table looked tidy because someone had already profiled nearly every account posting about it under Market Monitor. Noom and WeightWatchers had no profiled posters, so a third to a half of their posts could not be placed. The button gives every brand the same treatment on demand. After running it on oviva, unplaced Noom posts fell from 12 to 8 and WeightWatchers from 28 to 19 in the 30-day window, and 84 accounts gained a profile.

**Exclude terms reach back.** Noom's page carried Thai fan posts about a television character nicknamed "Noom", which the AI had scored as highly relevant. Adding exclude terms used to affect only posts scored from then on. Now saving the terms also removes matching posts already in the tables. On oviva that took 30 fan posts out of Noom's view, leaving one genuine bystander comment.

**The digest reads clean.** A customer saw "The writer used verdict language in its own voice after one rewrite: poor. Read the quotes, not the labels." That was a note from our own tone check. It, the raw error messages and the AI model name are gone from the page and the HTML export. The check also flagged ordinary attributed reporting, so it was tightened. Digests that came back empty were never retried and now are; Noom's patients digest, empty before, now shows a summary and five themes.

## Release notes (copy-ready)
- Voices on health brands shows patients in one row; prospective users are counted with them.
- Posts with no identifiable author role are labelled Bystanders.
- New "Profile posters" action builds account profiles for a brand's posters and refreshes the audience table.
- Brand exclude terms now remove matching posts that were collected before the term was added.
- Audience digests no longer show internal notes, error text or model names, and retry when the AI returns nothing usable.

## Demo / walkthrough
Brand Watcher → Voices. Pick a brand. The audience cards along the top show the split; Bystanders is the row for unplaced posts. Click "Profile posters" and watch the counter; the table reloads when it finishes. Click two audience cards to compare their digests. Export HTML gives the same view as one file.

## Positioning notes
Voices is the answer to "who is saying this about us, and do doctors say something different from patients". This release removes the two things that made the table hard to trust in a demo: an audience row that was an artefact, and a large unexplained "Unidentified" block.

## Limits and what's next
- The fold to Patients fires on any brand with patient, clinician or caregiver posts. Consumer weight-loss brands such as WeightWatchers qualify, so their buyers are also shown as patients.
- Profiling is on request, not scheduled, and each account costs two platform calls and one short AI call. The runner paces itself to stay under the shared rate limit; 50 accounts take about six minutes.
- A profiled account outranks the reading of one post. After a run, a single Press or Investor row can vanish if the account reads as something else with its bio in view.
- Exclude terms match as plain substrings. A short term can hit a real author; "palm" would have removed a journalist covering Noom Med, so terms need checking against actual authors before saving.
- The relevance model still scores some non-English fan posts as on-brand. Exclude terms are the fix per brand; a model-side fix is not in this release.
- Live on oviva only. The code is in the canonical tree but not yet committed, and the Wiley sites hide Voices.
