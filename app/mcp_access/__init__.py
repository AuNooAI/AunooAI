"""HTTP MCP server for this Aunoo site.

Exposes the Auspex tools over the Model Context Protocol at ``POST /mcp``
with two ways to authenticate: a static ``aunoo_…`` bearer key (Claude Code,
Claude Desktop, Cursor) or an OAuth 2.1 access token obtained through the
dynamic-client-registration flow (the claude.ai and ChatGPT connector UIs).

Ported from saas.aunoo.ai's ``app/skills`` + ``app/oauth`` with the
multi-tenant parts (packs, tiers, tenant ids, Redis) removed. One site is
one MCP server.
"""

from .router import router  # noqa: F401
