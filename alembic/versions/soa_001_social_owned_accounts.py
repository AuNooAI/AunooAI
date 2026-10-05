"""Register a company's own social accounts on tenants without entity tables.

A company's own posts are claims, not opinion about it, and the Brand Watcher
Social tab keeps them out of sentiment by checking the author against
``bw_entity_social_identities``. That table arrived with the entity migrations
(ei_002), which the Wiley trees never took, so on wiley and wileytest Wiley's
own Bluesky accounts counted as public sentiment about Wiley.

This creates only the registry, with the same shape as ei_002, so a tenant
without the rest of the entity layer can still record which accounts a company
runs. Idempotent: a no-op wherever ei_002 already ran. These trees have
diverged, so it is copied between them with only ``down_revision`` changed.

Revision ID: soa_001
Revises: sc_001
Create Date: 2026-09-24
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'soa_001'
down_revision = 'sc_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS bw_entity_social_identities (
        id                  BIGSERIAL PRIMARY KEY,
        brand_id            INTEGER NOT NULL REFERENCES bw_brands(id) ON DELETE CASCADE,
        social_account_id   INTEGER NOT NULL REFERENCES social_accounts(id) ON DELETE CASCADE,
        relationship        VARCHAR(24) NOT NULL,
        verification_method VARCHAR(24) NOT NULL,
        confidence          DOUBLE PRECISION,
        status              VARCHAR(16) NOT NULL DEFAULT 'proposed',
        valid_from          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        valid_to            TIMESTAMPTZ,
        provenance          JSONB NOT NULL DEFAULT '{}'::jsonb,
        verified_by         TEXT,
        verified_at         TIMESTAMPTZ,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT ck_bw_entity_identity_rel CHECK (relationship IN
            ('owned_company','product','executive','employee','community',
             'unofficial','critic','advocate')),
        CONSTRAINT ck_bw_entity_identity_method CHECK (verification_method IN
            ('manual','linked_from_domain','provider','content_inference')),
        CONSTRAINT ck_bw_entity_identity_status CHECK (status IN
            ('proposed','verified','rejected','retired'))
    )""")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_bw_entity_identity_active
        ON bw_entity_social_identities (brand_id, social_account_id, relationship)
        WHERE valid_to IS NULL""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_identity_account
        ON bw_entity_social_identities (social_account_id, status)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_entity_identity_owned
        ON bw_entity_social_identities (social_account_id)
        WHERE relationship = 'owned_company' AND valid_to IS NULL""")


def downgrade() -> None:
    # Nothing to drop: on an entity tenant the table belongs to ei_002, and on
    # the others dropping it would throw away operator decisions.
    pass
