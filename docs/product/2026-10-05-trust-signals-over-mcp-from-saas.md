# Trust Signals for any article, from the assistant you already use
_2026-10-05 · MCP connectors on the Aunoo sites (bugfixing today) and on saas.aunoo.ai_

## What shipped
- An Aunoo site connected to Claude, ChatGPT or Cursor can now ask for the five Trust Signals
  on any article it holds: who the outlet is, how its claims hold up, whether the text looks
  machine-written, how the story spread, and who owns the outlet.
- On saas.aunoo.ai the same ratings are available for articles named by web address, not only
  for articles saas collected itself.
- The saas connector now hides low-relevance articles and reports a failed tool as a failure,
  the way the Aunoo sites already did.
- Connector tools can return images and other rich content on both products.

## Why it matters
**Before**, Trust Signals lived only in the saas app, and only for articles saas had collected.
An analyst on an Aunoo site reading a Guardian piece through their assistant had no way to ask
"is this outlet reliable, and who owns it?" without leaving the conversation. The site's own
copy of the outlet ratings was nearly empty: of the 3,000 most recent articles on the test site,
108 carried a rating.

**Now**, the assistant asks the site, the site asks saas, and the answer comes back in the same
turn. Source and Owner are rated for any outlet in the Media Bias/Fact Check record, which covers
8,221 outlets. The analyst sees a rating and the reason behind it: "Factual reporting: Mixed",
"Owner: Guardian Media Group (United Kingdom)". Who feels it: analysts and brand managers using
the connector, and the operator, who keeps one trust database instead of copying it to every site.

**The honest part is kept.** A rating that was not measured says so. For an article saas has not
collected, the claim check, the machine-writing check and the spread check read "not assessed",
with a line explaining why and what to call next. Nothing reads "clean" because nobody looked.

## Release notes (copy-ready)
- New connector tool on Aunoo sites: `get_trust_signals`. Pass one or more article links and
  get the five Trust Signals with reasons.
- saas.aunoo.ai connector: Trust Signals now work for any article link, not only articles in
  the saas corpus.
- saas.aunoo.ai connector: articles below the site's relevance floor no longer appear in tool
  results, and a tool that fails now says so instead of returning an empty success.
- Connector tools can return images on both products.

## Demo / walkthrough
In a Claude conversation connected to the site, ask for recent articles on a topic, then ask
"what are the trust signals for the first one?". The assistant calls `get_trust_signals` with
the article's link. For a Guardian article today the answer was Source "Mixed", Owner "Guardian
Media Group", and three stations marked not assessed. There is no page in the site's UI for
this; it lives in the assistant.

## Positioning notes
This is the first feature where a saas capability serves the Aunoo sites as a service rather
than being copied into them. It fits the plan to retire the saas UI and keep saas as the trust
and verification engine behind every site. For a buyer, the point is that outlet reputation and
ownership arrive inside the research conversation, cited, instead of as a separate lookup.

## Limits and what's next
- Live on bugfixing only, and rating against the saas development instance. Pointing it at saas
  production needs one key to be issued and the site restarted; the steps are in the engineering
  notes.
- Claims, Origin and Spread are only measured for articles saas itself has collected. For the
  test site that is about one article in fifteen. A claim check on any other article means
  calling saas's `validate_article` with the link, which is paid work and not done automatically.
- Outlets published under mirror or regional domains may be unrated even when the parent outlet
  is rated. An RT German mirror came back "Unrated" today.
- Answers are cached for an hour per link on the site, so a freshly validated article can take
  up to an hour to show its new claim verdicts through the connector.
- The other Aunoo sites do not have the tool. Adding it is a copy of three files plus two
  environment variables per site, once a prod key exists.
- The site's own outlet-rating columns are still 96% empty. The same saas endpoint can fill
  them during the AI analysis step; that change has not been made.
