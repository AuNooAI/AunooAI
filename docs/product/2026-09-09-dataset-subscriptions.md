# aisocnews.com sells the intelligence feed: $179/month, or $279 with MCP access
_2026-09-09 · aisocnews.com (the AI in the SOC market site), Stripe checkout, the MCP server_

> **Superseded.** The $179 plan was withdrawn on 2026-09-22, and MCP access dropped from $279 to $139 a month on 2026-10-08. See `docs/product/2026-10-08-mcp-access-139.md`.

## What shipped
- The **intelligence feed** at $179/month: the whole site with every
  monitored vendor named and every figure shown — the attention rankings,
  hiring numbers and the analyst benchmark that the free view holds back.
- **Intelligence feed + MCP access** at $279/month: the same, plus a key
  that lets the buyer's AI tools (Claude, ChatGPT, their own agents) query
  the coverage directly through our MCP server.
- An "Intelligence feed" button in the site's top bar, a plans page at
  aisocnews.com/subscribe, and Stripe's hosted checkout behind it. Payment,
  cards and cancellation all live with Stripe; we never see a card number.
- A setup guide at aisocnews.com/mcp-help with copy-paste configurations
  for Claude Code, Claude Desktop, Cursor, VS Code and home-built agents.
- Self-serve recovery: a buyer who loses the access mail can re-issue
  their credentials from the payment success page. The old link and key
  stop working, new ones are shown once and mailed again.

## Why it matters
Until now the site had two speeds: free readers saw a capped view, and the
only paid product was an analyst call booked by hand. Anyone convinced by
the free tier had no self-serve way to pay. Now the reader who wants the
numbers clicks, pays, and is inside the full site within a minute — the
access link arrives on the success page and by mail. Cancelling in Stripe
ends access on its own; nobody has to remember to turn anything off.

The MCP plan is for the growing share of readers who arrive through AI
assistants (the site converted its first ChatGPT-referred vendor request
this week): it turns the site from pages into a data source their tools
can query.

## Release notes (copy-ready)
- Subscribe to the AI SOC intelligence feed for $179/month: every
  monitored vendor, every metric, updated as we collect.
- Add MCP access for $279/month and query the same data from Claude,
  ChatGPT or your own agents. Setup takes one command; the guide is at
  aisocnews.com/mcp-help.
- Cancel any time from your Stripe receipt; access runs to the end of the
  paid month.

## Demo / walkthrough
aisocnews.com → "Intelligence feed" in the top bar (or /subscribe) → pick
a plan, name and email → Stripe checkout → the success page shows the
access link (and the MCP key on that plan), repeated by mail. The whole
flow was exercised with a real Stripe subscription before launch,
including cancellation and revocation.

## Positioning notes
This makes the free site a funnel with three paid exits at different
depths: a one-off analyst call ($250/$450), the continuous feed
($179/month), and machine access ($279/month). The MCP tier is the
differentiator — none of the analyst firms sell their coverage as
something an AI agent can query.

## Limits and what's next
- No account page: the access link is the credential. Recovery exists
  (the success page re-issues), but there is nothing to log into.
- The RSS/JSON feeds stay on the free tier; a subscriber key does not
  open them yet.
- One market only (AI in the SOC); prices are fixed in code and Stripe;
  no VAT/tax collection (existing decision from the analyst-call flow).
- Claude's and ChatGPT's own web connector UIs want OAuth, not a pasted
  key, so the guide covers the clients that accept a bearer header
  (Claude Code, Claude Desktop via bridge, Cursor, VS Code, custom
  agents). OAuth for subscriber keys is the obvious follow-on if buyers
  ask for the web UIs.
