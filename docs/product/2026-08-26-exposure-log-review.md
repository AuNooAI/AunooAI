# What the access logs can and cannot tell us about the login gap
_2026-08-26 · No product surface. Written for the decision about whether to tell a customer._

## Audience note — internal only

Nothing here ships and nothing here is customer-facing. This document exists for one reason: to
put evidence behind the question left open yesterday, which is whether the login gap on eight
customer sites needs telling anyone. It should not be forwarded to a customer as written, and no
part of it is release copy.

It does not make the decision. It sets out what the logs show, and — more importantly — what they
cannot show.

## What shipped

Nothing. No code, settings or data changed today. This was a review of the web server's access
logs.

## Why it matters

**The evidence, as far as it goes, is reassuring.** Every successful request to the affected
addresses came from one of two places. One is a signed-in operator using a Chrome browser, who made
91,601 requests over the period and whose pattern matches somebody opening the settings page. The
other is this server itself, from the checks I ran yesterday. No script, crawler or scraper ever
got a successful response out of those addresses.

**The problem is how little of the period the logs cover.** The web server keeps 14 days. The gap
was open from January 2025, so the logs cover about 2.5% of it. The honest sentence is "we see no
misuse in the 2.5% we can look at". That is not the same as "nothing happened", and it would not hold
up if anyone pressed on it.

Nothing from the other 97.5% is recoverable. There is no archive.

**This is cheap to fix and worth fixing today.** The entire log directory is 9.4 MB and the disk has
1.8 TB free. The 14-day limit buys nothing and is not a decision anyone made. Extending it means
that the next time somebody asks "was this accessed", the answer is a query rather than a shrug. I
have not changed it, because it is an infrastructure change nobody asked for.

**One thing nearly became a false alarm, and it is worth knowing about.** Outside scanners
constantly probe this server for settings files. 781 of those probes got a "success" response,
including 51 requests for a file called `.env`, which is where a system's passwords normally live.
Read from the log alone, that looks like a serious leak. It is not. Two of the sites are built so
that any unrecognised address returns the application's home page, which counts as a success even
though no file was found. I confirmed this by requesting the file directly on four sites: two
correctly said "not found", and two returned the home page. No settings file was ever served.

## Release notes (copy-ready)

None. Nothing shipped, and nothing here should reach a customer without a deliberate decision.

## Demo / walkthrough

None. There is no interface to this.

## Positioning notes

None, and deliberately. This is evidence for an internal decision about disclosure. Presenting it
as anything else would be a mistake.

## Limits and what's next

**The decision is still open and is not mine to make.** What supports not notifying: no sign of
misuse, and the affected addresses returned internal settings and the list of topics we track, not
customer personal data. What argues for caution: we can only see 2.5% of the period, and one of the
eight affected sites belongs to a paying customer. If it helps, I can list exactly which kinds of
data were reachable so the decision rests on specifics rather than on the phrase "internal
settings".

**Log retention is the fix I would do first.** One line, no risk, and it stops this exact question
being unanswerable next time.

**Three status addresses now need a login** and will report failures if any outside monitoring
checks them. Reverting is one line per site. This still needs a yes or no.

**One reporting oddity worth knowing.** The automated test suite reports either 98 or 99 failures
depending on the run, because one pre-existing test is unreliable. Every one of those failures
predates this week's work, and the failure list is identical between runs of the same count. It
matters only because it makes the suite a slightly noisy signal for whoever looks next.
