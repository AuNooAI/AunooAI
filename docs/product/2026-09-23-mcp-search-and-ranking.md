# Asking Aunoo a question in a sentence now works
_2026-09-23 · Claude/MCP connector, Brand Watcher Perception tab, search ranking across the product_

## What shipped

- **Questions asked as sentences return answers.** Connect Claude to an Aunoo site and ask "What
  do patients say about the Oviva NHS programme?" — you now get articles. Before today you got
  nothing back, with no error to tell you why.
- **The Perception tab stopped counting a brand's own blog as press coverage.** A company's
  website and press page are the company talking, not the press writing about it. They are now
  excluded from the media score, as they already were from the article counts.
- **Search results are ordered better, everywhere.** A ranking step that was supposed to sort
  results by how well they answer the question had not been running. It runs now.
- **A broken connector tool says it is broken.** Tools that fail now return an error instead of an
  empty list of results.

## Why it matters

**Sentence questions returned nothing.** The connector's two research tools looked for the whole
question as one literal phrase, the way a search box looks for an exact match. No article contains
the sentence "Oviva NHS weight management programme", so the answer was zero articles — while the
single word "Wegovy" returned six. Anyone asking a real question got silence, and the guided
"deep dive" research playbook is built on these two tools, so it returned empty research on every
customer site. Both tools now search by meaning and by the question's own keywords together. The
Oviva question went from 0 articles to 35.

*Who feels it:* every analyst using Claude against their Aunoo site, and anyone who ran the deep
dive playbook and assumed the corpus was thin.

**The Perception tab was flattering brands with their own marketing.** Oviva's media score read
+45 with no negative coverage at all, across 22 articles. Every one of those 22 was Oviva's own
blog or press page. A company never writes badly about itself, so the score was measuring its
marketing output, not its press. It now reads zero media coverage for that window, which is the
true answer and which matches what the dashboard's article counts had been saying all along. Noom
was affected too: three of its seven "media" articles were its own blog.

*Who feels it:* brand and comms teams reading the Perception tab, and anyone who compared a brand
against its competitors there.

**Result ordering had quietly stopped working.** Aunoo runs a second-pass ranking step that reads
each candidate article against the question and re-sorts. That step needs a slice of the shared
GPU, the GPU had filled up, and the step responded by switching itself off and leaving results in
rough similarity order. Nothing reported this. It now runs on the regular processor instead, using
a smaller model that turned out to both cost a fifth as much and rank better.

You can see the difference. "How are SOC teams using AI agents for alert triage?" used to lead
with an unrelated roundup of Google's AI plans; it now leads with an article about cutting triage
time in a security operations centre. "Which companies raised funding for security automation?"
now leads with an actual funding round. Asked in German, "Was sagen Patienten über die Oviva
App?" now returns patients posting about prescriptions and missing medication, where before it
returned Oviva's own marketing posts.

*Who feels it:* everyone who searches, in the product and through the connector.

**A failing tool looked like an empty database.** When the web-search tool failed, the connector
returned "no results" and recorded the call as successful. A customer could not tell a broken
integration from a quiet news week, and neither could we — the usage log showed nothing wrong.
Failures now come back as errors, carrying the reason.

*Who feels it:* customers debugging their connector, and support trying to reproduce a complaint.

## Release notes (copy-ready)

- Research questions asked in plain language now return results. Previously, questions phrased as
  sentences could return nothing.
- The Brand Watcher Perception tab no longer counts a brand's own website and press releases as
  media coverage of that brand.
- Search results are re-ordered by how well each article answers the question. This ranking step
  had not been running and is now active across the product.
- Connector tools that fail now return a clear error instead of an empty result.

## Demo / walkthrough

**Perception fix:** Brand Watcher → Perception tab. The media column for a brand that publishes a
busy blog (Oviva, Noom) now reflects outside coverage only. Cross-check against the Dashboard's
article counts — the two now agree, where they used to contradict each other.

**Search and ranking:** Explore → search, or ask through a connected Claude. Ask a full question
rather than keywords, and compare the top result against what the same question returned before.

**Connector:** connect Claude to a site and run the "deep dive" playbook. It previously produced a
research write-up citing nothing.

## Positioning notes

The connector story is "ask your own news corpus a question in plain language." Until today the
product did not actually do that — the two tools that carried the promise matched literal phrases.
This closes the gap between the demo script and the behaviour.

The Perception fix is a credibility point in a specific sales conversation. Buyers asking "how do
I know your sentiment scores are real?" now have a concrete answer: we exclude the brand's own
publishing, and we can show the number moving when we do. A media score that never goes negative
is a tell that a monitoring tool is counting press releases, and competitors' scores are worth
checking for the same thing.

## Limits and what's next

- **Web search is still down.** The connector's Google web search returns an authorisation error
  on every site. The shared Google API key is blocked for the Custom Search service, which is a
  setting in the Google Cloud console and cannot be fixed from our side. Until that is changed,
  that one tool does not work. Everything else in the connector does.
- **Search takes about five seconds.** The ranking step runs on the regular processor because the
  GPU is full, which costs seconds per search — roughly five when warm, twelve on the first search
  after a restart. Freeing GPU memory would cut that substantially. It is a speed cost, not a
  quality one.
- **Only the top 32 candidates get re-ranked.** Articles below that keep their previous order.
  Raising the limit costs proportional time.
- **Ranking the brand's own posts.** For "what do patients say", the English-language results still
  lead with the brand's own posts on some sites, because those posts genuinely discuss patients and
  the programme. The German example ranks real patient voices first. Worth watching whether
  "what do X say" questions need the brand's own content demoted.
- **Two internal sites (wbm, abm) run an older connector** that returns low-relevance articles the
  product's own screens hide. Not customer-facing today, but it should be brought up to date.
- **One brand site (wiley) has ranking switched off** by configuration. Its code is current; only
  the setting is missing.
