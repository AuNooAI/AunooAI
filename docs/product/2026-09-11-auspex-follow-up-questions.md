# Auspex follow-up questions now stay on subject
_2026-09-11 · Auspex research chat, on every site that runs it_

## What shipped
- A short follow-up question ("overview recent reviews", "what about
  Elsevier?") is understood in the context of the conversation before it
  searches the article database.
- Asking for "recent" or "latest" coverage of something searches for that
  something and shows the newest matches first. It no longer returns a
  random sample of the last week.
- A question about one tracked brand is answered from that brand's
  coverage, not from a mix of its competitors' coverage.

## Why it matters
**Before:** a user on the Wiley brand-monitoring site asked whether
Wiley's Glassdoor rating had dropped, then typed "overview recent
reviews". Auspex answered the second question from 218 unrelated
articles and told the user the database held no Glassdoor reviews. It
held 11 for Wiley. The first answer had a quieter problem: it described
31 "Wiley" reviews, and 20 of them were Elsevier, Pearson and SAGE
reviews counted in as Wiley's. An analyst reading that answer would have
attributed a competitor's "hostile family-unfriendly policies" quote to
Wiley.

**Now:** the follow-up is read as "recent Wiley Glassdoor employee
reviews", the search finds all 11 Wiley reviews, and the answer contains
nothing from the other publishers. The person who feels the difference
is the analyst who chats with Auspex the way people actually chat, in
short follow-ups that assume the subject carries over.

## Release notes (copy-ready)
- Auspex follow-up questions now keep the subject of the conversation
  when searching the database.
- "Recent" and "latest" now mean newest-first results about your subject,
  not a sample of everything from the past week.
- Brand questions are answered from that brand's own coverage; competitor
  coverage is no longer mixed in.

## Demo / walkthrough
Any site with Auspex. Open Auspex, set the topic to All Topics, ask a
question that names a tracked brand, then follow up with a short phrase
that does not repeat the brand ("overview recent reviews", "any
negatives?"). The article count shown above the answer now reflects that
brand's coverage only. On wbm, "did Wiley's Glassdoor rating drop?"
followed by "overview recent reviews" is the reference case.

## Positioning notes
This closes the most common way a demo of Auspex goes wrong: the second
question. Prospects test a research chat by following up, and an answer
that loses the thread reads as the product not understanding the domain.
It also removes a credibility risk for brand monitoring, where mixing a
competitor's employee complaints into a client's brand picture is worse
than returning nothing.

## Limits and what's next
- The follow-up rewrite runs only for messages of 300 characters or
  fewer. A long pasted prompt is treated as standing on its own.
- The rewrite is a small model call before each follow-up, so a follow-up
  turn takes roughly a second longer than before. Not measured this
  session.
- Brand scoping applies only to brands set up in Brand Watcher on that
  site. A company that is not a tracked brand still goes through the
  ordinary cross-topic search.
- "Recent" without a number does not apply a date cut-off; it orders by
  date. Say "last 30 days" to get a hard window.
- Auspex still has no Glassdoor rating history, only the reviews the
  collectors stored. The original question, whether the rating dropped,
  still cannot be answered from the data.
- The 14 sites that are currently switched off do not have this change
  and will pick it up at their next catch-up.
