# A tracked company can be searched under the name the press actually uses
_2026-09-23 · Market Monitor — how collection keywords are generated_

**Audience note: internal.** Nothing here changes a screen. It changes whether the system finds
news about a company we said we were tracking, which a customer would eventually feel as an
absence rather than as a visible fault. Not for external distribution.

## What shipped
Two fixes to how the system turns a tracked company's name into a search term.

An ampersand in a company's name is no longer deleted. A company can now be given a separate
"search as" name, for when the press writes the brand differently from how our reports name it.

## Why it matters
We name a company one way for a reader and search for it another way, and until today the
system only had one name for both jobs.

Sunstar's new oral-care market tracks a company we call "P&G Oral-B", which tells a reader who
owns the brand. Two things then went wrong. The ampersand was stripped, producing a search for
"PG Oral-B". And even spelled correctly, "P&G Oral-B" is not what anybody writes: in sunstar's
own 26,766 collected articles it appears **0 times**, against **380** for "Oral-B".

So one of six tracked companies was being searched for under a phrase that returns nothing. The
market would have looked like it was working — thirteen search terms, running daily — while
never finding a single story about that company.

**The failure mode is what makes this worth writing down.** Nothing errors. No alert fires. A
keyword that matches nothing looks exactly like a company that had a quiet month. We only found
it because the setup was run against a corpus we could check the terms against.

The same trap is waiting for any company with an ampersand in its name — Procter & Gamble,
Johnson & Johnson, AT&T, H&M — and for any company whose registry name is not its press name.

## Release notes
Internal only — no customer-facing change.

## Demo / walkthrough
None. No screen shows a search keyword.

## Positioning notes
None. This is correctness in a step no customer sees.

## Limits and what's next
**The override is manual and per company.** Somebody has to notice that a company's name and its
press name differ, and set it. Nothing detects the mismatch automatically, and the detection is
the hard part — a keyword returning nothing is indistinguishable from a quiet company without
checking the corpus.

**It is set for exactly one company today**, P&G Oral-B on sunstar. No other market has been
audited for the same problem. The check is cheap: compare each generated keyword against the
tenant's own articles and look for zeros.

**A worthwhile follow-on** is making that check part of setup rather than a thing someone thinks
to do — report any generated keyword with no corpus matches at the time the market is configured,
when it costs nothing to fix. That is a few hours of work for an AI.
