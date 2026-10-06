# Brand topic relevance: spec

_2026-10-06 · status: draft for Oliver's review · scope: news rows on brand topics ("Brand Monitoring X")_

## 1. The problem

A brand topic should keep every news article that is coverage of the brand and nothing else. On the
two proof-of-value sites that run brand monitoring it does neither reliably, and every fix so far has
been a hand repair of one topic.

Measured on 6 October over the last 30 days of news rows:

| Topic | Rows | Approved | Rejected rows that name the brand in their title |
|---|---|---|---|
| Sunstar · Colgate-Palmolive | 251 | 18 | 40 |
| Sunstar · Lion Corporation | 333 | 0, then 3 after a hand rescore | 12 |
| Sunstar · P&G Oral-B | 160 | 6 | 10 |
| Sunstar · Sunstar | 113 | 2 | 7 |
| Oviva · Oviva | 60 | 54 | 0 |

What those rows are, from samples:

- **Real coverage rejected.** Of 15 sampled Colgate rows that name the brand and were rejected, about
  a third are real coverage: "Colgate-Palmolive explores sale of three personal care brands in $1 bn
  plus deal" (0.40), "Colgate-Palmolive Declares Regular Quarterly Dividend" (0.40), a Barclays
  conference transcript (0.30), and two title-only items marked failed. The rest are correct
  rejections: Colgate University football, deal listings, stock-list mentions.
- **Japanese coverage invisible.** Lion's topic approved nothing for a month. Lion Dental Materials'
  product launch scored 0.10 and the Clinica advert 0.30. Today's judge scores them 0.8 to 0.9 with
  the same inputs; the stored scores came from older pipeline versions and were never redone.
