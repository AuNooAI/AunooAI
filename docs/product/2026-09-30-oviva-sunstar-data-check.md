# Oviva and Sunstar: cleaner social feeds, two brands that now collect news
_30 September 2026 · Brand Watcher on the Oviva and Sunstar customer sites_

## What shipped
- Oviva: HelloBetter and Zanadio now collect German news. Until now they collected nothing useful.
- Sunstar: we removed 27 search keywords that brought in almost only off-topic posts.
- Sunstar: Japanese keywords now get the same check as English ones. Each social post must
  actually contain the keyword.

## Why it matters
**HelloBetter and Zanadio (Oviva).** Someone added both brands on Oviva in September.
- *Before:* Zanadio had no search keywords at all, so its page stayed empty for 16 days.
  HelloBetter's keywords included a founder's name, "David Ebert". That name pulled in film
  reviews about Roger Ebert, and every article it collected was off-topic.
- *Now:* both brands are searched by name in English and German news. Both companies are
  German, and their press coverage is German. On the first run, the site picked up HelloBetter's
  data breach report from 29 September, which it had missed before.
- *Who notices:* the analyst watching Oviva's competitors.

**Sunstar keyword clean-up.** Keywords like "Lion Corp" matched any post containing the word
"lion".
- *Before:* over 30 days, the 27 keywords we removed matched posts 16,766 times, and only 749 of
  those matches were on topic (4.5%). A post that matched two keywords counts twice.
- *Now:* the site spends less of its paid social search on noise, and the AI check that reads
  each post has less to read.
- *Who notices:* the operator paying for the social search. Analysts see little change, because
  the site already hid these posts.

**Japanese keyword check (Sunstar).** After each social search, the site checks that each post
really contains the keyword.
- *Before:* that check only understood Latin letters, so it let every post for a Japanese
  keyword through. Chinese "happy weekend" posts were filed under Sunstar.
- *Now:* Japanese, Chinese and Korean keywords get the same check. When we replayed the last 30
  days, the check would have removed 6,187 of the 6,730 posts brought in by the Japanese keywords
  we later deleted.
- *Who notices:* the operator. The analyst sees a Consumer Voice and brand feed with less junk
  in it.

## Release notes (copy-ready)
- Oviva: HelloBetter and Zanadio are now monitored in German and English news.
- Sunstar: brand searches tightened. Keywords that returned mostly unrelated posts were removed.
- Social monitoring now checks Japanese, Chinese and Korean keywords against post text, as it
  already did for English.

## Demo / walkthrough
Oviva → Brand Watcher → select HelloBetter → News. The 29 September data-breach reports appear
there.

## Positioning notes
None. This is upkeep of two customer sites. It doesn't add a new capability.

## Limits and what's next
- **Social collection is paused on seven sites.** Since 29 September, our social search provider
  has refused searches because the account hit its usage limit. That covers Twitter, Instagram,
  Reddit and TikTok on Oviva, Sunstar, panaya, abm and bugfixing. Bluesky and LinkedIn still work.
  Nothing above changes this until the account is topped up.
- **Lion has no company-name keyword now.** In English, "Lion" can't be separated from animals
  and religious posts. Lion Corporation is tracked through its product names instead.
- **"Sunstar" stays, though only about 1 in 20 of its posts is on topic.** It is the client's own
  name, so removing it is the client's call.
- **Sometimes a Japanese keyword returns an English post.** The social provider does this for
  "Polident", for example. The new check drops such a post unless an English keyword for the
  same product also finds it.
- **Two Oviva topics still collect only noise.** Second Nature news (493 articles in 30 days, none
  on topic) and Oviva's market watch (269, none on topic).
- **Oviva's German searches use one news source.** The second source, NewsData, has no key set
  up on Oviva.
