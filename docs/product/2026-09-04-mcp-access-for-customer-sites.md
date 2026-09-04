# Connect Claude and ChatGPT directly to a customer site
_2026-09-04 · MCP server on the single-site (monolith) deployment; live on bugfixing only_

## What shipped
- Any AI assistant that speaks the Model Context Protocol (Claude Desktop, Claude Code, Cursor, the claude.ai and ChatGPT connector menus) can now connect to a customer site and use its news tools directly.
- Two ways to sign in: an access key an administrator hands out, or the standard "Connect" button flow where the user logs into the site and clicks Allow.
- Eleven tools: list the topics the site tracks, pull recent articles for a topic, search by keyword or category, sentiment and category breakdowns, semantic search with an AI analysis, follow-up questions, live news search, and web search where the site has it configured.
- Three ready-made playbooks the assistant can run: a topic briefing, a deep dive on a question, and a keyword scan.
- An audit log of every call: who, which tool, how long, and whether it worked.

## Why it matters
Before, a customer who wanted to use Aunoo's data inside Claude or ChatGPT had only the SaaS product. A customer with their own dedicated site had no way in except the web UI. Now the dedicated site offers the same connection the SaaS product does, and the customer's own login controls it.

For an analyst: ask Claude "what happened on our brand topic this week and how was the tone" and it pulls the answer from the site's own articles, with links to each one, instead of guessing from training data.

For an administrator: hand out a key with an expiry date, see every call in one table, revoke a key or disconnect an app in one step. Deactivating a user account cuts off everything that user connected.

For a buyer: the dedicated-site tier no longer loses the "works inside your AI assistant" feature to the SaaS tier.

## Release notes (copy-ready)
- Your Aunoo site now works as a connector for Claude, ChatGPT, Cursor and other MCP-capable assistants.
- Connect with a key from your administrator, or click Connect in the assistant and sign in to the site.
- Available tools: topic list, recent articles, keyword and category search, sentiment and category breakdowns, semantic search with analysis, follow-up questions, live news search.
- Built-in playbooks: topic briefing, deep dive, keyword scan.
- Administrators can issue keys with an expiry date, review a full call log, and revoke access at any time.

## Demo / walkthrough
- Claude Code: `claude mcp add --transport http aunoo https://<site>/mcp --header "Authorization: Bearer <key>"`, then ask "call list_capabilities" and "give me a topic briefing for <topic>".
- claude.ai: Settings, Connectors, Add custom connector, URL `https://<site>/mcp`, leave the client fields empty. A browser tab opens the site login, then a one-page Allow / Deny screen. After Allow the connector shows as connected and the tools appear in the chat.
- The consent screen names the app asking to connect, the account it will act as, and the tools it can call.

## Positioning notes
Closes the gap between the dedicated-site deployment and the SaaS product on "use it from your AI assistant". The connection uses the same open standard and login flow the major assistants already support, so there is nothing to install on the customer side.

## Limits and what's next
- Live on one internal site (bugfixing) as of today. Customer sites (sunstar, wiley, wileytest) do not have it yet; each needs the code copied, a database migration, and a restart.
- Verified with scripts, including the full sign-in and Allow flow. Not yet verified by clicking through the claude.ai connector in a real browser, or by adding it to Claude Code. Do that before showing a customer.
- Tools are the general news tools only. Brand Watcher, forecast, consensus and market-horizon data are not exposed yet. Adding them is one tool each on top of services the site already has.
- The site runs on a single worker, so a service restart during the five-minute Allow window makes the user click Connect again.
- Keys are managed by an administrator from the command line or an admin API. There is no settings-page panel yet.
- Requests from the assistant count against the same AI budget as the site's own analysis for the tools that call a model (semantic search, follow-up questions, natural-language search).
