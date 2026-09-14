# Voices: what doctors say about a brand, next to what patients say
_2026-09-14 · Brand Watcher (new Voices tab, Social tab chips), Market Monitor Top voices, MCP server_

## What shipped
- A new **Voices** tab in Brand Watcher that sorts everything said about a brand on social
  media by who said it: patients, clinicians, caregivers, customers, employees, press,
  investors, the brand's own accounts.
- Two audiences side by side, with a plain-language digest of what each one says, quotes
  copied from the posts, and a list of what the posts ask for.
- An **Export HTML** button that turns the view into a single file the brand's team can open,
  search and forward: the audience table, the two compared audiences with their digests and
  quotes, and every post.
- Every post on the Social tab now shows who wrote it.
- The Top voices table in Market Monitor now says which audience each account belongs to,
  even before anyone has profiled it.
- Brand and market data over the MCP connector: a connected assistant can read the brand's
  numbers, articles, perception, voices and alerts, and the market's vendors, analyses, top
  voices, maturity map and briefings.

## Why it matters
**Before**, a health provider could see that sentiment about them was mixed, but not that
the negative half came from the doctors who refer patients to them and the positive half from
the patients on the programme. Those are two different problems with two different owners,
and one number hid both. **Now**, Oviva's team opens Voices and sees 26 patient posts running
slightly positive next to 7 clinician posts running clearly negative, with the clinician
digest naming the thread, the country, the date and the two things those doctors asked for.
Who feels the difference: the person at the brand who has to decide what to fix first, and the
analyst who has to explain the sentiment number to them.

**The digest is written for the client, not about them.** The first version said clinicians
"distrust" and "resent" the brand. That is a verdict from seven posts. The digest now says
what the posts say and how many say it, gives the reader the context to weigh it (six of seven
posts, one German GP thread on X, one date), and ends with what the posts ask for, phrased as
things the brand could act on. Wording the brand's own team can forward without editing.

**Who is speaking comes from the account, not just one post.** A GP's single post may not
say they are a GP. When the account has been profiled, or when its other posts keep reading
the same way, that wins over the reading of one post. On Oviva 41 of 42 posts now take their
audience from the account.

## Release notes (copy-ready)
- New Voices tab in Brand Watcher: posts about your brand grouped by who wrote them, with a
  sentiment split per audience.
- Compare any two audiences side by side. Each side has a short digest with quotes from the
  posts and a list of what those posts ask for.
- Export the Voices view as a self-contained HTML file.
- Social tab posts show the author's role.
- Market Monitor Top voices shows each account's audience.
- MCP connector: new tools for brand stats, articles, perception, voices and alerts, and for
  market vendors, analyses, top voices, maturity map and briefings, plus a "brand briefing"
  prompt.

## Demo / walkthrough
Brand Watcher → Voices. The tiles across the top are the audiences, ranked by volume; click
two to compare them. On a health site the view opens on Clinicians vs Patients. Each column
shows the count and sentiment split, the digest (context line, summary, themes with quotes,
"What these posts ask for"), and the posts with the reason the role was assigned. Social tab:
the small chip next to the author's name is the role. Market Monitor → Top voices: the Role
column; italic means the reading came from the account's posts rather than a profile.

## Positioning notes
This is the "stakeholder split" that reputation tools do not do for social media: they report
sentiment and reach, not whether the person speaking is the customer, the referrer, the
regulator or the company itself. For a healthcare brand the referrer's view decides growth,
and it is a different signal from the patient's. The same split works for a publisher
(academics, librarians, students) or a security vendor (practitioners, analysts, customers)
once the persona list is set for that customer.

## Limits and what's next
- **Live on Oviva only.** Wiley's sites have the code but the tab is hidden, because their
  audiences (academics, librarians, students, authors) need their own persona list before the
  view says anything useful there.
- **Social and community posts only.** News articles are written by journalists and quote
  doctors; pulling quoted voices out of news is separate work. Trustpilot, the largest patient
  voice for a provider like Oviva, is not collected yet.
- **Small numbers.** Oviva's clinician side is seven posts from six accounts, mostly one
  thread. The digest says so, and the reader should treat it as a lead, not a survey.
- **The role reader matters.** The cheaper model on Oviva read prescribing GPs as patients;
  it was switched to a stronger one. A new site's split should be checked by eye before it is
  shown to the customer.
- **One post from a different company** with the same name (Oviva Therapeutics) reached the
  view before it was excluded. The exclusion now runs before any scoring; look-alike names
  should be added to a brand's exclusion list at setup.
