# Customer wins that belong to the market, and open roles that are actually open
_2026-10-09 · Market Monitor reports: aisocnews.com, plus the Oviva, Panaya and Sunstar market sites_

## What shipped
- A customer announcement now counts only if the deal is in the market the report covers, and
  the vendor we track is the one selling.
- The hiring figure now counts the job listings that are open now, not the listings we first
  noticed that week.
- The AI-in-the-SOC report now says what the market includes and excludes.
- aisocnews.com shows a sponsored Anvilogic webinar at the top of its Sponsored panel.

## Why it matters

### Customer announcements
**Before:** the AI-in-the-SOC report took any post in which a named organisation used a tracked
vendor's product. Large vendors sell far more than security tools, so on 9 October four of the
five customer announcements in the 7-day highlight had nothing to do with security operations:

- the Bundesliga using ServiceNow's CRM for fan support
- an AT&T data scientist building an HR chatbot with GitHub Copilot
- Tinder building a recommendation engine on Elasticsearch
- a post in which the tracked vendor, Kai Security, was the customer of another company, not the
  supplier

**Now:** each customer post gets two more questions. Is the deal in this market's line of work,
and is the tracked vendor the one supplying? A post that fails either one no longer counts. The
7-day highlight went from seven customer announcements to two, and both are real security
operations deals: EQUANS with Torq, and LTM with ServiceNow.

**Who notices:** anyone reading the highlights to see which vendors are winning customers.
Before, the list rewarded the vendors with the widest product range, not the ones winning in
this market.

### Open roles
**Before:** the figure labelled "open roles" counted the listings we first noticed in the period.
A role posted in September and still open dropped out of the 7-day count. The 7-day page said 115
and the 30-day page said 158, for the same market on the same day. Neither was the number of
open roles.

**Now:** the figure counts listings that our latest collection run still saw. Both views say 182.
More vendors show up (21 of 114 have listings we can read, up from 16), and 7AI's count went from
24 to 39 because roles it posted earlier now count.

**Who notices:** anyone comparing vendors by hiring, or quoting the figure. Last week's LinkedIn
post said 193 open roles "trending down". That number came from the old method, and it included
Torq, which we have since moved into the large-vendor group that this count leaves out. The data
never supported a trend.

### Market scope
The AI-in-the-SOC report had no written scope. The Analyst View now says what is in (AI SOC
analysts, agentic platforms, SIEM, XDR, EDR, SOAR, managed detection and response) and what is
out (firewalls and network access, identity governance, application security testing,
observability tools). The customer check reads the same text, which is how CrowdStrike Falcon
deployments now count as in-market while firewall deals do not.

## Release notes (copy-ready)
- Customer announcements now count only deals in the market the report covers, where the
  tracked vendor is the supplier.
- The hiring section now counts job listings that are open now. The 7-day and 30-day views now
  show the same figure, since open roles are a current state, not an activity in the period.
- The hiring figure is not comparable with figures published before 9 October 2026.
- The AI-in-the-SOC report now shows its market scope: what it includes and what it excludes.

## Demo / walkthrough
- **Customer highlight:** open aisocnews.com/?view=v2&days=7 and open the "Customer
  announcements" highlight. The ServiceNow CRM and Copilot HR deals are no longer there.
- **Open roles:** open aisocnews.com/?view=v2&section=hiring&days=7. The byline reads "Job
  listings · open now", and the total matches the 30-day view.
- **Market scope:** open the Analyst View (aisocnews.com/?view=report). The scope sits under the
  heading and in the "Market scope" section.
- **Sponsored webinar:** on aisocnews.com, the Sponsored panel at the right on desktop, or the
  strip under the lead story on a phone.

## Positioning notes
The report's case against a news feed is that it only reports what the data supports. A
customer list padded with CRM deals, and a hiring count that measured our own collection rather
than the market, both broke that promise without anyone seeing it. Fixing them supports a
message the data now carries for buyers: in the last 30 days we recorded 8 customer
announcements in this market, and none was reported by anyone other than the vendor.

## Limits and what's next
- **Unnamed customers are not checked.** A post about "a global software company" still counts
  as a customer announcement. Without a name, the check gave wrong answers in testing.
- **The check can be wrong at the edges.** LTM's deal with ServiceNow is borderline: the AI
  agents serve HR, IT and security, and the check let it through at 0.61.
- **Customer spotlights inside vendor newsletters don't count.** SentinelOne's customer story
  about Halton District School Board sits inside a newsletter post, and the report does not treat
  newsletters as developments.
- **Closed roles take a few days to show.** LinkedIn listings can only be marked gone after two
  collection runs that record what they saw. Those runs happen about twice a week, so the 7-day
  and 30-day views on Oviva and Sunstar still differ for now.
- **Some open roles stay hidden.** LinkedIn returns at most 20 listings per company, searched in
  the company's home country, so a vendor's count can be lower than its true number of openings.
