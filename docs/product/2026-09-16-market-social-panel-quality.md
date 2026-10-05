# The Social panel on the public market page now shows people, not adverts
_16 September 2026 · aisocnews.com front page, Social section_

## What shipped
The "What practitioners are saying" panel on the public AI SOC market page now
shows six different people saying six different things. Before this change it
was showing adverts, job questions, automated reposts and stock tips.

## Why it matters

**The panel had stopped doing its job, and it was the most visible part of the
page to get wrong.** Every other section on the market page reports on
companies. This one reports on the people who buy from them, which is the part
a reader cannot get from a press release. On the morning of 16 September the
six posts on display were: a promotional advert for an adult content site, two
posts from one graduate asking which job offer to take, two automated reposts
from the same news robot, and a stock tip. None of them was a practitioner and
none of them was about this market.

**One advert got in by matching a vendor's name inside a discount code.** The
vendor 7ai has a short name with a digit in it. The advert offered a discount
under the code "7AI-N5AI". Our name matching saw the vendor's name, correctly
by every rule it had, and pulled the advert into the market as coverage of
that vendor. It then led the panel. We now recognise a reference code for what
it is and ignore names found inside one. A hyphenated phrase like
"7AI-backed" still counts as a mention, because the second half is an ordinary
word.

**The other five were classes of post, not one-offs.** Rather than blocking
the individual posts, we added rules for the classes they belong to: consumer
promotion, somebody asking which job to take, automated accounts restating
headlines, share-price chatter, and sales approaches asking the reader to get
in touch. Each rule was measured against 90 days of real posts from this
market before we kept it, and each one was read by a person. Across 587 posts
the new rules turn away 22.

**The rules are deliberately narrow, because the cost of overreach is the
posts we want.** A practitioner asking "what's the best way to evaluate AI SOC
solutions in 2026, our alert backlog has crept up" looks a lot like somebody
asking for career advice if you match on loose phrases. It is exactly the post
the panel exists for. The rules are written to keep it, and there is a test
that fails if a future change starts catching it.

**The panel also no longer repeats itself.** One account can no longer hold
several of the six slots, and one line of marketing copy posted from three
different handles now appears once. Nothing is hidden: the panel's own full
page still lists every post in date order.

## Release notes (copy-ready)
- The Social panel on the market page now shows six different voices rather
  than repeating the same account or the same sentence.
- Adverts, job-hunting questions, automated news reposts, stock tips and sales
  pitches no longer appear among practitioner posts.
- Fixed a case where a vendor's name matched inside an unrelated discount
  code, which credited that vendor with coverage it had nothing to do with.

## Demo / walkthrough
Open aisocnews.com and scroll to **Social**, under Thought leadership. The six
posts should each come from a different account. Click **All N →** to see the
complete list for the period, which is unchanged.

## Positioning notes
This is the accuracy story, not a feature. The market page's claim is that
somebody has read the market rather than aggregated it, and a panel of adverts
falsifies that claim in one glance. It is also the kind of thing a prospect
checks first, because it is the only part of the page they can verify against
their own feed.

## Limits and what's next
Three of the six posts now on the panel are still automated accounts reposting
press releases rather than practitioners with an opinion. They are on topic
and factually fine, so no rule turns them away, but they are thin. Telling a
person's post from a syndication account's is a judgement about the account,
not about the words, and the honest way to do it is either a reviewed list of
known aggregator accounts or a cheap model call over each post. Neither is in
this change.

The rules are also specific to what has actually appeared in this market. A
new class of junk will need the same treatment: look at the posts, write the
rule, measure it against the corpus before keeping it.
