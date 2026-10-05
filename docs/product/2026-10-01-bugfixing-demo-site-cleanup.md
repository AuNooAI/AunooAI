# Demo site clean-up: leftover Panaya vendors and an empty topic removed
_1 October 2026 · Brand Watcher and topics on bugfixing, our own demo site_

Audience note: bugfixing is our internal demo and development site. No customer sees it, so
none of this is for external distribution. It matters because we demo from this site.

## What shipped
- The six Panaya demo vendors, UiPath among them, no longer appear in bugfixing's competitor
  views.
- The Harm Reduction topic is gone. Nobody knew who had added it, and it couldn't produce an
  article.

## Why it matters
**Wrong companies in a demo.** On 21 September we built the Panaya demo market on this site
and then moved it to Panaya's own site. Six of its vendors stayed switched on here. Because of
that, UiPath and Tricentis showed up as competitors in an AI security demo.
- *Before:* deselecting UiPath in the brand picker didn't help. In Brand Watcher, the picker
  chooses the brand you look at, and every other switched-on brand counts as a competitor.
- *Now:* the six are switched off, the same as the four peers that were already off. The
  competitor views show only the security vendors.
- *Who notices:* whoever runs a demo from bugfixing.

**A topic that only collected noise.** Someone created Harm Reduction through the UI on
23 September.
- *Before:* the topic had no label lists, so the AI step could never analyse its articles. Its
  keywords were broad ("NGO", "policy", "insurance"). It collected 1,877 articles in six days,
  and none was usable.
- *Now:* we deleted the topic, its keywords and its articles, and kept backups.
- *Who notices:* nobody directly. It stops wasting relevance scoring once the news feed is back.

## Release notes (copy-ready, internal only)
- bugfixing: Panaya demo vendors switched off; they no longer show as competitors.
- bugfixing: Harm Reduction test topic deleted.

## Demo / walkthrough
None. These are removals. Refresh Brand Watcher's competitive views to confirm UiPath has gone.

## Positioning notes
None.

## Limits and what's next
- **Brand Watcher has no way to hide a competitor without switching the brand off.** If someone
  wants to compare against only some brands, that needs a product decision and a UI change.
- **Some screen creates topics with no label lists.** This is the second such topic in two days,
  after wileytest's intralogistics topic. Every one fails silently. We haven't found the screen
  yet, and it should either fill in default labels or refuse to save.
- **Harm Reduction still shows until the site restarts.** The restart is waiting for a moment
  with no active users.
