# What Aunoo solves that a vanilla AI assistant does not

*Positioning note, 20 September 2026. Written for sales, partners and the connector-directory listing.*

## The claim

A general assistant with web search answers questions about the world as it looks today. Aunoo
gives that assistant what it is missing: a curated corpus held over time, judgments computed
across hundreds of articles, a memory of how each story moved, and a watcher that runs when
nobody is asking. The assistant stays the front door. We are the source it calls and cites.

## What the assistant already does well

Be honest about this, because buyers will test it. An assistant with web search will summarise a
company, find the latest headline, and draft a memo from whatever it retrieves. For a one-off
question about a well-covered subject it is good enough, and it is free at the margin. Anything
we sell has to be something search cannot produce, no matter how good the model gets.

## The seven gaps

### 1. It has no memory of the story

Ask an assistant "what happened with Brand X this quarter" and it re-reads today's search results
and guesses at the order. It does not know that the same recall story surfaced four times, or that
sentiment turned in week three and never recovered.

We keep a timeline per brand and per topic. Each day's articles go through detectors for volume
spikes, sentiment shifts and new-source arrivals, then one model pass names the events that are
genuinely new. Recurring stories fold onto one event with an occurrence count. Weekly and
monthly rollups compact the timeline and a maintained state document says what is live now.
The longer a subscriber stays, the deeper this gets. Search cannot rebuild it.

### 2. It searches. It does not watch

An assistant runs when asked. Nobody asks it every hour whether anything happened, and a poll
loop on a frontier model is expensive and noisy.

Our observer agents run on a schedule against the incoming stream, match articles to a written
instruction, and send an alert once. Alert identity is content-based, so the same story a day
later is a bump on the existing alert rather than a new email. A second judge now scores each
flagged article on "does this match the instruction" and holds the weak ones out of the email
for review. The assistant reads the alert; it did not have to find it.

### 3. It sees the open web today, not a curated corpus

Web search returns what ranks. It misses paywalled trade press, non-English coverage, social
posts, and anything older than the index cares about. It also returns junk that mentions the
right words.

We collect from our own news aggregator, licensed news APIs, arXiv, Bluesky, Reddit and X, then
translate at insert so a German or Japanese article reads in English with the original kept.
Every article passes a relevance gate that scores alignment to the topic's definition, and
readers only see what passed. For a market topic that means vendor press releases are kept
because they are the signal, and an earnings story that merely mentions "security" is not.

### 4. It cannot compute across hundreds of articles

A model reading twenty search results cannot tell you whether the field agrees, how polarised
the coverage is, whether a claim is spreading through the same outlets that spread the last
one, or where a vendor sits on the maturity curve. Those are calculations over a corpus, not
readings of a page.

We compute them and expose them as tools: consensus and polarisation over a topic's coverage,
propagation fingerprints that show which sources carry a claim and in what order (the detector
is under a provisional patent), brand risk from earned press only, market maturity maps for a
vendor set, and forecast trajectories for a topic. Each returns the figure and the articles that
produced it.

### 5. It cannot tell you how sure it is

An assistant's answer is text. There is no probability attached, so downstream code and
downstream humans cannot set a threshold.

Our judgment steps are moving to typed answers with a probability per option. Relevance,
whether a citation supports a claim, whether two issues are the same event, whether an article
answers a query: each is a question with a calibrated score, measured against blind human
labels before it is allowed to decide anything. A subscriber's own agent can act on "0.92
supports" in a way it never could on a paragraph.

### 6. It cannot show its evidence in a form a compliance team accepts

When an assistant states a fact, the audit trail is a chat transcript. A communications,
legal or compliance buyer cannot forward that.

Every figure we return carries the article identifiers, the scores, the model and the
timestamp. Alerts sit on the timeline as new or ongoing. Reports and briefings carry the EU AI
Act Article 50 disclosure. A human can click from any claim to the sources that produced it,
and see which model made the call.

### 7. Its cost and quality are the vendor's to change

Per-question pricing on a frontier model is fine for a person. It is not fine for a pipeline
that scores ten thousand articles a day, and quality can shift with a model update nobody
announced.

We run the cheapest model that fits each step, measured before and after on our own labels,
and we log every model call with its cost. Four typed judgments on an article cost about four
cents per thousand articles. The buyer gets a predictable subscription, and we absorb the
model churn.

## What we do not claim

We are not a better chat interface, and we do not intend to build one. We do not replace web
search for one-off questions on well-covered subjects. Our judgments are as good as the corpus
under them, and a topic with a thin or badly defined collection produces thin results. Dates,
arithmetic and anything requiring a model to reason over numbers still go through deterministic
checks, because the decision models we use read text literally.

## One line

Aunoo is the intelligence source an assistant can trust: curated coverage, computed judgments
with probabilities, a memory of every story, and a watcher that runs when nobody is asking.
