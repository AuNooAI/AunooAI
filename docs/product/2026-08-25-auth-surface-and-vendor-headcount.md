# Login now required everywhere, and unknown staff counts stop reading as zero
_2026-08-25 · Market Monitor vendor tables; platform-wide login checks on five customer sites_

## Audience note — internal only

Most of this session has **no customer-facing surface**. It closed a set of web addresses that
answered requests without asking anyone to log in. A customer cannot see that work, and none of it
should be sent out as a release note or used as sales material. Announcing "we now check logins"
tells a reader that we previously did not.

One small part **is** visible: the Market Monitor vendor tables. That part is safe to describe to a
customer and is the only thing in the release-notes section below.

There is also a decision for Oliver in "Limits and what's next" about whether any of this needs
telling a customer. That is a judgement call and this document does not make it.

## What shipped

- **Vendor tables no longer show a staff count of zero when the count is simply unknown.** Seven
  vendors on the SOC Automation list showed "0 staff". They now show a dash, the same as any other
  missing figure.
- **The activity counts say which period they cover.** "Announced" and "Open roles" are now
  labelled "all time", because the summary strip above them covers a chosen number of days.
- **Every web address on five customer sites now requires a login**, apart from eleven that are
  meant to be open — the checks our own monitoring uses, the sign-in flow, and shared report links.

## Why it matters

**The zero staff count was a claim we could not support.** A reader comparing vendors saw "0"
next to real numbers and had no way to know it meant "the source did not give us this". Six of the
seven affected vendors have a public company page, so zero staff was not merely unhelpful, it was
wrong. Missing values now look missing. An analyst reading the table can tell the difference
between a small company and an unknown one.

We also caught a second problem before it reached anyone. Our monthly write-up compares a vendor's
current staff count against its starting figure. With a starting figure of zero, the first real
reading would have been published as that vendor hiring its entire workforce in one month. No
vendor was in that state yet, so nothing wrong was ever sent out — the fix is preventive.

**The undated counts were ambiguous.** The same screen showed a figure for a chosen period and two
figures covering all time, with nothing marking the difference. Anyone reading it as one period
would have drawn the wrong conclusion about how active a vendor is.

**The login checks matter to the buyer, not the analyst.** Nobody using the product will notice a
change. What changed is that internal data — the list of topics and categories we track, which
data providers a site has configured, model-training controls — could be read or triggered from the
open internet without signing in. That is the kind of thing a security questionnaire asks about,
and the honest answer before today was bad. It is now good.

The reason it went unnoticed for so long is worth understanding, because it will come up if anyone
asks. Every page in the product does require a login. A person using the product always sends
proof of their session, so every response looked correct. The gap was only visible to someone
asking without signing in first, which no customer and no test ever did.

## Release notes (copy-ready)

Customer-safe. Market Monitor only:

- Vendor tables now show a dash instead of "0" when a staff count is not available from the source.
- The "Announced" and "Open roles" columns are now labelled "all time", to distinguish them from
  the period-based figures above them.

**Internal only, do not send:** login checks added to 2,712 web addresses across ten customer
sites; hardcoded default administrator password removed; two signing keys no longer fall back to a
value published in the code.

## Demo / walkthrough

Explore → Market Monitor → click any figure on the overview to open the vendor breakdown. The
"Staff" column shows a dash for the seven vendors whose count is unknown, and the two right-hand
columns read "Announced (all time)" and "Open roles (all time)".

Nothing to demonstrate for the login work. Its correct appearance is no visible change at all.

## Positioning notes

None for the login work, and deliberately so. A fixed weakness is not a selling point, and
describing it invites the question of how long it was open.

The vendor table fix supports a claim we already make: that we show where each number came from and
say so when we do not have one. Competing vendor directories routinely present blanks as zeros.
Being able to point at a table that distinguishes "small" from "unknown" is a small, real
demonstration of that. It is a supporting detail in a demo, not a headline.

## Limits and what's next

**All ten sites are now done, but two of them are unverified.** pbm, ibaset and bwtemplate were
live and are confirmed fixed. pearson and interroll are switched off with their settings encrypted,
so they were not exposed and could not be tested — they have the code fix, but nobody has run them
with it. Whoever switches them back on should watch that they start cleanly; if a signing key is
missing from their settings file the site will refuse to start and say which one.

**A disclosure question needs deciding, and this document does not decide it.** On five sites,
internal configuration and topic lists were readable from the open internet without signing in,
and the server logs show outside scanners probing for configuration files on 25 August. Those
probes were refused. We have no evidence anyone read anything they should not have, and we did not
check the full request history to find out. One of the affected sites is a paying customer. Whether
that needs telling them, and whether the logs should be reviewed properly first, is Oliver's call.

**Monitoring may need adjusting.** Three status addresses that reported article counts and database
connection details now require a login. If anything outside the product polls them, it will start
reporting failures. Reverting those three is a one-line change per site.

**The wider tidy-up is untouched.** 225 web addresses are still registered twice in the code. This
is mostly harmless, but one of them means a future login fix could silently fail to take effect.
Worth a separate piece of work.

**The staff counts that are now blank are still blank.** We removed a wrong zero; we did not go and
find the real number. Seven vendors on the SOC Automation list have no staff figure, and six of
them have a public company page we could read one from.
