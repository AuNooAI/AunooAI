"""Incident attachments + enrichment agent tables.

bw_incident_files            — disk-stored file attachments (evidence rows point at them)
bw_incident_enrichment_runs  — one row per agent run (status/stage/stats/brief)
bw_incident_enrichment_candidates — staged review-queue items; UNIQUE per
    (incident, type, ref) so dismissed candidates are never re-proposed.

DDL is IF NOT EXISTS so the file copies safely to tenants whose alembic
chains have drifted (wbm/abm are deployed by file copy, not git).

Revision ID: bw_020_incident_attachments
Revises: tl_001_timeline_mementos
"""

from alembic import op

revision = 'bw_020_incident_attachments'
down_revision = 'tl_001_timeline_mementos'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS bw_incident_files (
            id SERIAL PRIMARY KEY,
            incident_id INTEGER NOT NULL REFERENCES bw_incidents(id) ON DELETE CASCADE,
            evidence_id INTEGER REFERENCES bw_incident_evidence(id) ON DELETE SET NULL,
            filename TEXT NOT NULL,
            mime TEXT,
            size_bytes BIGINT NOT NULL,
            sha256 TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            uploaded_by TEXT,
            uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_bw_incident_files_incident
            ON bw_incident_files(incident_id)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS bw_incident_enrichment_runs (
            id SERIAL PRIMARY KEY,
            incident_id INTEGER NOT NULL REFERENCES bw_incidents(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'running',
            stage TEXT,
            params JSONB,
            stats JSONB,
            brief TEXT,
            error TEXT,
            started_by TEXT,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_bw_enrich_runs_incident
            ON bw_incident_enrichment_runs(incident_id)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS bw_incident_enrichment_candidates (
            id SERIAL PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES bw_incident_enrichment_runs(id) ON DELETE CASCADE,
            incident_id INTEGER NOT NULL REFERENCES bw_incidents(id) ON DELETE CASCADE,
            candidate_type TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            title TEXT,
            snippet TEXT,
            score DOUBLE PRECISION,
            reason TEXT,
            meta JSONB,
            state TEXT NOT NULL DEFAULT 'pending',
            decided_by TEXT,
            decided_at TIMESTAMPTZ,
            CONSTRAINT uq_bw_enrich_cand UNIQUE (incident_id, candidate_type, source_ref)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_bw_enrich_cand_incident
            ON bw_incident_enrichment_candidates(incident_id, state)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bw_incident_enrichment_candidates")
    op.execute("DROP TABLE IF EXISTS bw_incident_enrichment_runs")
    op.execute("DROP TABLE IF EXISTS bw_incident_files")