- **Non-coverage approved.** Of Oviva's 54 approvals, 51 do not name Oviva. They are Oviva's own
  recipe and diet blog posts, German weight-loss sector stories, and some noise ("ehex starts rollout
  for HSM-B in TI-Gateway").

## 2. Why it fails

1. **A coarse score meets a fine cut.** The judge answers in steps of 0.1 and the site cut is 0.45.
   Its prompt puts "the brand is a notable part of the story" at 0.3 to 0.6, a band the cut splits.
   A story about Colgate selling three brands lands at 0.40 and is rejected.
2. **The judge learns who the brand is from the collector's search terms.** For Lion those were four
   terms, none of them the Japanese company name or most product lines. The brand profile
   (`bw_brands`) holds names, products and people, but the news judge never reads it.
3. **Old verdicts are never redone.** The gate version stamp (`rejected_candidates.gate_version`)
   decides whether a saved rejected *candidate* is re-judged on the next collection. Nothing
   revisits stored articles when the judge, the model or the profile changes.
4. **Title-only articles fail whatever they say.** The no-text guard in
   `automated_ingest_service._process_single_article_async` marks a row `enrichment_failed` before
   any relevance check, so "Colgate-Palmolive seeks to divest some personal care brands" never reaches
   the judge.
5. **Owned content and sector news count as brand coverage.** The brand prompt approves "the
   industry/sector/policy it operates in" at 0.7 to 1.0 and has no notion of the brand's own site.
6. **Nothing measures correctness.** `scripts/data_quality_check.sh` counts volumes. Whether a change
   helped is answered by a hand sample each time.

## 3. What we build

One decision path for brand-topic news, in four steps. Theme and market topics keep the current path.

### 3.1 Brand identity comes from the brand profile

The profile in `bw_brands` becomes the single source of who the brand is, for collection, judging and
display. Fields used:

- `brand_keywords`, `product_keywords`: names in **every script the site covers**. Lion gains
  ライオン, LION, ライオン歯科材, and its oral-care product lines in Japanese and Latin script.
- `config.mention_context` and `config.exclude_context`: as in Oviva's mention gate today.
  `exclude_context` is where collisions go: for Colgate, "university", "Raiders", "football",
  "basketball", "lacrosse"; for Lion, "Lionsgate", "sea lion".
- `config.owned_domains` (new): the brand's own sites (oviva.com, colgate.com, lion.co.jp).
- `config.non_press_domains`: as today.

A site without a profile field falls back to the topic's search terms, so nothing breaks before the
profiles are filled in. Filling them in for the 14 brands on Sunstar and Oviva is part of the work.

### 3.2 A deterministic mention check runs first

`brand_mention_gate.py` (on bugfixing and Oviva today, missing on Sunstar) is extended into a mention
check that reads title, summary and the original-language title and summary, and returns one of:

- `title`: a brand or product name is in the title.
- `body`: a name is in the summary or body only.
- `none`: no name anywhere.
- `same_name`: every match sits beside an `exclude_context` word.

`same_name` rejects without a model call. The other three go to the judge with the result attached.

### 3.3 The judge answers a category, not a number

For brand topics the judge is asked which of these describes the article, given the brand profile:

| Label | Meaning | Default outcome |
|---|---|---|
| `subject` | The article is about the brand, its products, people or results | approve |
| `notable` | The brand is a notable part of a wider story | approve |
| `sector` | About the brand's market or policy area, brand not material | **decision 1** |
| `passing` | The brand is named in passing | reject |
| `other` | Unrelated, or a different thing with the same name | reject |

The answer is JSON with the label and a one-line reason, parsed strictly. An unparseable or missing
answer leaves the row `relevance_check_failed`, as the integrity patch already does.

Two deterministic rules sit on top:

- **Title floor.** A `title` mention that the judge labels `passing` becomes `notable`. A company
  named in a headline is coverage of that company. Decision 2 confirms this.
- **Owned content.** A row from an `owned_domains` host is labelled `owned` without a model call and
  kept in its own bucket (see 3.5).

The stored `topic_alignment_score` keeps working for every existing reader: `subject` 0.9,
`notable` 0.7, `sector` 0.5, `passing` 0.2, `other` 0.0. The approval decision is made on the
label, not on that number, so the 0.40-versus-0.45 split disappears.

### 3.4 Title-only articles are judged on the title

For brand topics the no-text guard moves after the mention check. A title-only row with a `title`
mention is judged on its title; if approved, the AI analysis step runs on the title and the row is
marked with a quality flag so readers know the summary is thin. A title-only row without a mention
keeps today's `enrichment_failed` outcome.

### 3.5 Where the label is stored

An alembic migration adds two nullable columns to `keyword_article_matches`, which already holds the
per-topic verdict (`topic_alignment_score`, `relevance_status`, `scored_at`):

- `brand_relation` (text): `subject`, `notable`, `sector`, `passing`, `other`, `same_name`, `owned`.
- `judge_version` (text): the brand judge's version plus a hash of the brand profile fields it read.

Brand Watcher's news views count `subject` and `notable` as earned coverage, show `owned` separately,
and show `sector` according to decision 1. The articles table is unchanged apart from the existing
score and status fields.

### 3.6 Old verdicts are redone automatically

A background pass re-judges a brand topic's last 30 days of news when that topic's `judge_version`
differs from the current one: after a deploy, after a model change, or after someone edits the brand
profile. It runs at a fixed rate (default 1 row per 3 seconds), only on brand topics, and it calls the
relevance step only; the AI analysis step runs only for rows that change from rejected to approved.
It never re-analyses rows that stay approved. Today's hand rescore did, which is why it was slow.

### 3.7 Correctness is measured

- `scripts/brand_relevance_eval.py` draws 50 news rows per brand: a third approved, a third rejected
  that name the brand, a third rejected that do not. It writes a small HTML page where each row gets
  a yes/no "is this coverage of the brand" from a person.
- The labels are stored (`brand_relevance_labels`, alembic) and the script reports precision and
  recall per brand against them.
- `data_quality_check.sh` gains a section that prints those two numbers for the last labelled set.

Proposed targets for the proof-of-value sites: precision 0.90, recall 0.90 on rows that name the brand.
Decision 4 confirms them.

## 4. Out of scope

- Social posts. They go through `social_eval_service.py`, which already has its own brand rules.
- Theme and market topics. Their path is unchanged.
- Collection keywords. Loose body matching stays; on 5 October quoting phrases was measured to lose
  more than half of approved coverage.
- Panaya. Its brand topics hold only vendor LinkedIn posts, no news.

## 5. Rollout

1. Build and test on canonical (bugfixing), which has no brand news of consequence, against copied
   Sunstar and Oviva rows.
2. Fill in the 14 brand profiles on Sunstar and Oviva (names in every script, collisions, owned sites).
3. Oliver labels the first set: 50 rows times 14 brands is 700 yes/no clicks. A smaller first round of
   20 per brand (280) is enough to see whether the change works.
4. Deploy to Sunstar and Oviva: migration first, then code, then restart when quiet. Sunstar also
   needs `brand_mention_gate.py`, which it lacks.
5. The re-sweep runs; compare precision and recall before and after on the labelled set.

Other brand-monitoring sites (wileytest, abm, bwtemplate) follow only if asked; this is a feature, and
features go to the sites that requested them.

## 6. Cost

The judge is called once per brand-topic candidate, as now; `same_name` and `owned` rows skip it, so
the count falls slightly. The re-sweep costs one judge call per row in the 30-day window per profile or
version change: about 900 rows on Sunstar's five brand topics and 940 on Oviva's eight, at today's
volumes. The AI analysis step runs only for rows newly approved. No new model; the judge stays on the
site's configured relevance fallback model.

## 7. Tests

- Mention check: every script (Latin, Japanese, German), collisions, original-language fields,
  owned domains.
- Judge parsing: each label, malformed JSON, missing answer, an answer outside the label set.
- Decision rule: the title floor, owned short-circuit, `same_name` short-circuit, each label's outcome.
- Regression rows taken from this spec: the Colgate divestment, the dividend notice, Lion Dental
  Materials, the Clinica advert, Colgate University football, the Lionsgate story, an Oviva recipe page.
- Re-sweep: runs on a version change, skips unchanged topics, never re-analyses rows that stay approved.

## 8. Decisions for Oliver

1. **Sector stories.** Are articles about the brand's market that do not involve the brand coverage
   of the brand? Recommendation: keep them, labelled `sector`, shown under a separate filter and left
   out of brand counts and brand alerts. Oviva's numbers today include them as brand news.
2. **Title floor.** Is a brand named in a headline always coverage? It would approve "The S&P 100 ETF
   just dumped Nike and Colgate for 4 AI stocks". Recommendation: yes; an index change is news for
   the company, and the label stays `notable`, not `subject`.
3. **Owned content.** Should the brand's own site appear in the brand topic at all? Recommendation:
   yes, labelled `owned` and shown apart from press, as social posts already are.
4. **Targets and labelling.** Precision and recall of 0.90, measured on a first round of 20 rows per
   brand labelled by you.

## 9. Effort

About a day of agent work for the code, migration and tests on canonical; an hour to fill in the 14
brand profiles; deployment to the two sites in the same session once the labelled round is back.
