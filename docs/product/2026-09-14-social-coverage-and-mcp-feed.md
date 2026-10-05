# More social posts per day, and the social feed reachable by assistants
_2026-09-14 · Keyword monitor, MCP tools, Market Monitor_

## What shipped

- Social collection asks each platform for 25 posts per keyword per run instead of 10,
  the figure the news APIs were tuned for. A day's social coverage was capped at ten
  posts per platform per keyword, and a day the provider was down stayed empty forever.
- Assistants connected over MCP can now call `get_social_posts` for a brand: the Social
  tab's feed with relevance, sentiment, engagement, and the original text next to the
  English translation. Until now the topic tools returned news only.
- On the Oviva site, the market-watch keywords were built for a cybersecurity market and
  searched "Numan security"; they now search the weight-loss market, and the topic
  describes what it is about and what it is not.

## Why it matters

A week of social data for a small brand looked thin, and part of that was real, but part
was a cap nobody had set on purpose and a four-day gap from an exhausted API key. Both
are gone. And an assistant asked about a brand's reputation could not see the social
posts at all, which is where most reputation lives.

## Where it is live

All running tenants for the collection and MCP changes; the market retune is Oviva's.
