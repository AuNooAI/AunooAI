# Brand Watcher now says how each article relates to the brand, and only counts real press
_6 October 2026 · Brand Watcher on every running customer site; Market Monitor vendor links on Panaya_

## What shipped
- **Every article in a brand's coverage now has a stated relationship to the brand.** It is
  about the brand, the brand plays a real part in it, it is about the brand's industry, the
  brand is a passing mention, or it is not about the brand at all.
- **Press counts, alerts and digests only count independent press about the brand.** Industry
  stories, the brand's own content, advertising and fan sites stay visible, but they no longer
  inflate the press numbers.
- **A coverage breakdown in the Articles tab** shows press, industry, the brand's own content,
  promotional listings and fan sites side by side.
- **Recipe and fan sites have their own group.** They are shown, but never counted as press.
- **A company's own social accounts are recognised as its own.** Its posts no longer appear as
  outside voices.
- **Market Monitor vendor links use the same decision on Panaya.** A news article is credited
  to a vendor only when it really covers that vendor.

## Why it matters

**Press counts you can quote.**
- **Before:** each article got a relevance score from 0 to 1, and anything above 0.45 counted.
  The score was unstable. The same Sunstar article scored 0.89 on one run and 0.3 on the next.
  Real Colgate and Haleon stories fell out, and stock-valuation pages got in.
- **Now:** each article gets a label that says how it relates to the brand, and only
  "about the brand" or "the brand plays a real part", from an independent source, counts as
  press. When the model call behind a decision fails, we retry it instead of quietly dropping
  the article.
- **Who feels it:** analysts reading coverage numbers, and anyone sending alerts or digests to
  a client.

**Measured on articles reviewed by hand.** Oliver labelled a sample on two sites, and we
scored the old and new methods against his answers:
- **Sunstar (82 articles):** when the new method calls something press, it is right 86% of
  the time, against 64% for the old one. It also finds every real press item in the sample,
  where the old method found 58%.
- **Oviva (74 articles so far):** the new method is right 83% of the time, against 25% for the
  old one. Most of the old method's mistakes were general weight-loss stories that never named
  the brand.

**Industry news stays available.** A story about the oral-care market that never names
Sunstar is still shown, as industry news. It just isn't counted as Sunstar press.

**Advertising is labelled as advertising.** A shop listing for the brand's own product counts
as coverage, because it is the brand's advertising. It is marked as promotional so it can be
counted apart from press.

**A company's own voice is not outside coverage.** On Panaya, posts from five vendors' own
social accounts, Panaya's among them, were counted as outside voices. They are now filed as the
company's own content.

## Release notes (copy-ready)
- Brand Watcher now labels how each article relates to the brand: about the brand, the brand
  plays a real part, industry news, a passing mention, or not about the brand.
- Press counts, alerts and digests now count only independent press about the brand.
- A new coverage breakdown in the Articles tab shows press, industry news, the brand's own
  content, promotional listings and fan sites separately.
- Recipe and fan sites are shown in their own group and never counted as press.
- Posts from a company's own social accounts are now shown as its own content, not as outside
  coverage.

## Demo / walkthrough
Brand Watcher → choose a brand → Articles tab. The coverage breakdown panel above the article
list shows how many articles fall into each group: press, industry, the brand's own content,
promotional listings and fan sites. Sunstar is the best site to demo it on, because it has the
most labelled articles so far.

## Positioning notes
- **Answers a common objection to media monitoring:** "your coverage counts are inflated by
  noise." Each count now rests on a stated relationship to the brand, and the noise is shown
  rather than hidden.
- **Keeps the context buyers want:** industry and competitor news stays one click away instead
  of being thrown out.
- **Is honest about failures:** an article the system could not judge is retried, not silently
  scored as irrelevant.

## Limits and what's next
- **New articles only.** Articles collected before 6 October keep their old verdicts. We did
  not rescore history, on purpose, so that earlier hand corrections stay in place.
- **Early numbers.** The labels started on 6 October, and only Sunstar has a meaningful number
  of them so far (145 by 17:09 that day). The other sites fill in as new articles arrive.
- **Small samples.** The accuracy figures come from 82 Sunstar articles and 74 of 125 Oviva
  articles. The Oviva review is unfinished, and we have no hand-reviewed sample yet on the
  other sites.
- **Wiley's site** (wileytest) has had the change since 19:09 on 6 October, so its labels
  start later than the other sites'.
- **Not every site.** Panaya and Wiley's archive site (wiley) have the change switched on, but
  neither has brand topics today, so nothing changes there yet. The ten stopped customer sites
  need a general software update before they can take it.
- **Social posts** still use the existing rule. The new decision covers news articles only.
- **Market Monitor** uses the new decision only on Panaya. aisocnews.com is unchanged.
