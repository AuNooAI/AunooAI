"""add llm retry state and processing tables

Revision ID: 9c7373d1f370
Revises: ea19ee445d19
Create Date: 2025-11-19 16:44:01.503085

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c7373d1f370'
down_revision: Union[str, None] = 'ea19ee445d19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create LLM retry state table for circuit breaker pattern
    op.execute("""
        CREATE TABLE IF NOT EXISTS llm_retry_state (
            id SERIAL PRIMARY KEY,
            model_name VARCHAR(255) NOT NULL UNIQUE,
            consecutive_failures INTEGER DEFAULT 0,
            last_failure_time TIMESTAMP,
            last_success_time TIMESTAMP,
            circuit_state VARCHAR(50) DEFAULT 'closed',
            circuit_opened_at TIMESTAMP,
            failure_rate FLOAT DEFAULT 0.0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata JSONB
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_llm_retry_model_name ON llm_retry_state(model_name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_llm_retry_circuit_state ON llm_retry_state(circuit_state)")

    # Create LLM processing errors table
    op.execute("""
        CREATE TABLE IF NOT EXISTS llm_processing_errors (
            id SERIAL PRIMARY KEY,
            article_uri TEXT REFERENCES articles(uri) ON DELETE CASCADE,
            error_type VARCHAR(255) NOT NULL,
            error_message TEXT NOT NULL,
            severity VARCHAR(50) NOT NULL,
            model_name VARCHAR(255) NOT NULL,
            retry_count INTEGER DEFAULT 0,
            will_retry BOOLEAN DEFAULT FALSE,
            context JSONB,
            timestamp TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_llm_errors_article_uri ON llm_processing_errors(article_uri)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_llm_errors_model_name ON llm_processing_errors(model_name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_llm_errors_severity ON llm_processing_errors(severity)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_llm_errors_timestamp ON llm_processing_errors(timestamp)")

    # Add LLM status tracking columns to articles table
    op.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_status VARCHAR(50)")
    op.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_status_updated_at TIMESTAMP")
    op.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_error_type VARCHAR(255)")
    op.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_error_message TEXT")
    op.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_processing_metadata JSONB")
    op.execute("CREATE INDEX IF NOT EXISTS idx_articles_llm_status ON articles(llm_status)")

    # Create processing jobs table for job tracking
    op.execute("""
        CREATE TABLE IF NOT EXISTS processing_jobs (
            id SERIAL PRIMARY KEY,
            job_id VARCHAR(255) NOT NULL UNIQUE,
            job_type VARCHAR(50) NOT NULL,
            status VARCHAR(50) NOT NULL,
            total_items INTEGER DEFAULT 0,
            processed_items INTEGER DEFAULT 0,
            failed_items INTEGER DEFAULT 0,
            error_summary JSONB,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            metadata JSONB
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_processing_jobs_job_id ON processing_jobs(job_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_processing_jobs_status ON processing_jobs(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_processing_jobs_job_type ON processing_jobs(job_type)")


def downgrade() -> None:
    # Drop tables and indexes in reverse order
    op.execute("DROP INDEX IF EXISTS idx_processing_jobs_job_type")
    op.execute("DROP INDEX IF EXISTS idx_processing_jobs_status")
    op.execute("DROP INDEX IF EXISTS idx_processing_jobs_job_id")
    op.execute("DROP TABLE IF EXISTS processing_jobs")

    op.execute("DROP INDEX IF EXISTS idx_articles_llm_status")
    op.execute("ALTER TABLE articles DROP COLUMN IF EXISTS llm_processing_metadata")
    op.execute("ALTER TABLE articles DROP COLUMN IF EXISTS llm_error_message")
    op.execute("ALTER TABLE articles DROP COLUMN IF EXISTS llm_error_type")
    op.execute("ALTER TABLE articles DROP COLUMN IF EXISTS llm_status_updated_at")
    op.execute("ALTER TABLE articles DROP COLUMN IF EXISTS llm_status")

    op.execute("DROP INDEX IF EXISTS idx_llm_errors_timestamp")
    op.execute("DROP INDEX IF EXISTS idx_llm_errors_severity")
    op.execute("DROP INDEX IF EXISTS idx_llm_errors_model_name")
    op.execute("DROP INDEX IF EXISTS idx_llm_errors_article_uri")
    op.execute("DROP TABLE IF EXISTS llm_processing_errors")

    op.execute("DROP INDEX IF EXISTS idx_llm_retry_circuit_state")
    op.execute("DROP INDEX IF EXISTS idx_llm_retry_model_name")
    op.execute("DROP TABLE IF EXISTS llm_retry_state")
