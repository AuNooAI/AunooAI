# Foreign-language articles now show an English headline
_2026-09-09 · News Feed, Brand Watcher and Market Monitor article cards on every site_

## What shipped
- Articles collected in Japanese, German, French or any other language now
  show an English headline, with the original headline in smaller text
  underneath.
- The last 30 days of existing articles are being converted the same way on
  every customer site.

## Why it matters
The AI summary under each article was already English. The headline above it
was not, so a Sunstar analyst scanning the feed saw "厚労省、唾液使った歯周病検査に経費補助"
over an English paragraph and had to read the paragraph to know what the
story was. Now the headline reads "Ministry of Health, Labour and Welfare to
subsidize costs for periodontal disease testing" and the Japanese line sits
under it for anyone who wants the source wording or needs to search for it.

The people who feel this are analysts on sites that track non-English
markets: Sunstar (Japan, France), Oviva (Germany, Switzerland), and any
Brand Watcher site whose brand is discussed in more than one language.

## Release notes (copy-ready)
- Article headlines are shown in English whatever language the article was
  written in. The original headline appears underneath.
- Existing articles from the last 30 days have been converted.

## Demo / walkthrough
On sunstar.aunoo.ai open Explore, pick the Oral Health & Whole-Body Health
topic and the Japan or France region, and scroll the article list. Cards
with a second, greyed headline are the converted ones. Click one: the detail
panel shows both.

## Positioning notes
None. This removes a gap that a multilingual customer would have counted
against us; it is not a differentiator on its own.

## Limits and what's next
- Social posts that the AI analysis step skips (most raw X and Bluesky
  posts) keep their original text. Translating those was the second option
  and is not done; it would add one cheap model call per post.
- The English detector is deliberately conservative: a short English
  headline with no common function word is sent to the model, which returns
  it unchanged. That costs a fraction of a cent, not a wrong headline.
- Headlines are translated by a small model. Brand and product names are
  kept as written, but a transliteration of a Japanese product name can
  differ from the company's official English spelling.
