# The whole feed in English: posts and article text, not just headlines
_2026-09-10 · News feed, Brand Watcher social views, every site_

## What shipped
- Social posts collected in another language are shown in English. The
  post as written is one click away under "Show original".
- News articles that did not make it through the relevance gate still
  show an English description instead of the collected one.
- Headlines of those posts and articles are English too, taken from the
  same translation.
- Sunstar's last 30 days were translated in place, so the change applies
  to what is already on the site, not only to new collection.

## Why it matters
Yesterday's release gave every article an English headline. On Sunstar,
where most of what we collect is Japanese, that left an English headline
over a Japanese post or description for most of the feed: the AI
analysis step writes an English summary, but social posts and articles
the relevance gate rejects never reach that step. An analyst reading the
Sunstar or Lion brand feed had to translate post by post.

Now every collected item is translated once, the moment it is saved, and
the original is kept next to it. Nothing about the analysis changes, and
an English item is left exactly as it was.

Who feels it: analysts on Japanese and German sites (Sunstar today, Oviva's
German coverage as it arrives), and anyone reviewing social posts in
Brand Watcher.

## Release notes (copy-ready)
- Posts and article descriptions collected in other languages now read in
  English, with the original text one click away.
- Headlines of those items are English as well.
- Existing Sunstar content from the last 30 days has been translated.

## Demo / walkthrough
Sunstar → News Feed → any Brand Monitoring topic → open a post. The
summary is English; "Show original" under it reveals the post as written.
Brand Watcher → Social shows the same English text in its lists.

## Positioning notes
Multilingual monitoring without a language barrier in the reading
experience. Competitors typically show machine translation on demand;
here the English is the default and the original is the option.

## Limits and what's next
- Translation is by a small model; it is faithful enough to read and
  triage, not for quoting in a report. The original is always there.
- Only the text shown in the product is translated: headline and
  summary/post. The full article body is not stored or shown, so it is not
  translated.
- Text longer than 3,000 characters is translated up to that point and
  marked with an ellipsis; the original is kept in full.
- A post that mixes languages, an English post with a Japanese hashtag
  say, is left as written.
- Oviva's last 30 days were translated the same evening (111 posts and
  descriptions, mostly German, plus Korean and Thai posts about Noom).
- Sites other than Sunstar and Oviva translate from now on; their older items keep
  the collected text until the backfill script is run for them.
- The "Show original" toggle is in the news feed article panel. Brand
  Watcher's social lists show the English text without a toggle yet.
