# Emerging Topics: detection that finishes, and tells you when it doesn't
_2026-08-19 · Explore → Emerging Topics; scheduled detection and its alerts_

## What shipped

- Topic detection now always finishes in a known state. When it fails, it says so instead of
  reporting "no topics found".
- Alerts for newly detected topics work again. The default alert settings had been matching
  nothing at all.
- Only administrators can start a detection run, clear detected topics, or change the schedule
  and alert settings. Any signed-in user could do all of that before.
- Two people can no longer start the same scan at the same time and corrupt each other's counts.
- The progress bar no longer freezes part-way through a scan.
- The detail panel for a topic now shows the analysis the system actually stored — the people
  and companies involved, the triggering event, the implications and the scores.

## Why it matters

**Failed scans used to look like quiet news days.** If the text-analysis service was down, or
the database hiccuped, the scan stopped where it was and the screen said no topics were found.
There was no error and no record. Looking at the four customer sites, about half of every scan
ever run had ended this way — 3,052 scans in total, sitting unfinished with nobody aware. An
analyst checking Emerging Topics on one of those days would reasonably conclude nothing was
emerging. Now a failed scan is recorded as failed, with the reason, and the screen shows an
error. Who feels it: analysts, and anyone who trusted an empty screen.

**Alerts were silently switched off.** The default setting said to alert on "accelerating" and
"new_cluster" topics. Neither value matches what the current detection engine produces, so the
filter matched nothing and no alert was ever sent. The defaults now match reality, and existing
settings were migrated across rather than reset. Who feels it: anyone who set up email or
Bluesky alerts and wondered why they were quiet.

**Anyone signed in could wipe the topic history.** "Clear all detected themes" deletes every
detected topic and resets the tracking counters that drive the trend charts. That button, and
the buttons that start scans and change the schedule, only checked that you were logged in.
They are now restricted to administrators. Who feels it: administrators and buyers who ask
about access control.

**Scans could stall the whole site.** The scan did its network and database work on the main
request thread. On one customer site we recorded the site freezing for 22 seconds at a stretch
while a scan ran. That work now happens off to the side, so the rest of the site stays
responsive during a scan. Who feels it: everyone using the site while a scan is running.

**Progress updates went missing.** Progress messages are streamed to the browser, and any
message that happened to be split across two network packets was thrown away — including,
sometimes, the final result. The browser now reassembles them properly. Who feels it: anyone
who watched a scan appear to hang at 60%.

## Release notes (copy-ready)

- Topic detection now records whether each scan succeeded or failed, and shows the reason when
  it fails. Scans no longer report "no topics" when something has gone wrong.
- Fixed the default alert settings for emerging topics, which previously matched no topics and
  so never sent an alert. Existing alert settings are carried over.
- Starting a scan, clearing detected topics, and changing the schedule or alert settings now
  require an administrator account.
- Two scans of the same topic can no longer run at once; the second is refused with a clear
  message.
- Scans no longer slow down the rest of the site while they run.
- Fixed progress updates that could stop part-way through a scan.
- The topic detail panel now shows the stored analysis — actors, events, implications and
  component scores — rather than falling back to older, thinner fields.

## Demo / walkthrough

Explore → **Emerging Topics**.

1. As a non-administrator, the **Run Detection** and **Clear** actions are refused. Sign in as
   an administrator to use them.
2. Press **Run Detection**. The progress bar advances through sampling, theme proposal, article
   assignment, validation and analysis, and finishes with a result. Start a second scan of the
   same topic from another browser and it is refused straight away rather than running twice.
3. Open any detected topic. The panel shows the companies, people and organisations involved,
   the triggering event and timeline, the implications, and the four component scores.
4. Alert settings are under the gear icon → **Notifications**. The choices are now "new theme",
   "ongoing topic" and "accelerating", which is what the engine actually produces.

## Positioning notes

This closes a trust gap rather than adding a capability. The honest version of the story is
that a monitoring feature which silently reports "nothing found" when it has broken is worse
than one that is visibly down, because the customer acts on the silence. Emerging Topics now
distinguishes "we looked and found nothing" from "we could not look". That is a reasonable
thing to say to a buyer who asks how they would know the system had stopped working.

The access-control change is also worth having ready for security questionnaires: destructive
and scheduling actions on shared data are now restricted to administrators.

## Limits and what's next

**The "new topic" versus "ongoing topic" label is not trustworthy, and is unchanged by this
release.** The system decides whether a theme already had earlier coverage by comparing text
similarity against a fixed cutoff. We measured that cutoff this session and it matches 100% of
the article corpus, so the test always answers "ongoing". As a check, we ran two invented
topics through it — a fictional product recall and a fictional licensing reform, neither of
which exists — and both were labelled as having prior coverage from around 40 sources. The
label is currently near-meaningless, and it feeds the "new theme" alert filter.

The cause is the text-similarity model used for article search, which does not separate topics
sharply enough for this comparison. A second, stronger model is already installed on two of the
four customer sites and does separate them in our measurements. Making the labels meaningful
needs a decision on rolling that model out, so it is not promised here. Until then, treat the
"ongoing topic" badge as unreliable and do not build alerting on it.

Also not covered:

- Alerts fire on the topics the engine detects; the quality of those topics is a separate piece
  of work.
- The scan still takes several minutes on a large site. It is no longer able to freeze the site
  while it does, but it is not faster.
