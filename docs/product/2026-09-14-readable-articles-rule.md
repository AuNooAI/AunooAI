# Every reader sees the same articles
_2026-09-14 · Auspex, deep research, MCP, newsletters_

## What shipped

The rule that decides whether an article is fit to show, the one the dashboard has always
applied, now sits in the data layer. Auspex chat, deep research, the assistant tools
reached over MCP, the newsletter and the futures views all go through it. An article that
collection swept in by mistake and quality control marked as off-topic no longer reaches
any of them.

## Why it matters

Quality control keeps what it rejects, because the rejects are training data. That is the
right design, but it meant every new reader started out seeing the rejects until someone
noticed. Today it was an assistant writing a competitor briefing from 389 articles that
were not about the competitor. Yesterday it could have been a newsletter.

## What it does not change

Training, audit and the analytics that look for emerging themes still read the raw store,
on purpose, and say so in code.

## Where it is live

All running tenants, 14 September 2026.
