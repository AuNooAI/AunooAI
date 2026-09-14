"""Manage MCP bearer keys from the shell.

The plaintext key is printed once by ``mint`` and never stored; only its
sha256 is. Give the key to the person who owns the user account, or paste it
into a Claude Code / Cursor MCP config as ``Authorization: Bearer <key>``.

Usage:
    ./.venv/bin/python scripts/mcp_keys.py mint --user admin --name "claude-code" [--expires-days 90]
    ./.venv/bin/python scripts/mcp_keys.py list [--user admin]
    ./.venv/bin/python scripts/mcp_keys.py revoke --id 3
    ./.venv/bin/python scripts/mcp_keys.py calls [--user admin] [--limit 50]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running directly from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from app.mcp_access import keys, store  # noqa: E402


def _fmt(value) -> str:
    if value is None:
        return "-"
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)


def cmd_mint(args: argparse.Namespace) -> int:
    username = args.user.lower()
    if not store.user_exists_active(username):
        print(f"no active user named {username!r}", file=sys.stderr)
        return 2
    plaintext, row = keys.mint_key(
        username=username, name=args.name, expires_days=args.expires_days, created_by="cli",
    )
    print(f"Key #{row['id']} for {username} ({args.name}); expires {_fmt(row.get('expires_at'))}")
    print("Plaintext (shown once, not stored):")
    print(plaintext)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    rows = store.list_api_keys(args.user)
    if not rows:
        print("no keys")
        return 0
    print(f"{'id':>4}  {'user':<16} {'name':<24} {'prefix':<12} {'active':<6} {'created':<16} {'expires':<16} {'last used':<16}")
    for r in rows:
        print(f"{r['id']:>4}  {r['username']:<16} {r['name'][:24]:<24} {r['key_prefix']:<12} "
              f"{'yes' if r['is_active'] else 'no':<6} {_fmt(r['created_at']):<16} "
              f"{_fmt(r['expires_at']):<16} {_fmt(r['last_used_at']):<16}")
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    if store.revoke_api_key(args.id):
        print(f"revoked key #{args.id}")
        return 0
    print(f"no active key with id {args.id}", file=sys.stderr)
    return 1


def cmd_calls(args: argparse.Namespace) -> int:
    rows = store.list_tool_calls(args.user, args.limit)
    if not rows:
        print("no calls")
        return 0
    print(f"{'id':>6}  {'when':<16} {'user':<14} {'auth':<8} {'tool':<30} {'status':<8} {'ms':>6}  key/client")
    for r in rows:
        who = r.get("api_key_id") or r.get("oauth_client_id") or "-"
        print(f"{r['id']:>6}  {_fmt(r['created_at']):<16} {(r.get('username') or '-'):<14} "
              f"{r['auth_kind']:<8} {r['tool_name'][:30]:<30} {r['status']:<8} "
              f"{(r.get('duration_ms') or 0):>6}  {who}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("mint", help="create a key and print it once")
    p.add_argument("--user", required=True, help="username that owns the key")
    p.add_argument("--name", required=True, help="label, e.g. the client it is for")
    p.add_argument("--expires-days", type=int, default=None)
    p.set_defaults(fn=cmd_mint)

    p = sub.add_parser("list", help="list keys (no secrets)")
    p.add_argument("--user", default=None)
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("revoke", help="deactivate a key")
    p.add_argument("--id", type=int, required=True)
    p.set_defaults(fn=cmd_revoke)

    p = sub.add_parser("calls", help="recent tool calls")
    p.add_argument("--user", default=None)
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(fn=cmd_calls)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
