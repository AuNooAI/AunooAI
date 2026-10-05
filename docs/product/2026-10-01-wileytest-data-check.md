# Wiley site: news supply outage found, intralogistics topic repaired
_1 October 2026 · Wiley's monitoring site_

Audience note: this covers one outage that affects what Wiley sees, plus repair work on a single
topic. It is for the internal team. Don't send it to the customer as written. The outage is not
fixed yet.

## What shipped
- The intralogistics trends topic can analyse articles again. It had collected articles for
  five weeks without analysing any of them.
- That topic now searches better: it brings in far less unrelated news.
- Social posts from Twitter, Instagram, Reddit and TikTok are arriving again, after three days
  without them.

## Why it matters
**The news feed shrank on 29 September, and we have not fixed it yet.** Our own news feed,
NewsFirehose, stopped taking in new articles at 13:55 UTC on 29 September. Most of Wiley's news
comes through it.
- *Before 29 September:* the site approved 400 to 870 new articles a day.
- *Since:* 174 on 30 September, and 29 by 07:30 on 1 October.
- *Who notices:* every Wiley reader. Feeds, briefings and alerts all have less fresh news in
  them.
- *Why nobody was told:* our health check only asks whether any articles arrived, and some still
  do from other sources. It needs to ask whether NewsFirehose is fresh.

**The intralogistics topic analysed almost nothing.** Every topic has a list of labels the AI
uses to tag each article. This topic's list of future signals was empty, so the AI step refused
every article.
- *Before:* 542 articles in 30 days passed the relevance check and then failed. 38 got through.
- *Now:* the topic has eight future-signal labels, such as "Adoption accelerating" and "Hype
  outpacing deployment". Once the site restarts, new articles in the topic will be analysed, and
  the 536 stuck articles will be run again.
- *Who notices:* whoever follows intralogistics trends on Wiley's site.

**The topic's searches pulled in unrelated news.** Two keywords meant to exclude crypto news did
the opposite: each one asked for every article that does not mention crypto. Together they
matched about 6,100 articles in 30 days. An article that matched both counts twice. We removed them, along with two old company names and
one duplicate. Two loose phrases now search as exact phrases.

**Social posts are back.** Our social search provider refused searches from 28 September to
1 October because the account hit its usage limit. The account has been restored, and a test run
at 08:10 collected 38 Wiley posts. Posts from those three days won't be filled in.

## Release notes (copy-ready, internal only)
- Intralogistics trends topic: AI analysis restored; search keywords tightened.
- Social monitoring (Twitter, Instagram, Reddit, TikTok) resumed on 1 October after a provider
  outage from 28 September.
- Known issue: less new news since 29 September because of a news-feed outage. A fix is pending.

## Demo / walkthrough
None. The changes are to collection and analysis, and no screen changed.

## Positioning notes
None. This is repair work.

## Limits and what's next
- **The news-feed outage needs someone with access to the NewsFirehose server.** We can't log in
  from here.
- **The topic fix waits for a restart.** The site is restarted only when nobody is using it, and
  it was busy at 08:10.
- **The topic name is misspelled ("interalogistics").** Renaming it touches stored articles, so we
  left it.
- **Readers see the same wire story many times.** About 1 in 9 approved articles is a repeat of a
  story another outlet also ran, up to 28 copies in one topic. Removing these at intake needs a
  short spec first.
- **Exam-cheating spam sits in the Pearson topic.** There are 84 such posts in its social
  results. We didn't check whether the Voices page shows them.
