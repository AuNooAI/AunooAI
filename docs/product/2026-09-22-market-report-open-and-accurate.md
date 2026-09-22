# The market report is free to read, and it stopped reporting things that never happened
_2026-09-22 · aisocnews.com, the public AI-in-the-SOC market report; the same report on the oviva and panaya sites_

## What shipped

**The whole report is open.** Every vendor, every figure, every chart, no sign-in and no blur.
The trial form is gone.

**The only thing we sell now is MCP access, at $279 a month.** It gives a customer's own AI
tools a key to query the data directly. The $179 plan that used to unlock the pages has been
withdrawn, because the pages are no longer locked.

**Four things the report was getting wrong are fixed.** Two of them were visible to anyone who
read the page.

- A vendor's Crunchbase record going blank was published as a funding round.
- An acquisition was reported backwards, naming the wrong company as the buyer.
- Seven "market moves" were one person joining or leaving a company of five.
- A panel meant to show how vendor headcounts moved showed a dash instead of every number.

**The report will also be more current from now on.** The collector was pulling a year of old
vendor posts every day and filing them by their original date, so genuinely recent news was
buried in back-fill.

## Why it matters

**Reading is free; not having to read is what costs money.**
Before, a reader who followed a shared link saw a sample: ten vendors named out of ninety-seven,
figures blurred out, and a form asking them to request a trial. The pitch was "pay to see the
rest of the page". Now the page is complete and the pitch is different. A buyer pays so their
own assistant can ask the data questions instead of them reading answers off a chart. That is a
cleaner thing to sell and a much better shop window.

**"StrikeReady: last funding type changed from series_a to series_unknown" was on the page.**
Nothing happened. Crunchbase stopped knowing what StrikeReady's last round was, and we announced
it as funding news. The rule that produced it treated any change as an event without asking
which direction the change went. The same rule is now applied consistently, and the same module
already got it right for dollar amounts: a funding total that falls is a correction, not news.

**One entry said the opposite of the truth.** The page read "Wirespeed: acquired us for our
ability to stop cyber threats". Wirespeed did not acquire anyone. Coalition acquired Wirespeed.
The sentence had been cut at "Inc." in "Coalition, Inc.", the remainder was taken as the news,
and the company name we attached made it read as the buyer. The same cut was truncating people's
names in hiring announcements at "Dr." and "J.T.". Eighty-six titles were corrected here and
three more on the oviva site.

**Seven of eleven headcount "moves" were one person.** A five-person company losing one employee
cleared a ten-per-cent threshold. An analyst scanning the market does not need to know that, and
it crowds out the moves that matter. A move now has to be real in absolute terms as well as
proportionally.

**The headcount panel was showing dashes.** Four rows that should have read "20 to 22 on
LinkedIn, +10%" read "LinkedIn headcount" and an em-dash, because the code asked for the numbers
under names that were never stored. Anyone who opened that panel learned nothing from it.

**Reports were being filled with last year's news.** Of 387 vendor posts collected on the oviva
site in a month, only 18 were published in that month. Everything else reached back through the
year, and each one was filed under the date it was written, so a report covering the last 30
days saw almost none of it. That is why the oviva report showed six items, all of them job
counts. Old posts are now dropped at collection, which also stops us paying an AI model to read
them.

## Release notes (copy-ready)

- The market report is now free to read in full. Every vendor, every figure, no sign-in.
- Subscriptions are now a single plan: MCP access, $279 a month, giving your AI tools a key to
  query the market data directly.
- Fixed: a vendor's funding record going blank is no longer reported as a funding round.
- Fixed: an acquisition that named the wrong company as the buyer.
- Fixed: announcement headlines were being cut short at abbreviations such as "Inc." and "Dr.",
  which sometimes changed their meaning.
- Fixed: the LinkedIn headcount panel showed a dash instead of the change.
- Headcount changes of a single person at very small companies no longer appear as market moves.
- Reports now cover recent vendor announcements rather than a back-fill of older ones.

## Demo / walkthrough

Open aisocnews.com with no session at all, in a private window. The front page is complete: no
blurred blocks, no "a vendor not shown in this view", no trial form. Click into **Market moves**
and the count reads 30 for the period. Open **Hiring**, scroll to the Headcount block, and the
four rows now read "20 to 22 on LinkedIn +10%", "37 to 33 -10.8%", "33 to 37 +12.1%" and
"6 to 16 +166.7%".

The subscribe page is the **MCP access** link in the header. It now offers one plan and opens
with "Everything here is open to read."

## Positioning notes

The old shape put us in an awkward category: a paywalled research page competing with analyst
newsletters that are mostly free to read. The new shape is clearer. The research is free and the
machine-readable feed is the product, which is the same shape as the market data businesses that
sell APIs rather than PDFs.

It also removes an objection we could not answer well. A prospect who saw the blurred page had
no way to judge the quality of what was behind it, so the trial form was asking for trust before
showing anything. Now they can read everything and decide whether having it inside their own
tools is worth $279.

## Limits and what's next

**The corrections do not rewrite history.** Old vendor posts already collected keep their dates,
so the oviva report will not fill up retroactively. It improves as new posts arrive.

**The oviva market is genuinely small.** It tracks 7 vendors against 97 on the AI-SOC market, so
its report will always be quieter. The back-fill fix removes an artificial cause of emptiness,
not the real one.

**One unresolved question with a supplier.** Between 1 and 21 September our LinkedIn posts
supplier delivered 67,239 records where our request capped them at 16,116. It corrected itself
on 22 September with no change from us. A billing query asking what changed and for a credit on
the excess has been sent.

**Event headlines are still the first sentence of the post.** They are no longer cut in the
wrong place, but a post that opens with a hook still leads with the hook. Choosing the sentence
that carries the news for every kind of announcement, not just hiring, is the obvious follow-on.

**Nothing changed for the sites that do not run the market report.** Wiley, wileytest and wbm do
not have it.
