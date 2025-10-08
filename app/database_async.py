"""
Unified async database module for PostgreSQL/SQLite
Replaces separate database.py and async_db.py
"""
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
    AsyncEngine
)
from sqlalchemy.pool import NullPool, AsyncAdaptedQueuePool
from sqlalchemy.orm import declarative_base
from app.config.settings import db_settings

# SQLAlchemy declarative base
Base = declarative_base()


class AsyncDatabase:
    """Unified async database interface"""

    def __init__(self):
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker] = None

    async def connect(self):
        """Initialize database connection"""
        if self._engine is not None:
            return  # Already connected

        # Engine configuration
        engine_kwargs = {
            "echo": False,
            "pool_pre_ping": True,
        }

        if db_settings.DB_TYPE == "postgresql":
            # PostgreSQL with connection pooling
            engine_kwargs.update({
                "poolclass": AsyncAdaptedQueuePool,
                "pool_size": db_settings.DB_POOL_SIZE,
                "max_overflow": db_settings.DB_MAX_OVERFLOW,
                "pool_timeout": db_settings.DB_POOL_TIMEOUT,
                "pool_recycle": db_settings.DB_POOL_RECYCLE,
            })
        else:
            # SQLite with NullPool (for compatibility)
            engine_kwargs.update({
                "poolclass": NullPool,
                "connect_args": {"check_same_thread": False}
            })

        # Create engine
        self._engine = create_async_engine(
            db_settings.database_url,
            **engine_kwargs
        )

        # Create session factory
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False
        )

        print(f"✓ Connected to {db_settings.DB_TYPE} database")

    async def disconnect(self):
        """Close database connection"""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            print("✓ Database disconnected")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session context manager"""
        if self._session_factory is None:
            await self.connect()

        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def create_all_tables(self):
        """Create all database tables"""
        if self._engine is None:
            await self.connect()

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        print("✓ Database tables created")


# Global database instance
async_db = AsyncDatabase()


# Dependency for FastAPI
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions"""
    async with async_db.session() as session:
        yield session
