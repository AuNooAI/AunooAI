# A company's own blog is no longer counted as coverage of it
_2026-08-26 · Market Monitor — earned coverage and attention_

## What shipped

- Articles published on a company's own website are now reported as the company's own voice, not as third-party coverage of it.
- Earned coverage across the SOC Automation market drops from 22 items to 11 — half of it was vendors' own blogs.
- Posts and articles are now split four ways: the company's LinkedIn, the company's own site, reshares, and everyone else.
- A company can no longer rank into a shared report's top 10 on the strength of its own blog.

## Why it matters

**Earned coverage is the one number where this mattered most.** It is the difference between a company saying it matters and anyone else agreeing. Ten of Dropzone AI's own blog posts, and one of Radiant Security's, were being counted as third parties covering them — half of everything the market recorded as earned coverage.

The cause: the split between "the company said this" and "somebody else said this" was decided by a tag that a company's website article does not carry. LinkedIn posts are tagged. Blog posts are not, so they fell through to the other side.

Who feels it: anyone reading a company's attention figures, or comparing companies on how much others are talking about them. A company that blogs a lot looked like a company others were writing about.

**The classification already existed and nothing was using it.** The platform has always been able to tell a vendor's own site from a publication — it matches the web address against the registry, which is exact. That check was there, correct, and never consulted by the code doing the counting. So this was not a missing rule; it was a read path ignoring the rule that was there.

**One company's blog writing about another still counts as coverage.** Deliberately. Dropzone's blog writing about Crogl is Dropzone talking for Dropzone and genuine outside coverage for Crogl. The match is against the specific company an article is attributed to, not against every monitored company at once — which would have erased real coverage.

**Reporting the four kinds separately rather than merging them.** A LinkedIn post, a post on the company's own site, a reshare of someone else's post, and an article by someone else are four different things. Each is now counted and labelled on its own. Merging any of them into a neighbour credits or discredits a company for words it did not write, which is the same error the reshare fix corrected earlier today one channel over.

## Release notes (copy-ready)

- Articles from a company's own website are now classified as the company's own content rather than as third-party coverage.
- Earned-coverage counts for the SOC Automation market fall from 22 to 11 items; the remainder are reported separately as the company's own site.
- Posts and articles are labelled one of four ways: company LinkedIn, company website, reshare, or third-party.
- Coverage lists show "vendor-owned (own site)" for a company's own web articles.
- The public top-10 selection for shared reports now ranks on third-party coverage only.

## Demo / walkthrough

Market Monitor → SOC Automation → Analysis. The share-of-voice panel's earned figure is now 11 rather than 22, with a separate count for vendors' own websites.

Open Dropzone AI's coverage list: its 10 blog articles read "vendor-owned (own site)", and it has no third-party coverage on record.

## Limits and what's next

**The 30-day figure did not change.** Those blog posts are older than a month, which is why this survived the checks made when the metric shipped. Anyone who quoted a longer-window earned figure before today was quoting a number roughly twice as large as it should have been.

**Employer reviews are still counted as coverage.** Seven Glassdoor items sit in the earned bucket, and they are a different kind of thing again — and in this market they are matched to the wrong companies. Untouched.

**A company with no website on file cannot be recognised.** The match needs a domain in the registry. Every monitored company here has one except Intezer.
