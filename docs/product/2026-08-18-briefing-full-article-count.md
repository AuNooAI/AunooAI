# The daily briefing now always fills up
_2026-08-18 · Explore tab → daily briefing_

## What shipped
The briefing on the Explore tab now returns the number of articles you asked for. If
you set it to six, you get six.

Before today it sometimes returned four or five with no explanation, and nothing in the
product told you an article had gone missing.

## Why it matters
The briefing asks an AI model to choose the day's most important articles from a pool of
about fifty. The model then has to hand each choice back to us by copying the article's
web address exactly. Some news sites use addresses that differ from each other by a
single character — two Techmeme stories on the same day might be `.../p9` and `.../p35`.
The model would pick a genuinely good article, copy its headline perfectly, and get one
character of the address wrong. We could not tell which article it meant, so we quietly
dropped it.

This morning that happened twice in one briefing, which is why six became four. The two
articles lost were a $120M settlement by Pornhub's parent company and a filing showing
Nvidia committing up to $105B to a data centre campus — both squarely relevant, both
thrown away over a typo in an address.

We checked how often this had been happening. Across ten months and 237 briefings, 34
came back short — about one in seven. It affected every AI model the briefing has ever
used, so switching models was never going to fix it. Seven of those short briefings were
since June.

Now the model hands back a short reference number for each pick, like `a7`, instead of
relying on it to copy a long address perfectly. If that reference is missing we fall
back to matching the address, and then the headline. And if a briefing still comes up
short, we ask the model for replacements rather than shipping a thin briefing.

Anyone who reads the daily briefing feels the difference: the briefing is complete, and
the articles that used to vanish were often the most newsworthy ones, because breaking
stories cluster on the aggregator sites with the confusable addresses.

## Release notes (copy-ready)
- The daily briefing now reliably returns the full number of articles you configured.
- Fixed a long-standing issue where relevant articles were silently dropped from the
  briefing because of how the AI model referenced them internally. This affected roughly
  one briefing in seven.
- If the briefing comes up short, it now automatically requests replacement articles.

## Demo / walkthrough
Open **Explore → the daily briefing panel**. Set the article count to six in the tune
modal. Regenerate. Count the cards — there will be six. Previously the same click could
produce four.

## Positioning notes
This is a reliability fix on a surface customers look at every morning, so it is worth
mentioning to anyone who has commented that the briefing "felt thin" on some days. It
closes a quiet trust gap: a briefing that silently returns less than you configured
teaches people to doubt the whole product. Nothing here is a competitive differentiator
on its own.

## Limits and what's next
- If the model picks an article that genuinely is not in the pool — an outright invention
  rather than a miscopy — we still reject it, which is correct. The replacement request
  covers the resulting gap.
- We ask for replacements once. A briefing could in theory still come up short, but it
  now records that in the logs rather than passing silently.
- Two unrelated problems surfaced while investigating and were deliberately left alone:
  the deeper per-article analysis fails to parse its own output on some articles, and
  full-text fetching returns nothing for Techmeme and a few other sites. Neither affects
  the article count. Both are worth a separate look.
