"""Create the Stripe product and the two one-off prices for the paid
analyst call on the market front page. Idempotent: a product is matched by
name and a price by lookup_key, so re-running creates nothing twice. A
price whose amount changed is archived and replaced, because Stripe prices
are immutable; the lookup_key moves to the new price.

Usage:
    STRIPE_SECRET_KEY=sk_test_...  .venv/bin/python scripts/seed_stripe_inquiry.py --dry-run
    STRIPE_SECRET_KEY=sk_live_...  .venv/bin/python scripts/seed_stripe_inquiry.py

Prints the two .env lines to paste. Modelled on saas.aunoo.ai's
scripts/seed_stripe.py with the recurring interval removed.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

import stripe

logger = logging.getLogger("seed_stripe_inquiry")
logging.basicConfig(level=logging.INFO, format="%(message)s")

PRODUCT_NAME = "AI SOC News analyst inquiry"
# (env var, lookup_key, amount in cents, nickname)
PRICES = [
    ("STRIPE_PRICE_INQUIRY_30", "aisocnews-inquiry-30", 40000, "Analyst inquiry, 30 minutes"),
    ("STRIPE_PRICE_INQUIRY_60", "aisocnews-inquiry-60", 70000, "Analyst inquiry, 60 minutes"),
]


def _find_product(name: str):
    for prod in stripe.Product.list(active=True, limit=100).auto_paging_iter():
        if prod.name == name:
            return prod
    return None


def _find_price(lookup_key: str):
    page = stripe.Price.list(lookup_keys=[lookup_key], active=True, limit=1)
    return page.data[0] if page.data else None


def _ensure_product(name: str, dry_run: bool):
    existing = _find_product(name)
    if existing:
        logger.info("  product OK   %s  (%s)", name, existing.id)
        return existing
    if dry_run:
        logger.info("  product NEW  %s  (dry-run)", name)
        return stripe.Product.construct_from({"id": "<dry-run>", "name": name}, key=stripe.api_key)
    prod = stripe.Product.create(name=name)
    logger.info("  product NEW  %s  (%s)", name, prod.id)
    return prod


def _ensure_price(*, product_id: str, lookup_key: str, unit_amount: int,
                  nickname: str, dry_run: bool):
    existing = _find_price(lookup_key)
    if existing and existing.unit_amount == unit_amount:
        logger.info("    price OK   %-28s %s", lookup_key, existing.id)
        return existing
    if existing:
        logger.info("    price OLD  %-28s %s  %d -> %d cents, archiving%s", lookup_key,
                    existing.id, existing.unit_amount, unit_amount,
                    " (dry-run)" if dry_run else "")
    if dry_run:
        logger.info("    price NEW  %-28s (dry-run)", lookup_key)
        return stripe.Price.construct_from(
            {"id": f"<dry-run:{lookup_key}>", "lookup_key": lookup_key}, key=stripe.api_key)
    price = stripe.Price.create(product=product_id, unit_amount=unit_amount,
                                currency="usd", lookup_key=lookup_key, nickname=nickname,
                                transfer_lookup_key=bool(existing))
    if existing:
        stripe.Price.modify(existing.id, active=False)
    logger.info("    price NEW  %-28s %s", lookup_key, price.id)
    return price


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    key = os.getenv("STRIPE_SECRET_KEY")
    if not key:
        logger.error("STRIPE_SECRET_KEY is not set")
        return 2
    stripe.api_key = key
    logger.info("Stripe mode: %s%s", "LIVE" if key.startswith("sk_live_") else "test",
                " (dry-run)" if args.dry_run else "")
    product = _ensure_product(PRODUCT_NAME, args.dry_run)
    lines = []
    for env, lookup_key, cents, nickname in PRICES:
        price = _ensure_price(product_id=product.id, lookup_key=lookup_key,
                              unit_amount=cents, nickname=nickname, dry_run=args.dry_run)
        lines.append(f"{env}={price.id}")
    logger.info("\n# Paste into .env:\n%s", "\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
