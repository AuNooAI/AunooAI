# Social sentiment now measures what other people say
_2026-09-24 · Brand Watcher: Social tab, social reports, Observer agents (Oviva)_

## What shipped
- A brand's own social accounts no longer count toward its social sentiment.
- The Social tab says how many of the brand's own posts it left out.
- Oviva's Adverse Media Monitor now judges a post by its overall message.

## Why it matters

### Own posts in social sentiment
**Before.** Social sentiment counted every on-brand post, including those from the company's own
accounts. News already left a company's own content out. Social did not.

A company's own posts are almost always positive, so they lifted the score:
- Oviva's Instagram read +86. All 7 posts behind that number came from @oviva_uk and @oviva_de.
- Oviva's engagement-weighted sentiment read +23, because the brand's own posts collect the most
  likes. Weighted by post count, it read −3.

**Now.** We keep a list of the accounts each company runs, checked by hand. Posts from those
accounts are left out of the sentiment scores, the network comparison and the "posted vs seen"
view.

Oviva now reads −28 by post count and −31 weighted by engagement. That is what patients,
clinicians and other outside voices are saying.

**Who feels it.** Brand and communications teams, who read the score as outside opinion.
Competitive analysts feel it most, because competitors' own accounts inflated them too. Colgate's
regional accounts, for example, posted 86 of the on-brand posts about Colgate in 90 days on
Sunstar's site.

### "N owned excluded" on the Social tab
**Before.** The Social tab dropped the brand's own posts without saying so. A reader couldn't tell
"we left these out" from "we never found them".

**Now.** The post count shows the number left out, the same way the News cards do.

### Adverse Media Monitor (Oviva)
**Before.** The monitor flagged a Reddit post titled "Oviva positive experience so far". The post
mentions a wait and a lost referral along the way, and the monitor treated those as complaints.

**Now.** The monitor's instruction tells it to judge each post as a whole. A post whose author
presents a positive or mostly positive experience is not flagged for a minor problem mentioned in
passing.

## Release notes (copy-ready)
- Social sentiment now excludes posts from the brand's own accounts, as News already did.
- The Social tab shows how many of the brand's own posts were excluded.
- Competitor sentiment is corrected the same way, so comparisons are like for like.
- The Oviva Adverse Media Monitor no longer flags positive posts that mention a minor problem.

## Demo / walkthrough
1. Open Brand Watcher → Social for Oviva, with a 30-day window.
2. The Posts card reads "last 30d · 39 owned excluded".
3. Instagram no longer appears as the best-perceived network.
4. "Posted vs seen" shows the outside view: −28 by posts, −31 by reach.

The "owned excluded" line is on Oviva and on our internal site. The Sunstar and Wiley sites
already exclude own posts from their numbers, but they don't show the count yet.

## Positioning notes
Social listening tools often mix a brand's own channel output into its sentiment. That makes a
brand look better liked than it is, and makes a competitor with many regional accounts look better
still. Separating the company's own voice from outside opinion is a concrete answer to "how do you
know this score is real?"

## Limits and what's next
- **Hand-kept list.** The list of company-run accounts is checked by hand. A new regional or
  campaign account counts as outside opinion until someone adds it. Registering an account also
  moves its earlier posts out of the score.
- **Handles are not proof.** Many handles that contain a brand name belong to other businesses: an
  estate agent called Pearsons, a pub whose Instagram handle is @sagepub, a separate stationery
  company called Sun-Star. We left all of these in as outside voices.
- **Small shifts elsewhere.** Brands with hundreds of outside posts move by only a few points.
  Colgate moved the most, by 6 points.
- **Monitor untested.** The monitor change is a wording change to its instruction. Its next run on
  25 September is the first real test.
- **Count not shown everywhere.** The "owned excluded" count is not yet shown on the Sunstar and
  Wiley sites.
