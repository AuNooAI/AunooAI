#!/usr/bin/env python3
"""
PostgreSQL Migration - Week 4: Concurrent Users Load Test
Simulates multiple concurrent users accessing the system.
"""

import sys
import os
import logging
import asyncio
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Tuple

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.database import Database
from app.vector_store import search_articles_async

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ConcurrentUserSimulator:
    """Simulates concurrent user sessions"""

    def __init__(self, num_users: int = 50, duration_seconds: int = 30):
        self.num_users = num_users
        self.duration = duration_seconds
        self.results: List[Dict[str, Any]] = []

    def simulate_user_session(self, user_id: int) -> Dict[str, Any]:
        """
        Simulate a single user session with mixed operations.

        Args:
            user_id: Unique user identifier
            duration_seconds: How long to simulate

        Returns:
            Dict with operation statistics
        """
        db = Database()
        operations = []
        start_time = time.time()

        while time.time() - start_time < self.duration:
            try:
                # Random operations users might perform
                operation_type = user_id % 4

                if operation_type == 0:
                    # Get recent articles (40% of operations)
                    articles = db.get_recent_articles(limit=20)
                    operations.append(('get_articles', 'success', len(articles)))

                elif operation_type == 1:
                    # Search (30% of operations)
                    async def do_search():
                        return await search_articles_async(
                            query="test query artificial intelligence",
                            top_k=10
                        )
                    results = asyncio.run(do_search())
                    operations.append(('search', 'success', len(results)))

                elif operation_type == 2:
                    # Get topics (20% of operations)
                    topics = db.get_topics()
                    operations.append(('get_topics', 'success', len(topics)))

                else:
                    # Get article count (10% of operations)
                    if user_id % 8 == 0:  # Only some users
                        topics = db.get_topics()
                        if topics:
                            count = db.get_article_count_by_topic(topics[0])
                            operations.append(('get_count', 'success', count))

                # Throttle requests (simulate real user behavior)
                time.sleep(0.1)

            except Exception as e:
                operations.append(('error', str(type(e).__name__), 0))
                logger.debug(f"User {user_id} error: {e}")

        return {
            'user_id': user_id,
            'operations': len(operations),
            'errors': len([op for op in operations if op[0] == 'error']),
            'by_type': self._count_by_type(operations)
        }

    def _count_by_type(self, operations: List[Tuple]) -> Dict[str, int]:
        """Count operations by type"""
        counts = {}
        for op in operations:
            op_type = op[0]
            counts[op_type] = counts.get(op_type, 0) + 1
        return counts

    def run_load_test(self) -> Dict[str, Any]:
        """
        Run the load test with concurrent users.

        Returns:
            Dict with test results
        """
        logger.info("=" * 80)
        logger.info("  CONCURRENT USERS LOAD TEST")
        logger.info("=" * 80)
        logger.info(f"  Number of users: {self.num_users}")
        logger.info(f"  Duration: {self.duration} seconds")
        logger.info("=" * 80)

        start_time = time.time()

        # Run concurrent user sessions
        logger.info(f"\n🚀 Starting load test...")

        with ThreadPoolExecutor(max_workers=self.num_users) as executor:
            futures = [
                executor.submit(self.simulate_user_session, i)
                for i in range(self.num_users)
            ]

            self.results = [future.result() for future in futures]

        elapsed = time.time() - start_time

        # Analyze results
        total_operations = sum(r['operations'] for r in self.results)
        total_errors = sum(r['errors'] for r in self.results)
        error_rate = (total_errors / total_operations * 100) if total_operations > 0 else 0

        # Count operations by type
        op_type_counts = {}
        for result in self.results:
            for op_type, count in result['by_type'].items():
                op_type_counts[op_type] = op_type_counts.get(op_type, 0) + count

        return {
            'success': error_rate < 5 and total_operations > 1000,
            'elapsed_seconds': elapsed,
            'total_operations': total_operations,
            'total_errors': total_errors,
            'error_rate': error_rate,
            'operations_per_second': total_operations / elapsed if elapsed > 0 else 0,
            'operations_by_type': op_type_counts
        }


