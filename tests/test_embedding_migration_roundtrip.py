"""The 1536d → 768d embedding migration, proved against a real database.

emb_768_01 has already been applied on every tenant, so its upgrade() is frozen.
What is testable — and what was actually broken — is the way back: its downgrade
used to add an empty vector(1536) column and present that as a rollback. An empty
column is a valid schema and a total data loss at the same time, which is the
worst combination: nothing fails, and search quietly returns nothing.

These tests run the real migration functions against a disposable schema holding
fixture vectors, and check that:

  * a downgrade with a verified backup restores the original vectors exactly,
  * a downgrade without one refuses to run rather than faking success,
  * the forward repair (emb_768_02) rebuilds the missing HNSW index and is safe
    to run again.

Skips cleanly when there is no reachable PostgreSQL with pgvector.
"""

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("alembic")

from alembic.migration import MigrationContext  # noqa: E402
from alembic.operations import Operations  # noqa: E402
from sqlalchemy import text  # noqa: E402

SCHEMA = "et_migration_sandbox"
VERSIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"


def load_revision(filename):
    """Import a migration module directly, without an alembic env."""
    path = VERSIONS / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _public_index_names(conn):
    """The tenant's real index names on public.articles.

    These tests run DDL under a search_path that still reaches public (pgvector's
    type and operator classes live there), so an unqualified DROP inside a
    migration can escape the sandbox. It happened once: the live
    articles_embedding_hnsw_idx was dropped by a sandboxed downgrade on
    2026-08-19. The fixture now fails loudly if the real schema is touched.
    """
    return {
        row[0] for row in conn.execute(text("""
            SELECT indexname FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = 'articles'
        """)).fetchall()
    }


@pytest.fixture
def db():
    from app.config.settings import db_settings
    from sqlalchemy import create_engine

    try:
        engine = create_engine(db_settings.get_sync_database_url())
        conn = engine.connect()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"No PostgreSQL available: {exc}")

    try:
        has_vector = conn.execute(text(
            "SELECT COUNT(*) FROM pg_extension WHERE extname = 'vector'"
        )).scalar()
        if not has_vector:
            pytest.skip("pgvector is not installed in this database")

        indexes_before = _public_index_names(conn)

        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        conn.execute(text(f"SET search_path TO {SCHEMA}, public"))
        conn.commit()
        conn.execute(text(f"SET search_path TO {SCHEMA}, public"))
        yield conn
    finally:
        try:
            conn.rollback()
            conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
            conn.commit()
            conn.execute(text("SET search_path TO public"))
            lost = indexes_before - _public_index_names(conn)
            assert not lost, (
                f"this test dropped real indexes on public.articles: {sorted(lost)}. "
                "A migration ran unqualified DDL that escaped the sandbox schema."
            )
        finally:
            conn.close()


def vector_literal(seed, dim):
    """A distinct, reproducible vector."""
    return "[" + ",".join(str(round((seed + i) % 97 / 97.0, 6)) for i in range(dim)) + "]"


def seed_post_migration_state(conn, rows=25, backup=True):
    """The state a tenant is in after emb_768_01: 768d live, 1536d in backup."""
    conn.execute(text("""
        CREATE TABLE articles (uri TEXT PRIMARY KEY, embedding vector(768))
    """))
    conn.execute(text("CREATE TABLE emerging_topics (id SERIAL PRIMARY KEY, "
                      "centroid_embedding vector(768))"))
    conn.execute(text("CREATE TABLE cluster_snapshots (id SERIAL PRIMARY KEY, "
                      "centroid_embedding vector(768))"))

    if backup:
        conn.execute(text("""
            CREATE TABLE articles_embedding_1536_backup (
                uri TEXT PRIMARY KEY, embedding vector(1536)
            )
        """))

    originals = {}
    for i in range(rows):
        uri = f"article-{i}"
        conn.execute(text(
            "INSERT INTO articles (uri, embedding) VALUES (:uri, CAST(:e AS vector))"
        ), {"uri": uri, "e": vector_literal(i, 768)})
        if backup:
            original = vector_literal(i * 7 + 1, 1536)
            originals[uri] = original
            conn.execute(text(
                "INSERT INTO articles_embedding_1536_backup (uri, embedding) "
                "VALUES (:uri, CAST(:e AS vector))"
            ), {"uri": uri, "e": original})
    conn.commit()
    return originals


def run_migration(conn, module, direction="upgrade"):
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        getattr(module, direction)()


def column_type(conn, table, column):
    return conn.execute(text("""
        SELECT format_type(a.atttypid, a.atttypmod)
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = :schema AND c.relname = :table AND a.attname = :column
    """), {"schema": SCHEMA, "table": table, "column": column}).scalar()


# ---------------------------------------------------------------------------

