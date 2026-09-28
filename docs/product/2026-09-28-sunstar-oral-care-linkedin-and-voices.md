# Oral Care market page fills in; Voices shows five audiences, not nine
_2026-09-28 · Market Monitor (Sunstar's Oral Care market) and Brand Watcher Voices on the Sunstar site_

## What shipped
- The Oral Care market page now collects LinkedIn company posts, LinkedIn company profiles,
  LinkedIn job listings and Crunchbase records for five of its six vendors. Until today it had
  none of these and every LinkedIn panel said "not set up".
- A panel that has nothing to show now says why in plain words: "no LinkedIn company page on
  file", "no Crunchbase profile on file", "no careers-site job board found yet". It used to quote
  an internal field name.
- The Voices panel for the Sunstar brand shows five audiences instead of nine: Customers,
  Retailers, Dental & health professionals, Press & analysts, Competitors.

## Why it matters
**The market page had no company data.** An analyst opening Oral Care saw the headline question,
the vendor list, and a row of empty panels explaining themselves in database vocabulary. Now the
five monitored vendors have a LinkedIn headcount, their recent company posts and job listings, and
a Crunchbase record. The first collection ran within seconds of switching it on and returned
24 new posts, 5 profiles, 5 Crunchbase records and 40 job listings for under five cents. The
Market Maturity Map needs the headcount to place a vendor, so the vendors stop sitting as
"not rated". The operator feels this most: the page now answers the question it asks.

**Empty panels explained themselves badly.** "no active linkedin_company_url identifier on file"
is a column name. A reader who does not know the database could not tell whether that was a
fault or a gap. The new wording says what is missing in words the reader can act on, on every
site that runs Market Monitor.

**Nine audience rows hid the signal.** The Voices panel listed every role the classifier had ever
assigned, including three rows with fewer than five posts each and one row of "bystanders" with no
role at all. The analyst had to read past six rows to find the two that matter for a toothpaste
brand: what customers say and what dental professionals say. The five-row view keeps every post
and every detailed label underneath; it only changes what is shown. Related roles are shown
together (patients and carers under Customers, clinicians and researchers under Dental & health
professionals, industry commentators and investors under Press & analysts), and the brand's own
posts and the bystanders are left out of the view.

## Release notes (copy-ready)
- Oral Care market: LinkedIn posts, profiles, job listings and Crunchbase records are now
  collected for Sunstar, Lion, Colgate-Palmolive, P&G (Oral-B) and Haleon.
- Market panels with nothing to show now say what is missing in plain words.
- Voices for the Sunstar brand shows five audiences: Customers, Retailers, Dental & health
  professionals, Press & analysts, Competitors. Each post keeps its detailed role.

## Demo / walkthrough
- Market Monitor, Oral Care, Findings tab: the LinkedIn and Crunchbase panels now carry figures.
  The Collection tab shows the four sources as checked, with five of six vendors covered (Kao is
  deliberately not monitored).
- Market Maturity Map tab: headcounts are in, so the placement rule has what it needs for the
  five monitored vendors.
- Brand Watcher, Voices, brand Sunstar: five rows; the view opens on dental professionals against
  customers. Hard refresh once after the update.

## Positioning notes
Nothing new to claim externally. This brings the Sunstar site level with what the AI SOC market
on aisocnews.com already does, and makes the empty state honest. The Voices change is the same
principle already applied for the publishing customer on 25 September: show the audiences the
customer cares about, keep the detail underneath.

## Limits and what's next
- Oral-B has no official LinkedIn company page of its own, so the P&G corporate page is on file.
  Oral-B's headcount on the map is P&G's 97,078, and its LinkedIn posts are P&G's. The only
  Oral-B-specific page is a dental-professionals showcase, which the data provider does not take.
- Kao is in the vendor list but not monitored, by an earlier decision. The page says "5 of 6".
- The Crunchbase links were entered as best guesses. All five resolved on the first run, but they
  are marked unverified until someone confirms them.
- The profile figures have arrived but the step that promotes them into the canonical company
  record had not yet run when this was written, so the Maturity Map may lag the Findings tab by
  one cycle.
- Spending is capped at 20 dollars a month for this market. At five vendors the first full run
  cost under five cents; the cap is there in case the vendor list grows.
- Oviva was checked for the same Voices treatment and already has it, through the health audience
  set saved on its settings page on 25 September. No change was made there.
