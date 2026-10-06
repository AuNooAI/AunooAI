#!/usr/bin/env python3
"""Cron entry for brand-judgment retries on sites without the enrichment
retry sweep (app/services/brand_retry.py). Run from the site's tree:

    cd /home/orochford/tenants/<site>.aunoo.ai && .venv/bin/python scripts/brand_retry.py
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    from app.database import get_database_instance
    from app.services.brand_retry import retry_brand_judgments
    # No enrichment sweep on these sites, so admitted items whose analysis
    # failed are retried here too.
    out = asyncio.run(retry_brand_judgments(get_database_instance(), include_pending=True))
    out.pop("_service", None)
    print(json.dumps(out, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
