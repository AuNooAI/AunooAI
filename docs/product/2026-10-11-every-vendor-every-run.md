# Every vendor, every run
_2026-10-11 · Market Monitor vendor pages and the public market report (aisocnews.com)_

## What shipped
- Vendor collection now covers the whole market on every run: Crunchbase, LinkedIn job listings and LinkedIn company profiles.
- Job boards on a company's own site are found even when they are not at /careers. Four more vendors in AI in the SOC now show their open roles, Prophet Security among them with six.
- A round whose type the company never disclosed now reads "Undisclosed round" instead of "Series Unknown".
- The hiring figure on a vendor page carries the date it was collected.
- Press coverage of a vendor is now scored for relevance and sentiment, so it counts toward the page's view of how the company is talked about.
- A blog post that looks back at earlier news is dated when the news happened, not when the post was edited.

## Why it matters
**Before, a market of 116 vendors was only ever partly read.** The scheduler that decides which vendors to collect did not know which market it was working for, so a small market's run could claim the big market's vendors, read none of them, and mark them done. On top of that, the job-listing batch always took the first 100 vendors in list order, so 16 vendors were never searched at all. The market median for open roles was zero, and that said more about us than about the vendors. Now each run reads every vendor in its market. The first run after the fix found listings at 29 vendors where the previous run had found 19.

**Open roles were missing for companies that do not hire through LinkedIn.** Most of these vendors publish jobs on their own site through a hiring system, and we only looked at one address, /careers. Prophet Security's six roles sat on a page we never opened. We now follow the site's own "Careers" link. Analysts reading a hiring comparison see the roles that exist.

**"Series Unknown" was a stage that does not exist.** Crunchbase uses that label when a company did not disclose what kind of round it raised. Showing it as a stage name made a gap in disclosure look like a fact about the company. The page now says what is true: the round type was not disclosed.

**Press coverage was collected but never judged.** Articles about a vendor from outside sources were linked to the vendor and then left unscored, so the page reported them as unevaluated and sentiment was built from social posts alone. They are now scored the same way, and the backlog is clearing at 200 per hour.

**A revisited announcement no longer moves the timeline.** When a company republishes or edits a post about earlier news, the feed carries the edit date. Prophet's February investment had become an October event. The page now reads the date the post itself states.

## Release notes (copy-ready)
- Vendor data is collected for every vendor in a market on every run.
- Open roles now include jobs posted on a vendor's own hiring system, wherever the site links to it.
- Undisclosed funding rounds are labelled as undisclosed.
- Hiring figures show the date they were collected.
- Press coverage of a vendor is scored for relevance and sentiment.
- Announcements are dated when they happened, not when the post was last edited.

## Demo / walkthrough
Market Monitor, AI in the SOC, open Prophet Security. "Observed active job listings" reads 6 with tonight's date and the company's own careers system as the source. In the Current profile panel, "Latest round" reads "Undisclosed round, Crunchbase, 11 Oct 2026". In Events, the Amex Ventures and Citi Ventures investment is dated 25 February 2026.

## Positioning notes
The market view is only as good as its coverage, and a buyer comparing vendors on hiring or funding will notice a zero that should not be there. This closes the gap between "we track 116 vendors" and "we read 116 vendors", and it does so without adding a data source. It also keeps a promise the page already made: that every figure says where it came from and when.

## Limits and what's next
- The job-board search follows one link from a page it already reads. A board linked only from a page we never open is still missed. Around 20 of 116 vendors have a known board; the rest either hire on LinkedIn or publish nothing machine-readable.
- Crunchbase gives no date or amount for an undisclosed round, so the page cannot say when it happened unless the company's own post does.
- Independent press coverage is thin in the corpus itself: for Prophet, two outside articles against 120 of its own blog posts. Scoring what we have does not collect what we lack.
- A vendor with zero listings still reads as "ahead of" the many other vendors at zero. The ranking is correct; the wording is not.
- This is live on bugfixing only. Oviva, Panaya and Sunstar run the same code and will receive it separately.
