# Market Monitor now watches every vendor, not the first twenty
_2026-08-26 · Market Monitor — vendor table, coverage figures, hiring, downloadable report_

## What shipped

- Every vendor in a market is now collected, instead of the first twenty by list order.
- The vendor table's "no observed activity" count fell from 58 to 6, because 52 of those companies did have activity — nobody had looked.
- Employee-count readings are now live for 78 of 84 vendors, up from 21. The rest still show the figure from the imported spreadsheet, and say so.
- Job listings are being collected again after being switched off in error. Postings held went from 33 across 7 companies to 91 across 16.
- A company's staff count can no longer be filled in from a size band, so no vendor can appear with a made-up headcount.
- Provider data now arrives when it is sent rather than ten minutes later.

## Why it matters

**The vendor table was reporting silence it had never checked.** Before today, a customer opening a market saw 58 of 85 vendors marked "No observed activity — no vendor posts, open roles or matched coverage were observed from monitored sources during this period." For 57 of those 58, nothing had ever been collected. The sentence described work that had not been done, in the voice of a measurement that came back empty. After one full pass, 52 of them turned out to have posts, and the count sits at 6.

Who feels it: an analyst using the table to decide which vendors are worth attention. A company marked quiet gets skipped. Fifty-two of them were being skipped for no reason.

**Headcount could have been wrong by three orders of magnitude.** The reader that turns a provider's answer into a staff number stripped out anything that wasn't a digit. For a follower count written "13,111" that is right. For a size band written "51-200" it produced 51,200, and "1,001-5,000" produced 10,015,000. It had not fired yet, but one provider response missing the exact field would have put ten million staff into a market total with nothing on screen to suggest a problem. A band is now kept as a band and never used as a number.

There was also a real case in the other direction: the provider returned a staff count of **0** for a company whose own profile said "2-10 employees". That company would have shown as having no staff and drawn a point on the floor of its headcount chart. Zero is now treated as a missing answer, which is what it is.

Who feels it: anyone reading a market total, a top-movers list, or a single vendor's headcount trend. All three were one bad provider response away from being obviously wrong, or quietly wrong.

**Hiring data had been switched off by mistake.** The job-listing collector was paused in error nine days ago, citing a provider error that had already been fixed on the same day it appeared. Because a paused source is simply silent, nothing on screen distinguished "we are not collecting this" from "there is nothing to report". It is collecting again, and the number of tracked job postings nearly tripled in one run.

**Provider data was arriving late, every single time.** Every batch we bought was being refused on delivery and then fetched a second time ten minutes later by a fallback. Customers never saw an error, because the fallback worked — but every figure was up to ten minutes staler than it needed to be, and we were paying to fetch the same records twice. Deliveries now land on arrival.

## Release notes (copy-ready)

- Market Monitor now collects every vendor in a market on each cycle. Previously only the first twenty were refreshed, so most vendors showed no activity because none had been gathered.
- The "no observed activity" count is now based on vendors we actually checked. It fell from 58 to 6 in the SOC Automation market.
- Live employee counts are available for 78 of 84 vendors, up from 21. Vendors still using the imported spreadsheet figure are labelled with their source.
- Staff counts are no longer inferred from company size bands, and a reported count of zero is treated as unknown rather than as a measurement.
- Job-listing collection has been restored. Tracked postings rose from 33 to 91.
- Provider data now arrives as soon as the provider sends it.

## Demo / walkthrough

Market Monitor → SOC Automation. The vendor table's "No observed activity" tile now reads 6 rather than 58. Click any vendor to see its Staff figure with the source and date it was read; open a vendor whose source says `workbook` to see the labelled fallback. The hiring panel shows currently observed listings across 16 companies.

## Positioning notes

This closes a specific and damaging objection: *"your dashboard says these companies are quiet — how do you know?"* Until today the honest answer was that we did not, and the product said otherwise. It now distinguishes what was measured from what was not, which is the whole basis for trusting any other number on the page.

It does not yet close the objection fully. See below.

## Limits and what's next

**The remaining 6 may be genuine, and we should not claim it yet.** One successful sweep is not two. A second pass is needed before saying those companies are actually quiet rather than newly unmeasured.

**"No observed activity" is still the wrong label even at 6.** The count is built from attributed coverage and job postings. It cannot yet tell a customer whether a vendor was measured and found empty, or never measured. Splitting that into two figures — measured-and-empty versus not-yet-measured — is the next piece of work, and it is what the phrase claims to already do.

**About one in six "vendor posts" is not the vendor.** 17% of what the market counts as a company's own posts are that company resharing somebody else, and for one vendor it is 32%. The system already detects reshares correctly for one internal purpose, but the figures on the Market Monitor screens do not consult it. So loudest-and-quietest rankings, post volume and share of voice all currently credit a vendor for amplifying other people. Sales should not quote per-vendor post counts as owned activity until this is wired through.

**Employer ratings are matching the wrong companies.** Where employer-review data appears, all four current matches in this market are a different company with a similar name — one three-person security startup is matched to a Paris fashion house. No customer alert has fired from it, but the data should not be shown or cited. This is a separate subsystem from the collection work above and is untouched.

**Funding is missing for 45 of 85 vendors,** because their funding-database URL has to be guessed from the company name and the guess lands about two times in three.

**Indeed job listings remain unavailable.** The provider's search has no employer field, so listings cannot be attributed to a specific company reliably. LinkedIn job listings are the supported source.