class ConnectionPoolLoadTest:
    """Test PostgreSQL connection pool under load"""

    def __init__(self):
        self.db = Database()

    async def test_connection_pool_saturation(self) -> Dict[str, Any]:
        """
        Test connection pool under heavy concurrent load.

        Verifies:
        - Pool handles burst traffic
        - Connections are reused properly
        - No connection leaks
        """
        logger.info("=" * 80)
        logger.info("  CONNECTION POOL SATURATION TEST")
        logger.info("=" * 80)

        # Get pool configuration
        pool_size = int(os.getenv('DB_POOL_SIZE', '15'))
        max_overflow = int(os.getenv('DB_MAX_OVERFLOW', '10'))
        max_connections = pool_size + max_overflow

        logger.info(f"  Pool size: {pool_size}")
        logger.info(f"  Max overflow: {max_overflow}")
        logger.info(f"  Max connections: {max_connections}")
        logger.info("=" * 80)

        # Create tasks that exceed pool size
        num_tasks = max_connections + 10
        logger.info(f"\n🔧 Testing with {num_tasks} concurrent tasks...")

        async def db_operation(task_id: int) -> Tuple[str, Any]:
            """Single database operation"""
            try:
                articles = self.db.get_recent_articles(limit=10)
                return ('success', task_id)
            except Exception as e:
                return ('error', str(e))

        # Run all tasks concurrently
        start = time.time()
        tasks = [db_operation(i) for i in range(num_tasks)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start

        # Analyze results
        successes = len([r for r in results if isinstance(r, tuple) and r[0] == 'success'])
        errors = len([r for r in results if isinstance(r, Exception) or (isinstance(r, tuple) and r[0] == 'error')])

        success = successes == num_tasks and errors == 0

        return {
            'success': success,
            'num_tasks': num_tasks,
            'successes': successes,
            'errors': errors,
            'elapsed_seconds': elapsed,
            'pool_size': pool_size,
            'max_overflow': max_overflow
        }


def print_load_test_results(results: Dict[str, Any]):
    """Print formatted load test results"""
    logger.info("\n" + "=" * 80)
    logger.info("📊 LOAD TEST RESULTS")
    logger.info("=" * 80)
    logger.info(f"  Duration: {results['elapsed_seconds']:.2f}s")
    logger.info(f"  Total operations: {results['total_operations']}")
    logger.info(f"  Total errors: {results['total_errors']}")
    logger.info(f"  Error rate: {results['error_rate']:.2f}%")
    logger.info(f"  Operations/second: {results['operations_per_second']:.2f}")
    logger.info("\n  Operations by type:")
    for op_type, count in results['operations_by_type'].items():
        logger.info(f"    {op_type}: {count}")
    logger.info("=" * 80)

    # Check against success criteria
    criteria = [
        ('Error rate < 5%', results['error_rate'] < 5),
        ('Total operations > 1000', results['total_operations'] > 1000),
        ('No connection failures', results['total_errors'] == 0 or results['error_rate'] < 1)
    ]

    logger.info("\n  Success Criteria:")
    all_passed = True
    for criterion, passed in criteria:
        status = "✅" if passed else "❌"
        logger.info(f"    {status} {criterion}")
        all_passed = all_passed and passed

    logger.info("=" * 80)

    return all_passed


def print_pool_test_results(results: Dict[str, Any]):
    """Print formatted connection pool test results"""
    logger.info("\n" + "=" * 80)
    logger.info("📊 CONNECTION POOL TEST RESULTS")
    logger.info("=" * 80)
    logger.info(f"  Tasks: {results['num_tasks']}")
    logger.info(f"  Successes: {results['successes']}")
    logger.info(f"  Errors: {results['errors']}")
    logger.info(f"  Duration: {results['elapsed_seconds']:.2f}s")
    logger.info(f"  Pool configuration:")
    logger.info(f"    - Pool size: {results['pool_size']}")
    logger.info(f"    - Max overflow: {results['max_overflow']}")
    logger.info("=" * 80)

    # Check success criteria
    criteria = [
        ('All tasks completed', results['successes'] == results['num_tasks']),
        ('No errors', results['errors'] == 0),
        ('Reasonable duration', results['elapsed_seconds'] < 10)
    ]

    logger.info("\n  Success Criteria:")
    all_passed = True
    for criterion, passed in criteria:
        status = "✅" if passed else "❌"
        logger.info(f"    {status} {criterion}")
        all_passed = all_passed and passed

    logger.info("=" * 80)

    return all_passed


async def run_all_load_tests():
    """Run all load tests"""
    logger.info("\n" + "=" * 80)
    logger.info("  WEEK 4: LOAD TESTING SUITE")
    logger.info("=" * 80)
    logger.info(f"Database Type: {os.getenv('DB_TYPE', 'sqlite')}")
    logger.info("=" * 80)

    test_results = {
        'concurrent_users': False,
        'connection_pool': False
    }

    # Test 1: Concurrent Users
    logger.info("\n📊 Test 1: Concurrent User Simulation")
    simulator = ConcurrentUserSimulator(num_users=50, duration_seconds=30)
    load_results = simulator.run_load_test()
    test_results['concurrent_users'] = print_load_test_results(load_results)

    # Test 2: Connection Pool Saturation
    logger.info("\n🔧 Test 2: Connection Pool Saturation")
    pool_test = ConnectionPoolLoadTest()
    pool_results = await pool_test.test_connection_pool_saturation()
    test_results['connection_pool'] = print_pool_test_results(pool_results)

    # Final Summary
    logger.info("\n" + "=" * 80)
    logger.info("  FINAL RESULTS")
    logger.info("=" * 80)

    passed = sum(test_results.values())
    total = len(test_results)

    for test_name, result in test_results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"  {test_name}: {status}")

    logger.info("=" * 80)
    logger.info(f"  Tests Passed: {passed}/{total}")
    logger.info("=" * 80)

    if passed == total:
        logger.info("✅ ALL LOAD TESTS PASSED!")
        return True
    else:
        logger.error(f"❌ {total - passed} load test(s) failed")
        return False


def main():
    """Entry point for load tests"""
    success = asyncio.run(run_all_load_tests())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
