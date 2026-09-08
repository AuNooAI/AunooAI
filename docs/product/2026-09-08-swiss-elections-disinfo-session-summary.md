# Swiss Federal Elections 2027 disinformation topic: session summary
_2026-09-08 · bugfixing.aunoo.ai, Add-Topic wizard, keyword monitor, NewsFirehose_

## Starting point

The topic "Swiss Federal Elections 2027 Disinfo Monitoring" was added on bugfixing
through the Add-Topic wizard. It saved five generic keywords: disinformation,
misinformation, propaganda, deepfake, generative AI. The first collection run fetched
50 articles and the relevance gate rejected all 39 it saved, among them Verisk fraud
press releases, an EU terror story syndicated eight times and a Telegram outage. The
questions in order were: why is the wizard generic, rebuild the topic with German and
French groups, and extend the firehose since we curate it.

## What was wrong with the wizard

The model was fine. The `gpt-5.4-mini` alias runs kimi-k2.5 on Bedrock and it had
suggested "Swiss elections", "Bundesrat", "Nationalrat", "Ständerat" and "election
interference". Four separate defects lost them:

- Step 3 of the React wizard kept only the first three entries of each list, and the
  model listed the generic words first. This came in with the original React MVP commit
  and had no recorded reason.
- The prompt told the model to use single-word or two-word keywords, which is what
  produces "disinformation".
- The save endpoint read `future_signals` while the wizard posts `futureSignals`, so
  every wizard-created topic has had an empty future-signals list.
- The keyword normaliser cut anything over 30 characters at the last space, turning
  "Switzerland election interference" into "Switzerland election".

A fifth defect surfaced when testing the German group. The manual "check now" button
applied a group's providers and threshold but not its language, so a German group
searched TheNewsAPI in English and found nothing. The scheduled path did this correctly.
The single-group settings query also never selected the language column.

## What was fixed in the wizard and monitor

All five are fixed on bugfixing and committed as `58e80cce`.

- The prompt requires every keyword to carry the topic's own anchor, two to four words,
  most specific first, in the local press's language.
- Step 3 keeps all suggestions. The regenerate button goes through the same rules
  instead of its own short prompt.
- Both future-signal keys are read on save.
- The length cap is 60.
- A manual single-group run applies language, country and date window and restores them
  afterwards. The settings query selects language and country.

Tested on the Swiss topic, the wizard now returns anchored terms in English, German,
French and Italian plus the seven Federal Councillors and the relevant federal bodies.

The onboarding fix and the normaliser were copied to wiley and wileytest without
restarting them. The language fix does not apply there because those tenants never
received per-group language.

## The topic as it stands

Three groups share the topic name.

| Group | Language | Providers | Terms |
|---|---|---|---|
| 21 | English | firehose | 14 |
| 22 | German | TheNewsAPI, firehose | 11 |
| 23 | French | TheNewsAPI, firehose, reddit, xpoz, bluesky | 8 |

The lists came from measuring every term over 30 days on its own collector and dropping
the noise generators: the Keystone-SDA byline, the Swissinfo syndication tag, FIFA's
2027 election, GLP-1 drugs, a Singapore rail link. Two quoted phrases were added for the
firehose, which honours a lone quoted phrase. The description now covers federal
referendums and popular initiatives before 2027, naming the neutrality initiative.
Committed as `d34d860e`.

Exclusion keywords were left out on purpose. The firehose strips NOT terms and nothing
filters afterwards, so they are searched as terms.

Two settings changed outside the groups. The tenant's search fields now include article
body for TheNewsAPI, because Swiss-anchored German phrases return zero on title and
description but 6 to 33 hits over 30 days with body search. Only these two groups use
TheNewsAPI on bugfixing.

The gate is drawing the right line. Pieces about Russia's role in the neutrality vote
pass at 0.80 to 0.88. Plain campaign coverage such as a Blocher profile is rejected at
0.2 to 0.4.

## The firehose

The firehose is our own aggregator at `/opt/newsfirehose`. It fetched from NewsData.io
in English only because a slice could set priority tier, category and count but not
language or country. The fetch script now allows per-slice language, country and domain,
with the priority tier optional.

A sixth slice fetches Swiss German, French and Italian politics, world and domestic
coverage: 1,000 articles on weekdays and 600 at weekends, roughly 19 requests against a
daily budget of about 650, of which today's run used 530.

A hand-run 100-article test inserted 48 German, 33 French and 19 Italian articles from
Tages-Anzeiger, Tribune de Genève and Ticino Libero, and the monolith found them by
language. The worker was restarted for tomorrow's 08:00 run. The change lives in a
checkout of a teammate's repository and is not committed there.

## Open items

- Group 23 gained reddit, xpoz and bluesky during the session. Reddit returns 429 on
  every call and the Bluesky posts were about rent initiatives and logins.
- The wizard still cannot set a group's language or providers. Those were set by SQL.
- The firehose's LLM classification step has been failing all day with "no credits
  remaining" from OpenAI. Articles are still stored and searchable through the other two
  steps.
- The firehose full-text index is English-stemmed, so German inflections do not match.
- `docs/changes.md` carries the firehose entry and is uncommitted on bugfixing.
- The next scheduled runs of the three groups are at 01:43 to 01:53 on 9 September, and
  the first Swiss firehose fetch is at 08:00 the same day.

Elapsed for an AI: roughly three hours, most of it waiting on collection runs.
