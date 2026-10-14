#!/usr/bin/env python3
"""Save Bright Data's MCP tool list to docs/brightdata_mcp_tools.json.

Listing tools costs nothing; this script never calls a tool. Use --groups to
list the paid groups as well, for example:

    python scripts/brightdata_mcp_tools.py --groups advanced_scraping,scrapers,browser

Reads BRIGHTDATA_MCP_TOKEN from the environment or .env, and writes nothing
that contains it. Spec: docs/BRIGHTDATA_WEB_ACCESS_SPEC.md, section 5.
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def _list(groups: str):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    token = os.getenv("BRIGHTDATA_MCP_TOKEN", "").strip()
    url = f"https://mcp.brightdata.com/mcp?token={token}" + (f"&groups={groups}" if groups else "")
    async with streamablehttp_client(url) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.list_tools()
            return [{"name": t.name, "description": t.description or "", "input": t.inputSchema}
                    for t in res.tools]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--groups", default="", help="comma-separated tool groups to include")
    ap.add_argument("--out", default=str(ROOT / "docs" / "brightdata_mcp_tools.json"))
    args = ap.parse_args()
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    token = os.getenv("BRIGHTDATA_MCP_TOKEN", "").strip()
    if not token:
        print("BRIGHTDATA_MCP_TOKEN is not set", file=sys.stderr)
        return 1
    try:
        tools = asyncio.run(_list(args.groups))
    except BaseException as e:  # noqa: BLE001 — the MCP client raises exception groups
        print(f"listing failed: {str(e).replace(token, '<token>')[:500]}", file=sys.stderr)
        return 1
    text = json.dumps(tools, indent=1)
    if token in text:
        print("refusing to write: the output contains the token", file=sys.stderr)
        return 1
    Path(args.out).write_text(text)
    print(f"{len(tools)} tools written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
