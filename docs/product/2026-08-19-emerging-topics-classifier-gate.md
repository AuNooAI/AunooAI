# Emerging Topics: the bar the "ongoing topic" label has to clear before it comes back
_2026-08-19 · internal — engineering and operations. Not for external distribution._

**Audience note.** There is almost no customer-facing surface here. This session built internal
safety tooling: a restart procedure that cannot cut off a running scan, a set of health checks
on a search index, and the pass/fail test that decides whether a switched-off feature may be
switched back on. Customers see none of it directly.

Two things do reach customers, and both are covered below: two scheduled scans were lost, and
we can now say precisely what has to be true before the "ongoing topic" label returns. The
customer-facing half of this work was written up in
`2026-08-19-emerging-topics-reliability.md`; this file carries the rest.

## What shipped

- A drain-and-restart tool. Restarting the service can no longer cut off a scan that is
  part-way through.
- Health checks on the second search index, so we can say whether it is fit to make decisions
  rather than assuming it is because it is big.
- A written pass/fail test for turning the "ongoing topic" label back on, with numbers attached.

## Why it matters

**Restarting used to be able to kill a scan in progress.** The old procedure was "look for
running scans, then restart". Between the looking and the restarting there is a gap, and a scan
can start inside it — or one can already be running and be missed. That is not a theoretical
risk: it happened twice today, and a customer's scheduled scan was cut off both times.

The replacement removes the gap rather than narrowing it. New scans are blocked and existing
ones are waited for in a single step, so there is no moment where one can slip through. Who
feels it: operators doing deploys, and any customer whose scan would otherwise have been cut
off mid-run.

**"It has lots of data" was not a health check.** Turning the "ongoing topic" label back on
depends on a second, stronger search index. We were treating that index as usable because it
held about half a million entries. Checking it properly showed that it covers 76% of one
customer site's articles and 93% of another's, that neither has the lookup structure that makes
searches fast, and that neither has been updated for over a month — 37 days on one site, 45 on
the other.

That last figure is the important one. The label asks "was this topic covered in the 60 days
before now?" With the index over a month stale, roughly half that period is not indexed at all,
so the honest answer is that we cannot yet judge the feature fairly. Who feels it: nobody today,
because the label is already switched off. It matters because it stops us switching it back on
against evidence that was never going to be sound.

**The bar for switching it back on is now written down.** Before the label can set anything, the
stronger index has to be judged against a prepared set of topics with known answers, per
customer site, never pooled:

- When it says a topic is "ongoing", it must be right at least 95% of the time.
- It must never say "ongoing" about a made-up topic. Not rarely — never.
- It needs at least 100 judged decisions spread over at least seven days, so one unusual day
  cannot carry the result.

The strictness is deliberate and one-sided. A topic wrongly marked "ongoing" is dropped from
new-topic alerts, so the customer is never told about it, and nobody notices an alert that does
not arrive. Being wrong in the other direction only means an extra topic appears.

## Release notes (copy-ready)

**Internal only — do not send to customers.**

- Deploys no longer interrupt an emerging-topics scan that is already running.
- Added health checks on the secondary search index: coverage, model version, dimensions,
  freshness, and lookup structure.
- Defined and implemented the acceptance test for re-enabling the "ongoing topic" label.

## Demo / walkthrough

None. There is no UI for any of this. The tools are command-line only and live in `scripts/`.

## Positioning notes

None. Nothing here changes the product story or answers a competitor question. The one
customer-facing claim it supports is the one already made in the reliability writeup: when the
system cannot tell, it says so instead of guessing.

## Limits and what's next

**The "ongoing topic" label stays off, and there is no date for its return.** It cannot be
judged until the second search index is brought up to date, and updating it is a separate
decision that has not been taken.

**Evidence gathered before that update should not be used.** The two sites are recording what
the stronger index *would* have decided, but against an index missing the last five to six
weeks. Those recordings will under-report prior coverage, so judging the feature on them would
flatter it in one direction and penalise it in the other. The seven-day clock should start after
the index is current, not now.

**Two scans were lost today** on two customer sites, in the deploy that introduced the tool
meant to prevent exactly that. Scans already running when it was installed were invisible to it.
Both were recorded as cancelled rather than silently vanishing, and the next scheduled scan ran
normally. The tool now refuses to proceed when it finds a recent scan it cannot account for,
instead of assuming it is safe to ignore.

**The tooling has no interface.** Running a drain or the acceptance test means a command line
and server access. That is appropriate for how rarely they are used, but it does mean neither is
self-service.
