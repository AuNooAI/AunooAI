# Articles stopped disappearing. Alerts stopped calling news "social".
_Work done 29–31 July 2026 · Affects Explore, alert emails, Briefing Desk, topic setup, Foresight_
_Written 2 August 2026, after the fact. The numbers are the ones recorded at the time. We have not re-measured them._

## What shipped

- **Articles no longer go missing.** The AI read them, could not file them, and threw them away.
  They now show up in search, alerts, and reports.
- **Alerts tell news from social posts.** They used to call almost everything a social post.
- **AI-generated output says so.** Reports, exports, dashboards, and emails now carry a visible
  label. This is what the EU AI Act asks for.
- **Daily briefings use one model.** Before, the answer depended on what the reader's browser had
  selected.
- **Topic setup suggests keywords again**, and the Foresight model list shows real models.
- **Collectors stopped choking on ordinary names**, such as "John Wiley & Sons".

## Why it matters

### Articles were disappearing, and they were not coming back

The AI wrote a summary of each article. Our code then checked that summary for 14 labelled
fields. The check demanded exact wording. If the AI renamed one field, numbered the list, or left
the title out, we threw the whole summary away. The article stayed in the database, but unfiled.

Nothing downstream can see an unfiled article. Not alerts, not search, not reports. Nothing
retried it. So the article was not late. It was gone, for good.

On one customer site this hit about 227 news articles a day. Social posts are handled by
different code and were fine. That is why alerts had started to look like nothing but Bluesky.

The check now accepts the wording the AI actually uses. It rejects a summary only when something
essential is missing. A recovery script can go back over the articles we lost. And when the AI
returns something garbled, we now try three times instead of giving up at the first attempt.

*Who notices: anyone who assumed an alert or a topic view was complete.*

### Alerts called news articles "social posts"

If a link was not Bluesky, X, or Reddit, the alert labelled it "Social · view post". Most links
are news, so most links were labelled wrong. A Nature or CNN article was presented as a social
post.

News links now show the publisher name and say "read article". Instagram and TikTok are now
recognised as social.

*Who notices: everyone who gets an alert email.*

### AI-generated output was not labelled

Reports, exports, dashboards, and emails now carry a visible "AI-generated" label and a
machine-readable marker. Both come from one place in the code, so they cannot drift apart between
a PDF and an email.

We also softened wording that claimed more than we do. Some screens said content was "reviewed
and validated". It is not, so they no longer say so.

*Who notices: EU customers, and anyone answering a procurement question about AI.*

### The briefing changed depending on who opened it

The daily briefing used whichever model the reader's browser had selected. Two people could read
the same briefing and get different content, with different bylines. The briefing now uses the
model set for that customer site.

*Who notices: readers who compare notes.*

### Two things left broken by the move to Bedrock

We moved every customer site to Bedrock for AI. Two features still expected the old setup.

Topic setup stopped suggesting keywords. The code looked for an OpenAI model, found none, and
gave up without saying anything.

The Foresight model list showed about two dozen options that were really the same few models
under different names, with Claude labelled as GPT and Gemini. It now lists the five models that
exist, under their real names.

*Who notices: anyone setting up a topic or picking a model.*

## Release notes (copy-ready)

- Fixed: some articles were discarded during AI analysis and never appeared in alerts, search, or
  reports. They are now processed correctly. A recovery pass is available for articles affected
  earlier.
- Fixed: alert emails and reports labelled news articles as social posts. News and social are now
  shown separately, each with the right link.
- Added: a visible "AI-generated" label on reports, exports, dashboards, and email, in line with
  the EU AI Act.
- Fixed: daily briefings now use the model configured for your site, not the one selected in the
  browser.
- Fixed: keyword suggestions in topic setup, and the model list in Foresight.
- Fixed: collectors failing on publisher names containing "&", on searches across several fields,
  and on articles with no text.

## Demo

- **Alert labelling.** Open any alert email or its online report. A news match now reads
  *publisher · News · read article*.
- **AI label.** Look at the footer of any generated report or export.
- **Model list.** Open the model dropdown on the Foresight view.

## Positioning notes

Say what actually happened. The plain version is stronger than a vague one.

Articles were lost, silently and permanently. That is different from slow or degraded. And the
symptom a customer would have noticed — "why is my alert all social posts?" — pointed at
collection, when the real problem was in processing. Any promise we make about coverage has to
account for failures that look like something else.

On the EU AI Act: we can now point to what we built, not to a policy statement.

## Limits and what's next

- **One customer site got the model-list fix three days late.** Wiley ran the old list, with
  invented "GPT-4.1" and "GPT-4o" entries, from 30 July. Its copy of the file was taken 18 minutes
  before the fix landed. Fixed and restarted on 2 August, and checked against the running service.
  Everything else here was already on both sites.
- **Recovering lost articles is a manual job.** Someone has to run the recovery script. It also
  skips any topic that has no list of allowed labels set up. One topic, "M&A Updates", is in that
  state, which holds back about 3,003 articles. That is a settings problem, not a code problem,
  and it needs fixing separately.
- **One relevance filter stays switched off.** We tested a filter that would decide on its own
  which articles are relevant. At the setting we had shipped, it would have rejected 18 of 20
  articles that were genuinely relevant. On brand topics it is no better than a coin toss, because
  telling SAGE Publishing from Sage Group plc is a name problem, not a meaning problem. It works
  on theme topics and is now safe to turn on there. We have not turned it on.
- **The numbers here are as recorded at the time.** We did not re-measure them for this write-up.
