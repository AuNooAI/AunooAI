# The Add-Topic wizard now suggests keywords that find your topic, not the whole world's news
_2026-09-08 · Add-Topic wizard (Gather and Explore), keyword collection_

## What shipped
- Keyword suggestions are specific to the topic. For a Swiss elections topic the wizard now proposes "Swiss election disinformation" and "Desinformation Schweiz", not "disinformation".
- Every suggested keyword is shown. The wizard used to keep only the first three per list and silently drop the rest.
- The "regenerate" button follows the same rules as the first suggestion.
- The future signals you enter in the wizard are saved. Until today they were lost on save.
- Keywords up to 60 characters are kept whole. The old 30-character limit cut "Switzerland election interference" down to "Switzerland election".
- "Check now" on a topic group in another language now searches in that language.

## Why it matters
An analyst setting up a topic gets the keywords the collectors run with. A bare word like "disinformation" matches every article on earth that contains it, so the topic filled up with fraud press releases and a Telegram outage, and the AI relevance check threw all of it away. That cost collection quota and AI spend for nothing, and the analyst saw an empty topic.

The wizard's model was already suggesting the right terms. The screen was discarding them. Now the analyst sees the full list, ordered most specific first, in the languages the local press uses, and removes what they do not want.

Future signals are the "what might happen" statements the forecast views build on. A topic created through the wizard had none, so those views started empty. They now carry what the analyst typed.

Operators running a German or French topic group could press "check now" and get nothing, because that button searched in English. It now uses the group's language, the same as the scheduled run.

## Release notes (copy-ready)
- Add-Topic wizard: keyword suggestions are now specific to your topic, and the full list is shown.
- Add-Topic wizard: future signals entered in the wizard are saved with the topic.
- Keywords can be up to 60 characters.
- "Check now" on a topic group honours the group's language.

## Demo / walkthrough
Gather tab, "Add Topic". Enter a name and a short description, continue to the keywords step. The lists are longer than before and every entry names the topic's country, body or event. Click "Regenerate" to see the same rule applied again. Finish the wizard, open the topic in Forecast, and the future signals are present.

## Positioning notes
None that changes the story. This makes the existing "set up a topic in minutes" claim true for topics outside the English tech press, which is where it had been failing.

## Limits and what's next
- The wizard still cannot set a group's language or which collectors it uses. For a German or French topic an operator sets those in the database or the group settings dialog after the wizard.
- Exclusion keywords (the "-term" entries) are not applied when collecting. The collectors strip them and nothing filters afterwards. Anchoring each keyword is the working substitute; a real exclusion filter is the obvious follow-on.
- Swiss-anchored German and French phrases only return results when the article body is searched. That is switched on for the bugfixing site; other sites still search title and description only, which is a cost decision per site.
- The relevance check judges articles against the topic description. A description about the 2027 election rejects coverage of the current neutrality referendum, even when Russia is promoting it. Widen the description if that coverage is wanted.
