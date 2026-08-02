# Articles stop disappearing; alerts stop calling news "social"
_2026-07-29 → 2026-07-31 · Explore, observer/signal alerts, Briefing Desk, Add-Topic wizard, Foresight_
_Written 2026-08-02 as a backfill. Figures are those recorded when each change was made, not re-measured since._

## What shipped
- Articles that the AI analysed but couldn't file are no longer thrown away. They now appear in
  search, alerts, and reports instead of vanishing.
- Alert emails and online reports now tell news apart from social posts, and link to each
  correctly.
- Every AI-generated report, export, and email now carries a visible "AI-generated" disclosure
  (EU AI Act Article 50).
- The daily briefing uses the model the tenant is configured for, not whatever the browser
  happened to have selected.
- Topic setup suggestions work again, and the Foresight model list shows the models that
  actually exist.
- Several collectors stopped failing on ordinary inputs — publisher names containing "&"
  ("John Wiley & Sons", "Taylor & Francis") among them.

## Why it matters

**Articles were disappearing, permanently.** The analysis step checked the AI's answer against
14 exact field headings. If the model renamed one heading, numbered them, or left the title out,
the whole analysis was discarded and the article was left unfiled. Everything downstream —
signal alerts, Explore, reports — only retrieves filed articles, and nothing ever retried the
failures. So the article was not delayed; it was gone. On wileytest this was around 227 news
articles a day. Social posts take a different path and were unaffected, which is why alerts had
started looking like they were all Bluesky. The analysis step now tolerates the variations,
fails only on genuinely missing essentials, and a recovery script re-processes the backlog.
Separately, articles that hit a garbled response now get retried three times instead of failing
on the first miss. *Felt by: anyone who trusted an alert or a topic view to be complete.*

**Alerts called news articles "social posts."** Any match that wasn't Bluesky, X, or Reddit was
labelled "Social · view post" — which covered most matches, since most are news (nature.com,
cnn.com, arxiv.org). They now show the publisher and "read article." Instagram and TikTok are
recognised as the social sources they are. *Felt by: every recipient of an alert email.*

**AI-generated output was not labelled.** Reports, exports, dashboards, and emails now carry a
visible disclosure plus a machine-readable marker, from one shared source so it can't drift
between formats. Some UI copy that over-claimed human review ("reviewed and validated") was
softened to match what actually happens. *Felt by: any customer subject to the EU AI Act, and
anyone answering a procurement question about AI disclosure.*

**The briefing changed depending on who opened the browser.** Draft, incident detection, and
final synthesis now read the model from tenant settings, so the content and the "model used"
byline are consistent for everyone. *Felt by: briefing readers comparing notes.*

**Two Bedrock leftovers.** Topic-setup keyword suggestions had silently stopped using the LLM —
the code looked for an OpenAI model and every tenant had moved to Bedrock. And the Foresight
model dropdown listed roughly two dozen entries that all collapsed onto the same few real
models, with Claude labelled as GPT and Gemini. It now lists the five models that exist, with
honest names. *Felt by: anyone setting up a topic or choosing a model.*

## Release notes (copy-ready)
- Fixed: articles whose AI analysis used non-standard formatting were being discarded and became
  invisible to alerts, search, and reports. They are now processed correctly, and a recovery pass
  is available for previously affected articles.
- Fixed: alert emails and online reports labelled news articles as social posts. News and social
  are now distinguished, with correct links for each.
- Added: visible AI-generated disclosure on reports, exports, dashboards, and email, per EU AI
  Act Article 50.
- Fixed: daily briefings now use the tenant's configured model rather than the browser selection.
- Fixed: topic-setup keyword suggestions and the Foresight model list on Bedrock deployments.
- Fixed: collectors failing on publisher names containing "&", on multi-field searches, and on
  articles with empty content.

## Demo / walkthrough
Alert labelling is visible in any observer alert email or its online report — a news match now
reads *publisher · News · read article*. The AI disclosure appears in the footer of any generated
report or export. The Foresight model list is the model dropdown on the Foresight/trend
convergence view.

## Positioning notes
The enrichment fix is worth being precise about, because the honest version is stronger than the
vague one: the failure was silent and permanent, not slow or degraded, and the symptom customers
would have noticed ("why is my alert all social posts?") looked like a collection problem rather
than a processing one. That is the kind of failure a coverage guarantee has to account for. The
EU AI Act disclosure is table-stakes for EU buyers and is now answerable with a specific
implementation rather than a policy statement.

## Limits and what's next
- **Wiley was three days late getting the Foresight model-list fix** — resolved 2026-08-02. That
  tenant had been showing the old list with fictitious "GPT-4.1"/"GPT-4o" entries since 07-30
  because its copy of the file was taken 18 minutes before the fix landed. Copied and restarted;
  verified live against the running service. Everything else in this range was already on both
  wiley and wileytest.
- **The backlog recovery is not automatic.** Previously discarded articles need the recovery
  script run against them, and it skips topics with an empty ontology — wileytest's "M&A Updates"
  has no future-signal list, which blocks around 3,003 articles for configuration reasons rather
  than parsing ones. That is a separate fix.
- **The relevance cross-encoder tier stays off.** Work in this range established it would have
  rejected 18 of 20 genuinely relevant articles at the shipped threshold, and that it is no
  better than chance on brand topics (AUC 0.478 vs 0.885 on theme topics). It is now safe to
  enable for theme topics; it has not been enabled.
- **These figures are as-recorded.** The article-per-day and AUC numbers come from the work at
  the time and were not re-measured for this write-up.
