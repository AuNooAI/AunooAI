# The engineering changelog was emptied four times in one day; cause found, guard added

_16 October 2026 · internal engineering process only_

**Audience note.** This has no product surface. No customer saw it, no customer-facing system
was touched, and nothing here is for external distribution. It is written so the incident and
its guard are on record next to the engineering entry in `docs/changes.md`.

## What shipped
- The documentation step that every Claude session follows now prepends to the changelog
  through a scratch file and checks the file grew, instead of a one-line write that silently
  emptied it.
- A written explanation of the fault, for sessions that write the changelog without that step.

## Why it matters
Before: four times on 16 October, a session documenting its own work ran a one-line Python
prepend that opened the changelog for writing before reading it. The file was left holding only
the newest entry. The committed history was intact every time, because that session staged the
file from the last commit rather than from disk, so the loss was hidden until another session
read the working copy and found the entries it had written that morning gone.

After: the documentation step builds the new file beside the old one, copies it over, and
confirms the line count went up. If it did not, the step says how to restore from the last
commit and re-add what was uncommitted.

Who feels it: whoever reads `docs/changes.md` to find out what changed and why. The changelog
is the one durable record for work that lives only in a checkout, so an emptied working copy
can lose the only account of a fix.

## Release notes (internal only)
- `docs/changes.md` was emptied at 09:57, 12:15, 13:55 and 14:49 CEST on 16 October 2026 by a
  prepend one-liner in another session. Restored from HEAD each time it was noticed.
- The session-docs skill now prepends through a scratch file and checks the file grew.

## Demo / walkthrough
None. There is no UI; the change is in a skill file outside the repo.

## Positioning notes
None. Internal process.

## Limits and what's next
- The guard lives in the skill file on this host, not in the repository. A session that
  already holds the old one-liner in its context keeps using it, which is how the fourth run
  happened after the patch. It stops when those sessions end.
- Nothing prevents a future session from writing the changelog without the skill. The memory
  note is the only protection there.
- The 13:55 run was not inspected before the 14:49 run overwrote it, so we do not know what
  the working copy held between those two.
