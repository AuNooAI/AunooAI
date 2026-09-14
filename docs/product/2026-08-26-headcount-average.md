# The staff-change panel no longer averages a single company
_2026-08-26 · Market Monitor — headcount_

## What shipped

- The market-wide average and median staff change are held back until enough companies have two readings to average.
- The panel says why the figure is missing, instead of the number quietly disappearing.
- The companies that did move are still listed, and the market's total headcount is unchanged.

## Why it matters

**The panel was showing one company's number as the market's.** It read "Average +1.3%, Median +1.3%, across 1 vendor". That was Dropzone AI's +1.3% printed three times under two statistical labels.

Staff change is measured between two readings of the same company. Only one company has two readings so far, because the earlier collection passes reached 19 of 84 companies before that was fixed. One mover is the correct answer to "who changed"; an average built from it is not a market figure.

Who feels it: anyone reading the panel as a market trend. "The market grew 1.3%" is a very different claim from "one company added one person", and the panel was making the first one.

**The average now waits until it means something.** The product already does this elsewhere — a share-of-voice percentage is withheld when there are too few mentions to rank, and a per-post engagement average is withheld below a handful of posts. Staff change now follows the same rule.

**A missing number explains itself.** The average row simply vanished when there was nothing to show, which reads as a broken page. It now says: "No market average yet: it needs several vendors with two readings, and only one has a second one so far."

## Release notes (copy-ready)

- The market-wide average and median staff change are shown only when several companies have two readings to compare, and the panel explains when they are withheld.
- Individual companies with a measured change are still listed.
- The market's observed total headcount is unaffected: it needs only one reading per company.

## Demo / walkthrough

Market Monitor → SOC Automation → Pulse → Headcount change. The average and median rows are replaced by a line explaining that only one company has a second reading. The mover itself, and the market total of 2,916 people across 80 companies, are unchanged.

## Limits and what's next

**This fills itself in.** The next staff reading is due the morning after this change for the 19 companies read on 20 August, and the following week for the 61 read on 26 August. Once several companies have two readings, the average appears on its own.

**The threshold is five companies.** Below that the movers are shown without an average. That number is a judgement about when a figure stops being one company's news, not a statistical test.
