#!/usr/bin/env python3
"""Diagnostic tests for current database state before migration."""

import sys
import os
import asyncio
import sqlite3
import threading
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.database import Database, get_database_instance
from app.config.settings import DATABASE_DIR

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseDiagnostics:
    """Comprehensive database diagnostics."""

    def __init__(self):
        self.results = {}
        self.db_path = os.path.join(DATABASE_DIR, 'fnaapp.db')

    def test_1_database_exists(self) -> bool:
        """Test 1: Check if database file exists."""
        logger.info("\n=== TEST 1: Database File Existence ===")
        exists = os.path.exists(self.db_path)
        if exists:
            size = os.path.getsize(self.db_path) / (1024 * 1024)  # MB
            logger.info(f"✓ Database exists at: {self.db_path}")
            logger.info(f"  Size: {size:.2f} MB")
            self.results['database_exists'] = True
            self.results['database_size_mb'] = size
        else:
            logger.error(f"✗ Database not found at: {self.db_path}")
            self.results['database_exists'] = False
        return exists

    def test_2_connection_pool_config(self) -> bool:
        """Test 2: Check connection pool configuration."""
        logger.info("\n=== TEST 2: Connection Pool Configuration ===")
        try:
            db = Database()
            logger.info(f"  MAX_CONNECTIONS: {db.MAX_CONNECTIONS}")
            logger.info(f"  CONNECTION_TIMEOUT: {db.CONNECTION_TIMEOUT}s")
            logger.info(f"  RETRY_ATTEMPTS: {db.RETRY_ATTEMPTS}")

            self.results['pool_max_connections'] = db.MAX_CONNECTIONS
            self.results['pool_timeout'] = db.CONNECTION_TIMEOUT
            self.results['pool_retry_attempts'] = db.RETRY_ATTEMPTS

            logger.info("✓ Connection pool configuration loaded")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to load connection pool config: {e}")
            self.results['pool_config_error'] = str(e)
            return False

    def test_3_check_same_thread_config(self) -> bool:
        """Test 3: Check if check_same_thread=False is configured."""
        logger.info("\n=== TEST 3: check_same_thread Configuration ===")
        try:
            # Read database.py source
            db_source_path = Path(__file__).parent / 'app' / 'database.py'
            with open(db_source_path, 'r') as f:
                content = f.read()

            # Look for check_same_thread configurations
            lines_with_check = []
            for i, line in enumerate(content.split('\n'), 1):
                if 'check_same_thread' in line.lower():
                    lines_with_check.append((i, line.strip()))

            if lines_with_check:
                logger.info(f"  Found {len(lines_with_check)} occurrences of check_same_thread:")
                for line_num, line in lines_with_check:
                    logger.info(f"    Line {line_num}: {line}")
                    # Check if it's set to False
                    if 'False' in line:
                        logger.info(f"    ✓ check_same_thread=False configured")
                    else:
                        logger.warning(f"    ⚠ check_same_thread not set to False")

                self.results['check_same_thread_configured'] = True
                self.results['check_same_thread_locations'] = lines_with_check
            else:
                logger.warning("⚠ No check_same_thread configuration found")
                self.results['check_same_thread_configured'] = False

            return True
        except Exception as e:
            logger.error(f"✗ Failed to check configuration: {e}")
            self.results['check_same_thread_error'] = str(e)
            return False

    def test_4_table_count_and_schema(self) -> bool:
        """Test 4: Count tables and check schema."""
        logger.info("\n=== TEST 4: Table Count and Schema ===")
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Get all tables
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)
            tables = [row[0] for row in cursor.fetchall()]

            logger.info(f"  Total tables: {len(tables)}")

            # Get row counts for each table
            table_stats = {}
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                table_stats[table] = count
                if count > 0:
                    logger.info(f"    {table}: {count:,} rows")

            self.results['total_tables'] = len(tables)
            self.results['table_list'] = tables
            self.results['table_stats'] = table_stats

            conn.close()
            logger.info("✓ Schema analysis complete")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to analyze schema: {e}")
            self.results['schema_error'] = str(e)
            return False

    def test_5_concurrent_reads(self) -> bool:
        """Test 5: Test concurrent read operations."""
        logger.info("\n=== TEST 5: Concurrent Read Operations ===")

        errors = []
        results = []

        def read_operation(thread_id: int):
            """Perform a read operation."""
            try:
                start = time.time()
                db = Database()
                conn = db._temp_get_connection()

                # Try to execute a simple query
                from sqlalchemy import text
                result = conn.execute(text("SELECT COUNT(*) FROM articles"))
                count = result.scalar()

                duration = time.time() - start
                results.append({
                    'thread_id': thread_id,
                    'duration': duration,
                    'count': count,
                    'success': True
                })
                logger.debug(f"  Thread {thread_id}: {count} articles in {duration:.3f}s")
            except Exception as e:
                errors.append({
                    'thread_id': thread_id,
                    'error': str(e),
                    'error_type': type(e).__name__
                })
                logger.error(f"  Thread {thread_id} failed: {e}")

        # Run 10 concurrent reads
        threads = []
        for i in range(10):
            t = threading.Thread(target=read_operation, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        success_count = len(results)
        error_count = len(errors)

        logger.info(f"  Completed: {success_count}/10 reads succeeded")
        if errors:
            logger.warning(f"  Errors: {error_count} reads failed")
            for err in errors:
                logger.warning(f"    Thread {err['thread_id']}: {err['error_type']} - {err['error']}")

        if results:
            avg_duration = sum(r['duration'] for r in results) / len(results)
            logger.info(f"  Average duration: {avg_duration:.3f}s")
            self.results['concurrent_reads_avg_duration'] = avg_duration

        self.results['concurrent_reads_success'] = success_count
        self.results['concurrent_reads_errors'] = error_count
        self.results['concurrent_reads_error_details'] = errors

        return error_count == 0

    def test_6_concurrent_writes(self) -> bool:
        """Test 6: Test concurrent write operations (with rollback)."""
        logger.info("\n=== TEST 6: Concurrent Write Operations (Test Only) ===")

        errors = []
        results = []

        def write_operation(thread_id: int):
            """Perform a write operation and rollback."""
            try:
                start = time.time()
                conn = sqlite3.connect(self.db_path, timeout=10)
                cursor = conn.cursor()

                # Insert test data
                test_uri = f"https://test-diagnostic-{thread_id}-{int(time.time()*1000)}.com"
                cursor.execute("""
                    INSERT INTO articles (uri, title, topic, analyzed)
                    VALUES (?, ?, ?, ?)
                """, (test_uri, f"Test Article {thread_id}", "test_diagnostic", False))

                # Immediately rollback (don't save)
                conn.rollback()
                conn.close()

                duration = time.time() - start
                results.append({
                    'thread_id': thread_id,
                    'duration': duration,
                    'success': True
                })
                logger.debug(f"  Thread {thread_id}: Write test completed in {duration:.3f}s")
            except sqlite3.OperationalError as e:
                if 'locked' in str(e).lower():
                    errors.append({
                        'thread_id': thread_id,
                        'error': 'DATABASE_LOCKED',
                        'error_type': 'OperationalError',
                        'message': str(e)
                    })
                    logger.error(f"  Thread {thread_id}: Database locked!")
                else:
                    errors.append({
                        'thread_id': thread_id,
                        'error': str(e),
                        'error_type': type(e).__name__
                    })
                    logger.error(f"  Thread {thread_id} failed: {e}")
            except Exception as e:
                errors.append({
                    'thread_id': thread_id,
                    'error': str(e),
                    'error_type': type(e).__name__
                })
                logger.error(f"  Thread {thread_id} failed: {e}")

        # Run 5 concurrent writes
        threads = []
        for i in range(5):
            t = threading.Thread(target=write_operation, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        success_count = len(results)
        error_count = len(errors)
        locked_count = sum(1 for e in errors if e.get('error') == 'DATABASE_LOCKED')

        logger.info(f"  Completed: {success_count}/5 writes succeeded")
        if errors:
            logger.warning(f"  Errors: {error_count} writes failed")
            if locked_count > 0:
                logger.warning(f"  🔴 DATABASE LOCKED errors: {locked_count}")

        if results:
            avg_duration = sum(r['duration'] for r in results) / len(results)
            logger.info(f"  Average duration: {avg_duration:.3f}s")
            self.results['concurrent_writes_avg_duration'] = avg_duration

        self.results['concurrent_writes_success'] = success_count
        self.results['concurrent_writes_errors'] = error_count
        self.results['concurrent_writes_locked_errors'] = locked_count
        self.results['concurrent_writes_error_details'] = errors

        # Test passes if no locked errors
        return locked_count == 0

    def test_7_async_sync_mixing_audit(self) -> bool:
        """Test 7: Audit for sync/async mixing issues."""
        logger.info("\n=== TEST 7: Async/Sync Mixing Audit ===")

        try:
            # Search for potential issues in automated_ingest_service.py
            service_path = Path(__file__).parent / 'app' / 'services' / 'automated_ingest_service.py'

            if not service_path.exists():
                logger.warning("⚠ automated_ingest_service.py not found")
                return True

            with open(service_path, 'r') as f:
                lines = f.readlines()

            # Look for sync db calls in async functions
            issues = []
            in_async_function = False
            current_function = None

            for i, line in enumerate(lines, 1):
                stripped = line.strip()

                # Track async functions
                if stripped.startswith('async def '):
                    in_async_function = True
                    current_function = stripped.split('(')[0].replace('async def ', '')
                elif stripped.startswith('def ') and not stripped.startswith('def __'):
                    in_async_function = False
                    current_function = None

                # Look for sync db calls
                if in_async_function and 'self.db.' in line and 'await' not in line:
                    # Exclude comments and certain safe patterns
                    if not stripped.startswith('#'):
                        issues.append({
                            'line': i,
                            'function': current_function,
                            'code': stripped[:100]
                        })

            if issues:
                logger.warning(f"  ⚠ Found {len(issues)} potential sync calls in async functions:")
                for issue in issues[:10]:  # Show first 10
                    logger.warning(f"    Line {issue['line']} in {issue['function']}: {issue['code']}")
                if len(issues) > 10:
                    logger.warning(f"    ... and {len(issues) - 10} more")
            else:
                logger.info("  ✓ No obvious sync/async mixing issues found")

            self.results['sync_async_issues_count'] = len(issues)
            self.results['sync_async_issues'] = issues

            return True
        except Exception as e:
            logger.error(f"✗ Failed to audit async/sync mixing: {e}")
            self.results['sync_async_audit_error'] = str(e)
            return False

    def test_8_lifespan_management_check(self) -> bool:
        """Test 8: Check for lifespan management implementation."""
        logger.info("\n=== TEST 8: Lifespan Management Check ===")

        try:
            # Check app_factory.py
            factory_path = Path(__file__).parent / 'app' / 'core' / 'app_factory.py'
            main_path = Path(__file__).parent / 'app' / 'main.py'

            has_lifespan = False
            has_on_event = False

            # Check factory
            if factory_path.exists():
                with open(factory_path, 'r') as f:
                    factory_content = f.read()
                if '@asynccontextmanager' in factory_content or 'lifespan' in factory_content:
                    logger.info("  ✓ Lifespan pattern found in app_factory.py")
                    has_lifespan = True

            # Check main.py for deprecated @app.on_event
            if main_path.exists():
                with open(main_path, 'r') as f:
                    main_content = f.read()
                if '@app.on_event' in main_content:
                    logger.warning("  ⚠ Deprecated @app.on_event found in main.py")
                    has_on_event = True

            self.results['has_lifespan_pattern'] = has_lifespan
            self.results['has_deprecated_on_event'] = has_on_event

            if has_lifespan and not has_on_event:
                logger.info("  ✓ Using modern lifespan pattern")
            elif not has_lifespan and has_on_event:
                logger.warning("  ⚠ Using deprecated @app.on_event pattern")

            return True
        except Exception as e:
            logger.error(f"✗ Failed to check lifespan management: {e}")
            self.results['lifespan_check_error'] = str(e)
            return False

    def generate_report(self) -> str:
        """Generate diagnostic report."""
        logger.info("\n" + "="*60)
        logger.info("DIAGNOSTIC REPORT SUMMARY")
        logger.info("="*60)

        report_lines = []
        report_lines.append(f"Timestamp: {datetime.now().isoformat()}")
        report_lines.append(f"Database Path: {self.db_path}")
        report_lines.append("")

        # Overall health
        issues = []
        warnings = []

        if not self.results.get('database_exists'):
            issues.append("Database file not found")

        if self.results.get('concurrent_writes_locked_errors', 0) > 0:
            issues.append(f"Database locking issues detected ({self.results['concurrent_writes_locked_errors']} locked errors)")

        if self.results.get('sync_async_issues_count', 0) > 0:
            warnings.append(f"Potential sync/async mixing issues ({self.results['sync_async_issues_count']} locations)")

        if self.results.get('has_deprecated_on_event'):
            warnings.append("Using deprecated @app.on_event pattern")

        # Status
        if issues:
            logger.error("Status: ❌ CRITICAL ISSUES FOUND")
            for issue in issues:
                logger.error(f"  - {issue}")
            report_lines.append("Status: ❌ CRITICAL ISSUES")
        elif warnings:
            logger.warning("Status: ⚠️  WARNINGS FOUND")
            for warning in warnings:
                logger.warning(f"  - {warning}")
            report_lines.append("Status: ⚠️  WARNINGS")
        else:
            logger.info("Status: ✅ HEALTHY")
            report_lines.append("Status: ✅ HEALTHY")

        report_lines.append("")
        report_lines.append("KEY METRICS:")
        report_lines.append(f"  Database Size: {self.results.get('database_size_mb', 0):.2f} MB")
        report_lines.append(f"  Total Tables: {self.results.get('total_tables', 0)}")
        report_lines.append(f"  Concurrent Reads Success: {self.results.get('concurrent_reads_success', 0)}/10")
        report_lines.append(f"  Concurrent Writes Success: {self.results.get('concurrent_writes_success', 0)}/5")
        report_lines.append(f"  Database Locked Errors: {self.results.get('concurrent_writes_locked_errors', 0)}")

        logger.info("\nKEY METRICS:")
        logger.info(f"  Database Size: {self.results.get('database_size_mb', 0):.2f} MB")
        logger.info(f"  Total Tables: {self.results.get('total_tables', 0)}")
        logger.info(f"  Concurrent Reads: {self.results.get('concurrent_reads_success', 0)}/10 success")
        logger.info(f"  Concurrent Writes: {self.results.get('concurrent_writes_success', 0)}/5 success")
        logger.info(f"  Locked Errors: {self.results.get('concurrent_writes_locked_errors', 0)}")

        # Recommendations
        logger.info("\nRECOMMENDATIONS:")
        report_lines.append("\nRECOMMENDATIONS:")

        recommendations = []

        if self.results.get('concurrent_writes_locked_errors', 0) > 0:
            recommendations.append("🔴 URGENT: Proceed with Phase 1 SQLite optimizations immediately")
            recommendations.append("🔴 URGENT: Plan for PostgreSQL migration (Phase 2)")

        if self.results.get('sync_async_issues_count', 0) > 0:
            recommendations.append("⚠️  Address sync/async mixing in Phase 1, Task 3")

        if not self.results.get('check_same_thread_configured'):
            recommendations.append("⚠️  Add check_same_thread=False to all engine creations")

        if self.results.get('has_deprecated_on_event'):
            recommendations.append("⚠️  Migrate from @app.on_event to lifespan pattern in Phase 1, Task 2")

        if not recommendations:
            recommendations.append("✅ Database is healthy, but PostgreSQL migration still recommended for production scalability")

        for rec in recommendations:
            logger.info(f"  {rec}")
            report_lines.append(f"  {rec}")

        logger.info("="*60)

        # Save report
        report_path = Path(__file__).parent / 'diagnostic_report.txt'
        with open(report_path, 'w') as f:
            f.write('\n'.join(report_lines))

        logger.info(f"\n📄 Full report saved to: {report_path}")

        # Save JSON results
        import json
        json_path = Path(__file__).parent / 'diagnostic_results.json'
        with open(json_path, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        logger.info(f"📊 JSON results saved to: {json_path}")

        return str(report_path)

    def run_all_tests(self):
        """Run all diagnostic tests."""
        logger.info("🔍 Starting Database Diagnostics")
        logger.info("="*60)

        tests = [
            self.test_1_database_exists,
            self.test_2_connection_pool_config,
            self.test_3_check_same_thread_config,
            self.test_4_table_count_and_schema,
            self.test_5_concurrent_reads,
            self.test_6_concurrent_writes,
            self.test_7_async_sync_mixing_audit,
            self.test_8_lifespan_management_check,
        ]

        for test in tests:
            try:
                test()
            except Exception as e:
                logger.error(f"Test {test.__name__} crashed: {e}")
                import traceback
                traceback.print_exc()

        return self.generate_report()


def main():
    """Run diagnostics."""
    diagnostics = DatabaseDiagnostics()
    report_path = diagnostics.run_all_tests()

    print(f"\n✅ Diagnostics complete! Report: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
