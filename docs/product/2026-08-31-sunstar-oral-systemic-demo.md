# A demo site for Sunstar, and news collection that finally reads other languages
_2026-08-31 · sunstar.aunoo.ai (prospect demo site) + collection fixes on every site that uses TheNewsAPI_

**Audience note.** Sunstar is a prospect, not a customer. The site is a working example built
for a demo on 3 September; nothing here should be sent to Sunstar as-is, and "case study" is the
word if it is ever described externally.

## What shipped

- A dedicated site, sunstar.aunoo.ai, that watches one question: how the link between oral
  health and whole-body health is understood in Japan, the United States, Germany and France,
  seen from three sides at once — what researchers publish, what Sunstar and its competitors
  say, and what patients and consumers discuss online.
- Topics that collect in their own language. A Japanese topic now reads the Japanese press, a
  German one the German press. Before today every topic on every site asked the news services
  for English only.
- A fix to TheNewsAPI collection: we had been searching headlines and blurbs only, never the
  article body, and the setting that should have added the body used a field name TheNewsAPI
  ignores. Japanese coverage of periodontal disease measures 8 articles a month the old way and
  114 with the body searched; German 4 against 23. Turned on for the Sunstar site; other sites
  keep their current setting until someone decides the extra volume is worth the analysis cost.
- Competitor watching for Sunstar, Lion, Kao, Colgate-Palmolive and P&G Oral-B, with
  Japanese-language watching for the three Japanese companies.
- Research summaries, explanations and tags now come out in English whatever language the
  article was written in.

## Why it matters

**Before:** a market-comparison question could only be answered from English sources, which for
Japan, Germany and France means almost nothing. Even in English, TheNewsAPI returned a fraction
of what it held because we asked it to search a field it does not have.

**Now:** on the first collection passes the site holds 120 enriched research papers, 32 US
articles, 9 Japanese and 4 German, all classified into the same 13 dental-health categories.
The Japanese set already shows a frame the others lack — "oral frailty" in ageing — which is
the kind of market difference the demo exists to surface. Lion's and Sunstar's own news appears
only through the Japanese groups: Clinica topping a repeat-purchase ranking, NONIO leading
dental-product sales, Sunstar's Ora² Feels launch. In English those companies looked silent.

Who feels it: the analyst preparing Thursday's walkthrough. Other sites gain the same coverage
only when their search setting is widened.

## Release notes (internal only)

- New site sunstar.aunoo.ai: seven topics, five brands, Japanese-language brand watching, two
  RSS feeds, Bedrock-only models.
- Topics can now set a collection language and country (database columns; no settings screen yet).
- TheNewsAPI collection can now search article bodies. On for sunstar; the code is on wileytest and wbm but their setting still limits searches to titles and descriptions.
- Research collection retries when Semantic Scholar rate-limits us instead of returning nothing.
- Analysis output is English regardless of source language.

## Demo / walkthrough

Not yet rehearsed. The spec's run of show: Explore with the seven topics; Japan against the US
on the periodontal–systemic category, then oral frailty as the Japan-only frame; Consensus on
the research topic next to the US topic; the Auspex answer to the periodontal–cardiovascular
question; regenerative dentistry with Emerging Topics; the five brands in Brand Watcher.
Minimum data before a view is shown: 40 enriched articles per market, 60 research, 25 consumer.

## Positioning notes

The proposition to Sunstar is the three-way comparison across four markets in four languages,
and the ability to say where public or commercial narratives run ahead of the research. The
language fix is what makes the four-market claim true rather than aspirational.

## Limits and what's next

- France and Germany are thin even with body search: France 15 collected, 2 approved (both
  Futura-Sciences on Alzheimer's and oral bacteria); Germany 33 collected, 3 approved. Say so on
  the call rather than pad it. Japan reached 131 collected, 9 approved.
- Sunstar's own English coverage is empty in the last 30 days; its news is Japanese.
- Semantic Scholar still runs without an API key and hits rate limits; the application must be
  submitted by hand (captcha). The research leg is usable but incomplete until then.
- The consumer view is scored on a cheap model: 1,234 posts scored, 226 relevant, most of them
  from Bluesky, Instagram and TikTok; Twitter contributed 7.
- Not built: the perspective-gap report that puts researchers, companies and consumers on one
  page per category; LinkedIn collection; any new dashboard. Reasonable week-two items.
- Brendan Jennings' own questions have not arrived; the two example questions from the 21 August
  email stand in.
