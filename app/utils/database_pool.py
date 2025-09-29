"""
Database connection pool for handling concurrent operations efficiently.
Reduces database locks and improves performance for bulk operations.
"""
import asyncio
import sqlite3
import threading
import logging
from typing import Optional, Dict, List
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
import time
import queue

logger = logging.getLogger(__name__)

class DatabasePool:
    """Thread-safe database connection pool for SQLite with optimized settings"""

    def __init__(self, db_path: str, max_connections: int = 10, max_workers: int = 3):
        self.db_path = db_path
        self.max_connections = max_connections
        self.max_workers = max_workers
        self._pool = queue.Queue(maxsize=max_connections)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="db_pool")
        self._lock = threading.Lock()
        self._created_connections = 0

        # Pre-create some connections
        self._initialize_pool()

    def _initialize_pool(self):
        """Initialize the connection pool with optimized connections"""
        initial_connections = min(3, self.max_connections)
        for _ in range(initial_connections):
            conn = self._create_connection()
            if conn:
                self._pool.put(conn)

    def _create_connection(self) -> Optional[sqlite3.Connection]:
        """Create a new optimized SQLite connection"""
        try:
            conn = sqlite3.connect(
                self.db_path,
                timeout=30,  # 30 second timeout
                check_same_thread=False,  # Allow sharing between threads
                isolation_level=None  # Autocommit mode
            )

            # Apply optimizations
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA temp_store = MEMORY")
            conn.execute("PRAGMA mmap_size = 30000000000")  # 30GB
            conn.execute("PRAGMA cache_size = 50000")  # 50MB cache
            conn.execute("PRAGMA busy_timeout = 30000")  # 30 seconds
            conn.execute("PRAGMA wal_autocheckpoint = 1000")

            self._created_connections += 1
            logger.debug(f"Created database connection #{self._created_connections}")
            return conn

        except Exception as e:
            logger.error(f"Failed to create database connection: {e}")
            return None

    def _get_connection(self) -> Optional[sqlite3.Connection]:
        """Get a connection from the pool or create a new one"""
        try:
            # Try to get from pool (non-blocking)
            conn = self._pool.get_nowait()
            # Test if connection is still valid
            try:
                conn.execute("SELECT 1")
                return conn
            except sqlite3.Error:
                # Connection is stale, create a new one
                conn.close()
                return self._create_connection()

        except queue.Empty:
            # Pool is empty, create new connection if under limit
            with self._lock:
                if self._created_connections < self.max_connections:
                    return self._create_connection()

            # Wait for a connection to become available
            try:
                conn = self._pool.get(timeout=5)
                return conn
            except queue.Empty:
                logger.warning("Connection pool exhausted, creating temporary connection")
                return self._create_connection()

    def _return_connection(self, conn: sqlite3.Connection):
        """Return a connection to the pool"""
        try:
            if conn:
                self._pool.put_nowait(conn)
        except queue.Full:
            # Pool is full, close the connection
            conn.close()

    @asynccontextmanager
    async def get_connection(self):
        """Async context manager for getting a database connection"""
        loop = asyncio.get_event_loop()

        # Get connection in thread pool
        conn = await loop.run_in_executor(self._executor, self._get_connection)

        if not conn:
            raise RuntimeError("Failed to get database connection")

        try:
            yield conn
        finally:
            # Return connection to pool in thread pool
            await loop.run_in_executor(self._executor, self._return_connection, conn)

    async def execute_batch(self, operations: List[tuple], batch_size: int = 10):
        """Execute a batch of operations efficiently"""
        results = []

        # Process in batches
        for i in range(0, len(operations), batch_size):
            batch = operations[i:i + batch_size]
            batch_results = await self._execute_batch_chunk(batch)
            results.extend(batch_results)

            # Small delay between batches
            if i + batch_size < len(operations):
                await asyncio.sleep(0.01)

        return results

    async def _execute_batch_chunk(self, operations: List[tuple]):
        """Execute a chunk of operations in a single transaction"""
        async with self.get_connection() as conn:
            def execute_chunk():
                results = []
                try:
                    conn.execute("BEGIN IMMEDIATE")

                    for operation in operations:
                        sql, params = operation[0], operation[1] if len(operation) > 1 else ()
                        try:
                            cursor = conn.execute(sql, params)
                            results.append({"success": True, "lastrowid": cursor.lastrowid})
                        except Exception as e:
                            results.append({"success": False, "error": str(e)})

                    conn.execute("COMMIT")
                    return results

                except Exception as e:
                    try:
                        conn.execute("ROLLBACK")
                    except:
                        pass
                    # Mark all operations as failed
                    return [{"success": False, "error": str(e)} for _ in operations]

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(self._executor, execute_chunk)

    async def execute_query(self, sql: str, params: tuple = ()):
        """Execute a single query"""
        async with self.get_connection() as conn:
            def execute():
                try:
                    cursor = conn.execute(sql, params)
                    if sql.strip().upper().startswith(('SELECT', 'PRAGMA')):
                        return cursor.fetchall()
                    return cursor.lastrowid
                except Exception as e:
                    logger.error(f"Query failed: {sql}, Error: {e}")
                    raise

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(self._executor, execute)

    def close(self):
        """Close all connections in the pool"""
        logger.info("Closing database connection pool")

        # Close all connections in pool
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except (queue.Empty, sqlite3.Error):
                break

        # Shutdown executor
        self._executor.shutdown(wait=True)
        logger.info("Database connection pool closed")

# Global pool instance
_db_pool: Optional[DatabasePool] = None

def get_database_pool(db_path: str) -> DatabasePool:
    """Get or create the global database pool"""
    global _db_pool
    if _db_pool is None:
        _db_pool = DatabasePool(db_path)
    return _db_pool

def close_database_pool():
    """Close the global database pool"""
    global _db_pool
    if _db_pool:
        _db_pool.close()
        _db_pool = None