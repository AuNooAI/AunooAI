#!/usr/bin/env python3
"""
Benchmark script for pgvector performance testing.

Tests:
1. Vector search with index
2. Similar articles query
3. Concurrent async operations
4. Connection pool performance
"""
import asyncio
import time
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.vector_store import search_articles, similar_articles
from app.vector_store import search_articles_async, similar_articles_async
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def benchmark_sync_search(query: str, iterations: int = 10):
    """Benchmark synchronous vector search."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Benchmarking SYNC search_articles ({iterations} iterations)")
    logger.info(f"{'='*60}")

    times = []
    for i in range(iterations):
        start = time.time()
        results = search_articles(query, top_k=10)
        elapsed = time.time() - start
        times.append(elapsed)
        logger.info(f"  Iteration {i+1}: {elapsed:.3f}s ({len(results)} results)")

    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)

    logger.info(f"\nResults:")
    logger.info(f"  Average: {avg_time:.3f}s")
    logger.info(f"  Min: {min_time:.3f}s")
    logger.info(f"  Max: {max_time:.3f}s")

    return avg_time


async def benchmark_async_search(query: str, iterations: int = 10):
    """Benchmark asynchronous vector search."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Benchmarking ASYNC search_articles ({iterations} iterations)")
    logger.info(f"{'='*60}")

    times = []
    for i in range(iterations):
        start = time.time()
        results = await search_articles_async(query, top_k=10)
        elapsed = time.time() - start
        times.append(elapsed)
        logger.info(f"  Iteration {i+1}: {elapsed:.3f}s ({len(results)} results)")

    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)

    logger.info(f"\nResults:")
    logger.info(f"  Average: {avg_time:.3f}s")
    logger.info(f"  Min: {min_time:.3f}s")
    logger.info(f"  Max: {max_time:.3f}s")

    return avg_time


async def benchmark_concurrent_async(query: str, concurrent: int = 5, iterations: int = 3):
    """Benchmark concurrent async operations."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Benchmarking CONCURRENT ASYNC ({concurrent} parallel, {iterations} iterations)")
    logger.info(f"{'='*60}")

    times = []
    for i in range(iterations):
        start = time.time()

        # Run multiple searches concurrently
        tasks = [search_articles_async(query, top_k=10) for _ in range(concurrent)]
        results = await asyncio.gather(*tasks)

        elapsed = time.time() - start
        times.append(elapsed)
        total_results = sum(len(r) for r in results)
        logger.info(f"  Iteration {i+1}: {elapsed:.3f}s ({concurrent} queries, {total_results} total results)")

    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)

    logger.info(f"\nResults:")
    logger.info(f"  Average: {avg_time:.3f}s for {concurrent} concurrent queries")
    logger.info(f"  Min: {min_time:.3f}s")
    logger.info(f"  Max: {max_time:.3f}s")
    logger.info(f"  Throughput: {concurrent/avg_time:.2f} queries/second")

    return avg_time


def benchmark_sync_similar(uri: str, iterations: int = 10):
    """Benchmark synchronous similar articles search."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Benchmarking SYNC similar_articles ({iterations} iterations)")
    logger.info(f"{'='*60}")

    times = []
    for i in range(iterations):
        start = time.time()
        results = similar_articles(uri, top_k=5)
        elapsed = time.time() - start
        times.append(elapsed)
        logger.info(f"  Iteration {i+1}: {elapsed:.3f}s ({len(results)} results)")

    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)

    logger.info(f"\nResults:")
    logger.info(f"  Average: {avg_time:.3f}s")
    logger.info(f"  Min: {min_time:.3f}s")
    logger.info(f"  Max: {max_time:.3f}s")

    return avg_time


async def benchmark_async_similar(uri: str, iterations: int = 10):
    """Benchmark asynchronous similar articles search."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Benchmarking ASYNC similar_articles ({iterations} iterations)")
    logger.info(f"{'='*60}")

    times = []
    for i in range(iterations):
        start = time.time()
        results = await similar_articles_async(uri, top_k=5)
        elapsed = time.time() - start
        times.append(elapsed)
        logger.info(f"  Iteration {i+1}: {elapsed:.3f}s ({len(results)} results)")

    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)

    logger.info(f"\nResults:")
    logger.info(f"  Average: {avg_time:.3f}s")
    logger.info(f"  Min: {min_time:.3f}s")
    logger.info(f"  Max: {max_time:.3f}s")

    return avg_time


async def get_sample_uri():
    """Get a sample URI with embedding for testing."""
    try:
        import asyncpg
        from app.config.settings import db_settings

        conn = await asyncpg.connect(
            host=db_settings.DB_HOST,
            port=int(db_settings.DB_PORT),
            user=db_settings.DB_USER,
            password=db_settings.DB_PASSWORD,
            database=db_settings.DB_NAME
        )

        row = await conn.fetchrow("""
            SELECT uri FROM articles
            WHERE embedding IS NOT NULL
            LIMIT 1
        """)

        await conn.close()

        return row["uri"] if row else None
    except Exception as e:
        logger.error(f"Failed to get sample URI: {e}")
        return None


async def main():
    """Run all benchmarks."""
    logger.info("\n" + "="*60)
    logger.info("PGVECTOR PERFORMANCE BENCHMARK")
    logger.info("="*60)
    logger.info(f"Database: {os.getenv('DB_TYPE', 'sqlite')}")
    logger.info(f"Database: {os.getenv('DB_NAME', 'N/A')}")
    logger.info("="*60)

    # Test query
    test_query = "artificial intelligence machine learning"

    # Get a sample URI for similar articles test
    sample_uri = await get_sample_uri()

    # Run benchmarks
    results = {}

    # 1. Sync search
    results["sync_search"] = benchmark_sync_search(test_query, iterations=5)

    # 2. Async search
    results["async_search"] = await benchmark_async_search(test_query, iterations=5)

    # 3. Concurrent async
    results["concurrent_async"] = await benchmark_concurrent_async(test_query, concurrent=5, iterations=3)

    # 4. Sync similar articles
    if sample_uri:
        results["sync_similar"] = benchmark_sync_similar(sample_uri, iterations=5)
        results["async_similar"] = await benchmark_async_similar(sample_uri, iterations=5)
    else:
        logger.warning("No articles with embeddings found, skipping similar_articles benchmarks")

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("BENCHMARK SUMMARY")
    logger.info(f"{'='*60}")
    for name, avg_time in results.items():
        logger.info(f"  {name:30s}: {avg_time:.3f}s average")

    if "sync_search" in results and "async_search" in results:
        speedup = results["sync_search"] / results["async_search"]
        logger.info(f"\n  Async speedup over sync: {speedup:.2f}x")

    logger.info(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
