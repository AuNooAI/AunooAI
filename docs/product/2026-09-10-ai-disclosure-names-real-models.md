# AI disclosure footer now names the models that actually ran
_2026-09-10 · Every dashboard footer that carries the "AI Technology Disclosure" line (Brand Watcher, Explore insights tabs, Auspex, Forecast Tracker)_

## What shipped
The disclosure line at the bottom of each dashboard now lists the AI models that ran on that customer site in the last 30 days, most-used first, instead of the first four names from the model picker.

## Why it matters
Before, every site showed the same four Claude names in its disclosure, because the footer copied the head of the model picker and the picker puts Claude first. On the Sunstar site the article analysis runs on Kimi K2.5 and the relevance scoring on Nova Lite, and Claude Opus 5 has never run there at all. The notice was naming a vendor that did no work and hiding two that did.

The EU AI Act Article 50 notice exists so a reader can check what produced the content. A wrong model list defeats that. Now the line is derived from the site's own call log, so an operator, an auditor or a customer reads what actually ran. Sunstar's footer reads "Nova Lite, Kimi K2.5, Claude Haiku 4.5, Claude Sonnet 4.5", which is the true picture.

The change touches no analysis, no scoring and no report content. Only the disclosure text changes.

## Release notes (copy-ready)
- The AI Technology Disclosure footer on dashboards now names the models that ran on your site in the last 30 days, most-used first.
- Sites whose analysis runs on Kimi or Nova now say so; the footer no longer defaults to a Claude-only list.

## Demo / walkthrough
Open any dashboard tab, for example Explore → Brand Watcher, and scroll to the bottom. The "AI Model:" field in the grey disclosure box shows the live list. Reports and exports that already record their own model are unchanged.

## Positioning notes
None. This is a correctness fix to an existing compliance feature, not new capability.

## Limits and what's next
- The list is site-wide, not per dashboard. Brand Watcher's footer lists models used anywhere on the site, including article analysis and translation. A per-feature breakdown would need the call log's use-case column surfaced, which is a follow-on.
- The window is 30 days. A model retired 31 days ago drops off; a model tried once with a single successful call stays on.
- Exports that hardcode "site-configured large language models" (some PDF and Markdown exports) still say that. They were not part of this change.
- Sites without a call-log table fall back to the configured model list, which may again overstate which models ran.