def test_downgrade_restores_the_original_vectors_from_the_backup(db):
    originals = seed_post_migration_state(db, rows=25)
    module = load_revision("emb_768_01_embeddings_to_768d.py")

    backed_up = db.execute(text(
        "SELECT COUNT(*) FROM articles_embedding_1536_backup WHERE embedding IS NOT NULL"
    )).scalar()
    assert backed_up == 25

    run_migration(db, module, "downgrade")
    db.commit()

    assert column_type(db, "articles", "embedding") == "vector(1536)"

    restored = db.execute(text(
        "SELECT COUNT(*) FROM articles WHERE embedding IS NOT NULL"
    )).scalar()
    assert restored == backed_up, "every backed-up vector must come back"

    # Numerically identical, not merely the right shape.
    for uri, original in originals.items():
        stored = db.execute(text(
            "SELECT embedding::text FROM articles WHERE uri = :uri"
        ), {"uri": uri}).scalar()
        assert [round(float(v), 6) for v in stored.strip("[]").split(",")] == \
               [round(float(v), 6) for v in original.strip("[]").split(",")]


def test_downgrade_rebuilds_the_cosine_index(db):
    seed_post_migration_state(db, rows=10)
    module = load_revision("emb_768_01_embeddings_to_768d.py")

    run_migration(db, module, "downgrade")
    db.commit()

    definition = db.execute(text("""
        SELECT indexdef FROM pg_indexes
        WHERE schemaname = :schema AND indexname = 'articles_embedding_hnsw_idx'
    """), {"schema": SCHEMA}).scalar()
    assert definition and "vector_cosine_ops" in definition


def test_downgrade_refuses_to_run_without_a_backup(db):
    """No backup means the original vectors are gone. Say so; do not pretend."""
    seed_post_migration_state(db, rows=5, backup=False)
    module = load_revision("emb_768_01_embeddings_to_768d.py")

    with pytest.raises(RuntimeError, match="unrecoverable"):
        run_migration(db, module, "downgrade")
    db.rollback()

    # And the live column is untouched, rather than replaced by an empty one.
    assert column_type(db, "articles", "embedding") == "vector(768)"
    assert db.execute(text(
        "SELECT COUNT(*) FROM articles WHERE embedding IS NOT NULL"
    )).scalar() == 5


def test_downgrade_reports_a_partial_restore_instead_of_accepting_it(db):
    seed_post_migration_state(db, rows=10)
    # An article deleted since the backup was taken: 10 backed up, 9 restorable.
    db.execute(text("DELETE FROM articles WHERE uri = 'article-3'"))
    db.commit()

    module = load_revision("emb_768_01_embeddings_to_768d.py")
    with pytest.raises(RuntimeError, match="restored 9 of 10"):
        run_migration(db, module, "downgrade")
    db.rollback()


# ---------------------------------------------------------------------------
# Forward repair
# ---------------------------------------------------------------------------

def test_forward_repair_builds_the_missing_index_and_is_rerunnable(db):
    seed_post_migration_state(db, rows=20)
    module = load_revision("emb_768_02_embedding_repair.py")

    assert db.execute(text("""
        SELECT COUNT(*) FROM pg_indexes
        WHERE schemaname = :schema AND indexname = 'articles_embedding_hnsw_idx'
    """), {"schema": SCHEMA}).scalar() == 0

    run_migration(db, module, "upgrade")
    db.commit()

    definition = db.execute(text("""
        SELECT indexdef FROM pg_indexes
        WHERE schemaname = :schema AND indexname = 'articles_embedding_hnsw_idx'
    """), {"schema": SCHEMA}).scalar()
    assert definition and "vector_cosine_ops" in definition

    # Running it again finds the index already there and changes nothing.
    run_migration(db, module, "upgrade")
    db.commit()
    count = db.execute(text("""
        SELECT COUNT(*) FROM pg_indexes
        WHERE schemaname = :schema AND indexname = 'articles_embedding_hnsw_idx'
    """), {"schema": SCHEMA}).scalar()
    assert count == 1


def test_forward_repair_rejects_a_wrong_width_column(db):
    db.execute(text("CREATE TABLE articles (uri TEXT PRIMARY KEY, "
                    "embedding vector(1536))"))
    db.commit()
    module = load_revision("emb_768_02_embedding_repair.py")

    with pytest.raises(RuntimeError, match="expected vector\\(768\\)"):
        run_migration(db, module, "upgrade")
    db.rollback()


def test_nearest_neighbour_query_uses_the_index(db):
    """EXPLAIN, with a sequential scan discouraged so the plan reflects the index."""
    seed_post_migration_state(db, rows=50)
    run_migration(db, load_revision("emb_768_02_embedding_repair.py"), "upgrade")
    db.commit()

    db.execute(text("SET LOCAL enable_seqscan = off"))
    plan = "\n".join(row[0] for row in db.execute(text("""
        EXPLAIN
        SELECT uri FROM articles
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:probe AS vector)
        LIMIT 5
    """), {"probe": vector_literal(3, 768)}).fetchall())

    assert "articles_embedding_hnsw_idx" in plan, plan
