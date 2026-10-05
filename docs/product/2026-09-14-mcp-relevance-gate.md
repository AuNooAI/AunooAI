# Assistants see the same articles the dashboard shows
_2026-09-14 · MCP tools, Auspex_

## What shipped

Every article list an assistant pulls through the MCP connection now applies the same
relevance cut the dashboard applies. Articles that a topic's keywords swept in by
accident, such as an iOS release note matching "second nature" and "app", or a Juniper
Networks earnings story under the Juniper weight-loss brand, are no longer handed to an
assistant writing a briefing.

## Why it matters

A competitor read-out for a customer described three of its brand topics as badly
polluted. The dashboard was clean the whole time; the assistant was reading the raw
collection behind it. Two readers of the same data disagreeing about what is in it is
worse than either being wrong alone.

## Also

The Second Nature keywords on that customer's site now match the brand name as an exact
phrase, which removes the source of most of that topic's noise at collection time rather
than hiding it afterwards.

## Where it is live

All running tenants, 14 September 2026.
