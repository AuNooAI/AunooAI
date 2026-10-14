# App store reviews in Brand Watcher, alerts on reported side effects, and voices cards that show every platform
_14 October 2026 · Brand Watcher (Oviva's site), the brand report and daily briefing, the MCP connector, Market Monitor voices cards (aisecwire)_

## What shipped
- **Brand Watcher reads app store reviews.** For any brand with an app, new Google Play and App Store reviews arrive as posts on the brand's page.
- **App ratings card.** The brand dashboard shows a tile per app: the store rating, or the average of the reviews we collected where the store gives none, always with how many reviews it rests on, plus a weekly trend line.
- **Two new alerts.** One fires when an app's rating slides. The other fires when 1–2 star reviews suddenly double.
- **Competitor apps, side by side.** On Oviva's site, eight competitors' apps are tracked next to Oviva's, in one table in the Comparison view.
- **App ratings in the brand report and the daily briefing.** The downloadable report has an App Reviews section. The daily briefing gets a short app-review note on days when something moved.
- **Alerts on reported side effects.** When an app review describes harm to the writer's health that they link to the brand, it's flagged and an alert goes out, one per report.
- **App reviews through the MCP connector.** An assistant connected to the site can compare app ratings across brands and read the complaints behind them.
- **Fuller voices cards.** On Market Monitor pages, the "Influence and Influencers" card now gives places to X, Reddit and Bluesky voices, and no longer lists bots as people.

## Why it matters

### App store reviews
**Before:** Oviva's Brand Watcher saw news, social posts and Glassdoor reviews, but not app reviews. Oviva's own app has 30,685 Google Play reviews. That's the largest body of customer opinion about Oviva. In the last 30 days alone it received 55 app reviews, against 19 press items in the 90 days to 1 October.

**Now:** Oviva's analysts see what users say about the app as it's posted. The first collection found complaints that press never covers: a login problem, "just application no coach", and too much information at the start.

**Who feels it:** brand and customer-experience teams. A bad app release now shows up as an alert within days, long before it moves the overall rating.

### Competitor comparison
**Before:** comparing Oviva's app with Voy's or Noom's meant checking each store by hand.

**Now:** the dashboard and the MCP connector hold the ratings for all nine brands. On 14 October, Google Play ratings ran from Voy at 4.71 to Zanadio at 3.96, with Oviva at 4.56 in third place. The complaints sit behind each number. Voy's most recent 1-star reviews were about a forced data-sharing update and an iPhone app that crashes every 10 seconds.

**Who feels it:** strategy and product teams asking "where do we stand, and why?"

### Recent reviews against the store rating
**Before:** a store rating sums up years of reviews, so it hides a recent slide, and the App Store tile showed only a dash.

**Now:** every tile shows the last 30 days next to the store rating, with the number of reviews behind it. Where the two differ by 0.3 stars or more, the tile says so. Voy's Android app has a store rating of 4.71, but its 27 most recent reviews average 3.81. Second Nature's iPhone reviews average 2.40 from 5 reviews, against 4.68 on Google Play. Averages from fewer than 5 reviews are greyed out and marked "few reviews", so nobody reads too much into them.

**Who feels it:** anyone comparing brands. The overall rating says how a brand was seen; the recent figure says how it is seen now.

### Reported side effects
**Before:** Oviva prescribes GLP-1 medication. On 7 October a patient wrote on Google Play that the staff's suggestions "would make me physically sick". Our risk check missed it. It only looked for words like "lawsuit" and "recall", and it had no category for a person reporting harm to their own health.

**Now:** app reviews that mention side effects, nausea, being made sick, hospital visits and similar go to the risk check. It flags those where the writer reports harm they experienced, not warnings about others. Each one sends an alert quoting the review, saying what the check found, and stating that we haven't verified it. The 7 October review was flagged and alerted at 19:04 on 14 October. Of the 209 reviews collected so far, it is the only one flagged.

**Who feels it:** today, Aunoo's own team, who receive Oviva's alerts. Later, if Oviva agrees, Oviva's safety team, who can be added to this alert alone.

### Voices cards
**Before:** aisecwire's card showed only Bluesky accounts. A fault in the overnight job meant X and Reddit authors were never looked up, on six customer sites, from 10 October. Even after that was fixed, the biggest X accounts would have taken every place, because the card ranked by follower count alone. One "practitioner" on the card was a Reddit moderator bot.

**Now:** each platform keeps up to two of the ten open places. The overnight lookups run again on every affected site. Accounts that are clearly software (feed bots, moderator bots, news tickers) are kept off the card.

**Who feels it:** readers of the market pages, who now see the practitioners and analysts on each platform, not just the loudest accounts on one.

## Release notes (copy-ready)
- Brand Watcher now collects Google Play and App Store reviews for brands with an app. Reviews appear as posts on the brand page.
- New "App ratings" card on the brand dashboard: store rating, 30-day change, review count, downloads, and recent reviews by stars.
- New alerts: app rating drop, and a surge in 1–2 star app reviews. Both thresholds can be adjusted in alert settings.
- The App ratings card shows a weekly trend, the number of reviews behind each figure, and a note when recent reviews run well above or below the store rating.
- Comparison view: app ratings for every tracked brand in one table.
- Brand report: a new App Reviews section with each app's figures, the comparison with competitors, and recent 1–2 star reviews.
- Daily briefing: a short app-review note on days when ratings moved or complaints came in.
- Reported health side effects in app reviews are flagged and sent as alerts, one per report, whatever their severity. The alert can be switched off in alert settings.
- MCP connector: two new tools. `get_app_ratings` compares brands' apps. `get_app_reviews` returns review text and can be filtered by store and stars.
- Market Monitor: the voices card now keeps places for each platform, and no longer lists automated accounts.
- Market Monitor: profiles of new voices are built every night again (this stopped on 10 October on some sites).
- Market Monitor: topic names describe what happened, without words like "momentum".

## Demo / walkthrough
1. **The card and the reviews.** On Oviva's site, open Explore, then Brand Watcher, and pick Oviva. The "App ratings" card is on the Dashboard, below the summary cards. App reviews appear in the brand's posts, labelled Google Play or App Store.
2. **The alerts.** Open the alert settings from the Brand Watcher tab. The two new rows are "App rating drop" and "1-2 star app review surge".
3. **Competitors.** Pick another brand, such as Voy or Second Nature, to see its card.
4. **The comparison.** Open the Comparison tab. The "App ratings" table is at the top. Hover a trend line to see a week's average and how many reviews it rests on.
5. **The report.** Export the HTML report from the Brand Watcher tab and open the "Apps" link in its navigation.
6. **Side effects.** Open the Risk view, or the alert list, and look for "reported health side effect".
7. **Through an assistant.** In an assistant connected to the site's MCP server, ask "How do Oviva's app ratings compare with its competitors?" (it calls `get_app_ratings`). Then ask "What are Voy users complaining about?" (it calls `get_app_reviews` with a 2-star limit).
8. **Voices.** On aisecwire, open the market page and scroll to "Influence and Influencers". It now lists X, Bluesky and Reddit voices.

## Positioning notes
- **App reviews fill a gap in health brand monitoring.** For a digital health service, the app is the service. News monitoring alone misses the experience of using it. Oviva received 55 app reviews in the last 30 days, against 19 press items in the 90 days to 1 October.
- **The competitor comparison answers a common question directly.** Prospects often ask how they compare with competitors. This answer comes with the reviews behind each number, not a single score.

## Limits and what's next
- **Some apps are only partly covered.**
  - WeightWatchers and Noom are covered on Google Play only. Their App Store pages return hundreds of old reviews on every call, which would have cost more than the rest of Oviva's collection put together.
  - We didn't find HelloBetter's iPhone app.
  - The German apps for Oviva (DiGA) are left out, because Oviva's site covers the UK programme.
- **The App Store gives no overall rating.** For iPhone apps the card shows the average of the reviews we collected, which for most apps is a small number each month.
- **The trend lines are short.** Collection started on 14 October, reading back 30 days, so each line starts in mid-September and fills out to 12 weeks over the coming months.
- **App Store reviews arrive weekly, Google Play reviews daily.**
- **Side effects go to Aunoo, not Oviva.** A reported side effect may be something Oviva is obliged to act on once it knows. The alerts go to Aunoo's team. Sending them to Oviva's safety team is Oviva's decision, and we haven't asked them yet. Only app reviews are checked this way, not news or social posts.
- **The daily briefing note hasn't appeared in a real briefing yet.** It will be in the next one composed on Oviva's site.
- **Cost.** Collection costs about $2.50 per 1,000 reviews, and each site is capped at 4,000 reviews a month. We haven't yet confirmed whether Bright Data also charges a minimum per call. If it does, daily Google Play calls cost more than they should.
- **Not on other sites yet.** App store reviews run only on Oviva's site. Any brand with an app could be added.
- **Deep research web search runs only on our development site.** Google's search API was already switched off there. Bright Data's search is slow (28–64 seconds) and fails at random, so it retries once before falling back to other sources. It isn't offered to customers yet.
