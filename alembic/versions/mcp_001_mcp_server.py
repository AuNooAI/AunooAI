"""Tables for the HTTP MCP server (app/mcp_access).

Two ways for an assistant to call this site's tools: a static bearer key
(mcp_api_keys, sha256 stored, plaintext shown once) or an OAuth 2.1 access
token obtained through dynamic client registration (oauth_clients,
oauth_authorization_codes, oauth_refresh_tokens). Every tool call lands in
mcp_tool_calls so an admin can see who called what and how long it took.

All rows hang off users.username. Deactivating a user is enough to cut off
their keys and tokens; deleting one removes them.

Revision ID: mcp_001
Revises: kg_lang_001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'mcp_001'
down_revision = 'kg_lang_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'mcp_api_keys',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('username', sa.Text(),
                  sa.ForeignKey('users.username', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('key_prefix', sa.String(16), nullable=False),
        sa.Column('key_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.Text(), nullable=True),
    )
    op.create_index('ix_mcp_api_keys_username', 'mcp_api_keys', ['username'])

    op.create_table(
        'oauth_clients',
        sa.Column('client_id', sa.String(64), primary_key=True),
        sa.Column('client_secret_hash', sa.String(64), nullable=False),
        sa.Column('client_name', sa.String(200), nullable=False),
        sa.Column('redirect_uris', postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    op.create_table(
        'oauth_authorization_codes',
        sa.Column('code', sa.String(64), primary_key=True),
        sa.Column('client_id', sa.String(64),
                  sa.ForeignKey('oauth_clients.client_id', ondelete='CASCADE'), nullable=False),
        sa.Column('username', sa.Text(),
                  sa.ForeignKey('users.username', ondelete='CASCADE'), nullable=False),
        sa.Column('redirect_uri', sa.Text(), nullable=False),
        sa.Column('scope', sa.String(64), nullable=False),
        sa.Column('code_challenge', sa.String(128), nullable=False),
        sa.Column('code_challenge_method', sa.String(8), nullable=False, server_default='S256'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index('ix_oauth_codes_expires', 'oauth_authorization_codes', ['expires_at'])

    op.create_table(
        'oauth_refresh_tokens',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('client_id', sa.String(64),
                  sa.ForeignKey('oauth_clients.client_id', ondelete='CASCADE'), nullable=False),
        sa.Column('username', sa.Text(),
                  sa.ForeignKey('users.username', ondelete='CASCADE'), nullable=False),
        sa.Column('scope', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index('ix_oauth_refresh_user_client', 'oauth_refresh_tokens',
                    ['username', 'client_id'])

    op.create_table(
        'mcp_tool_calls',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('username', sa.Text(),
                  sa.ForeignKey('users.username', ondelete='SET NULL'), nullable=True),
        sa.Column('api_key_id', sa.Integer(),
                  sa.ForeignKey('mcp_api_keys.id', ondelete='SET NULL'), nullable=True),
        sa.Column('oauth_client_id', sa.String(64), nullable=True),
        sa.Column('auth_kind', sa.String(16), nullable=False),
        sa.Column('tool_name', sa.String(64), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('error_code', sa.String(64), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('request_bytes', sa.Integer(), nullable=True),
        sa.Column('response_bytes', sa.Integer(), nullable=True),
        sa.Column('user_agent', sa.String(400), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index('ix_mcp_tool_calls_created', 'mcp_tool_calls', ['created_at'])
    op.create_index('ix_mcp_tool_calls_user_created', 'mcp_tool_calls',
                    ['username', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_mcp_tool_calls_user_created', table_name='mcp_tool_calls')
    op.drop_index('ix_mcp_tool_calls_created', table_name='mcp_tool_calls')
    op.drop_table('mcp_tool_calls')
    op.drop_index('ix_oauth_refresh_user_client', table_name='oauth_refresh_tokens')
    op.drop_table('oauth_refresh_tokens')
    op.drop_index('ix_oauth_codes_expires', table_name='oauth_authorization_codes')
    op.drop_table('oauth_authorization_codes')
    op.drop_table('oauth_clients')
    op.drop_index('ix_mcp_api_keys_username', table_name='mcp_api_keys')
    op.drop_table('mcp_api_keys')
