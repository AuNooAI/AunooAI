# Sharing an edited briefing by email works again
_2026-09-17 · Briefing Desk → Share via Email_

## What shipped
Sharing a briefing by email no longer fails when someone has edited that briefing's themes.

## Why it matters
Before: you opened a daily briefing, tidied up the AI-written themes, then clicked Share via
Email. The send failed and put a Python error on screen — `'str' object has no attribute
'get'`. Nothing was sent and nothing said why. Briefings nobody had edited sent fine, so the
failure looked random.

Now: the share goes through. The recipient gets the full briefing — summary, themes,
incidents, emerging topics, strategic considerations and articles — with the edited wording
in it.

Who feels it: the analyst who reviews a briefing before passing it on. That is the normal
way the Briefing Desk gets used, so the break sat directly on the main path out of the
product.

One existing briefing was affected, on the wileytest site: *Daily Briefing — 2026-09-17*.
We repaired it, so it shares correctly now. No other briefing on any site was affected.

## Release notes (copy-ready)
- Fixed: sharing a briefing by email failed with a technical error if the briefing's themes
  had been edited. Editing themes or strategic considerations now saves them in the right
  format, and sharing works.
- Briefings saved before this fix are read correctly rather than causing an error.

## Demo / walkthrough
Briefing Desk → open a briefing → edit a theme's title or description and save → Share via
Email → enter an address and send. The email arrives with the edited theme text in it.

## Positioning notes
None. This is a defect fix on an existing feature, not a change to what the product claims to
do.

## Limits and what's next
The fix covers themes and strategic considerations, the two fields whose save path had the
problem. We checked the other briefing fields — articles, incidents and emerging topics — and
they were already saving correctly, on every site.

The email error message still shows raw technical text when a share fails for any reason. We
did not change that in this pass. A plainer message would be the obvious follow-on, and is
small work.
