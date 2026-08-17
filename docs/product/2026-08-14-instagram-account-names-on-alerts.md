# Instagram and Reddit posts in alerts now name the account
_2026-08-14 · Observer agent alert emails and online signal reports_

## What shipped
Alert emails and online signal reports now show the account behind a flagged Instagram
or Reddit post. Instagram cards get a clickable @handle that opens the account's
profile, instead of the generic label "Instagram post". Reddit cards, which previously
showed only the subreddit, now lead with the posting account (u/name, linked to the
user's profile) with the subreddit still shown and linked alongside.

## Why it matters
When a monitoring agent flags a hostile post, the first question is "who posted this?"
For X, Bluesky, and TikTok the answer was already on the card. For Instagram it wasn't:
the card said only "Instagram post", so an analyst had to open the post itself to see
the account, and had no direct link to the poster's profile to gauge reach or history.
Reddit showed the community but not the account, so two posts by the same account in
different subreddits looked unrelated — which hides exactly the pattern that matters
when one account is spamming or campaigning across communities. Now every platform's
card names the account and links to it. This also applies retroactively — reports
generated before the fix show the account names the next time they are opened, because
the page is rendered fresh each time.

## Release notes (copy-ready)
- Alert emails and signal reports now show the Instagram account name (@handle) for
  flagged Instagram posts, linked to the account's profile.
- Reddit posts in alerts now show the posting account (u/name, linked) alongside the
  subreddit, so repeat posters are visible across communities.
- Older saved reports pick this up automatically when reopened.

## Demo / walkthrough
Open any signal report that includes an Instagram or Reddit post (email link or the
online report page). The source card header now reads, for example,
"@erik.jia · Instagram · view post ↗" or
"u/VSJBSHS · r/ONLINECLASSSOS · Reddit · view post ↗" — the account opens the
profile, the subreddit opens the community, "view post" opens the post.

## Positioning notes
None as a standalone item — this closes a consistency gap in the existing source
attribution rather than adding a new capability.

## Limits and what's next
The account name comes from our own collected copy of the post. If a post reaches an
alert without its author metadata, the card falls back to the previous behaviour
rather than failing: "Instagram post" for Instagram, subreddit-only for Reddit. In
the data we checked (wbm and wileytest customer sites), every collected Instagram and
Reddit post had the author recorded, so the fallback should be rare.
