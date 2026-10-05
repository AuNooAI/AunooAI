# Brand Watcher measures what others say, not what the brand says about itself
_2026-09-16 · Brand Watcher dashboard, Articles and Social tabs, every site_

## What shipped
- Articles a company publishes on its own website are marked "owned". They
  stay in the article list, but they no longer count towards news sentiment,
  share of voice or the category charts.
- Share of voice shows a brand's owned items beside its earned coverage, as
  "+N owned", instead of mixing them in.
- Social posts no longer appear in the News list.
- A post that was reposted, mirrored or spammed several times shows once,
  with a "×N posts" mark.

## Why it matters
On Oviva's site, every article the dashboard counted as Oviva news over the
last 90 days came from oviva.com: recipe posts and customer testimonials.
Read as coverage, that made Oviva's news sentiment look positive and its
share of voice look healthy, when in fact no external press about Oviva had
made it through in that period. A brand praising itself is not coverage.

The same review found Bluesky and Reddit posts listed as news, and the same
WeightWatchers post repeated in the Social list because it matched the brand
twice. Each of these made the numbers look busier than the reality.

Who feels it: anyone reading a Brand Watcher dashboard to judge how a brand
is being talked about, and anyone comparing brands. Analysts still see the
owned items, clearly labelled, the way the market map shows a vendor's own
posts.

## Release notes (copy-ready)
- Brand Watcher now separates what a company publishes about itself from
  what others publish about it. Own-site articles are labelled "owned" and
  excluded from sentiment and share of voice.
- Social posts are no longer listed among news articles.
- Reposts and mirrors of the same social post are folded into one entry.

## Demo / walkthrough
Oviva site → Brand Watcher → Dashboard, 90 days. Share of voice lists
WeightWatchers with 25 articles, Noom with 3 and "+2 owned", Oviva with
"+14 owned" and no earned coverage. Articles tab, brand Oviva: every card
carries the "owned" chip. Social tab, Noom and WeightWatchers: no post
appears twice; a few carry "×2 posts".

## Positioning notes
Earned versus owned is the distinction a communications team already makes.
Showing both, separately, is more credible than a single inflated number,
and it makes the absence of earned coverage visible rather than hidden.

## Limits and what's next
- A brand's own domains come from the Entity Intelligence identifiers. On
  Oviva all seven brands have one. Sunstar's brands have none yet, so their
  own pages are not tagged there until the identifiers are added.
- Only articles on the company's own website and its LinkedIn page are
  treated as owned. A press release republished by a newswire still counts
  as earned coverage.
- Folding reposts works on identical text. A quote-tweet that adds a
  comment stays a separate post.
- Oviva has had no external press pass the relevance and analysis gates in
  90 days; the dashboard now shows that plainly as zero earned coverage. The
  next question is whether the relevance gate is too strict for Oviva's
  external mentions, which is a separate piece of work.
