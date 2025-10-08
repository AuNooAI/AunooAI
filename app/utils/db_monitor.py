"""
Database monitoring and metrics collection
"""
import time
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any
from datetime import datetime

class DatabaseMonitor:
    """Monitor database operations and collect metrics"""

    def __init__(self):
        self._lock_wait_times = []
        self._operation_counts = {
            "reads": 0,
            "writes": 0,
            "errors": 0
        }
        self._slow_queries = []

    @asynccontextmanager
    async def track_operation(self, operation_type: str, query_description: str = ""):
        """Track timing and success of database operations"""
        start_time = time.time()
        error_occurred = False

        try:
            yield
        except Exception as e:
            error_occurred = True
            self._operation_counts["errors"] += 1
            raise
        finally:
            duration = time.time() - start_time

            # Track slow queries (>1s)
            if duration > 1.0:
                self._slow_queries.append({
                    "query": query_description,
                    "duration": duration,
                    "timestamp": datetime.now().isoformat(),
                    "error": error_occurred
                })
                # Keep only last 100 slow queries
                self._slow_queries = self._slow_queries[-100:]

            # Track lock wait times
            if "lock" in str(query_description).lower():
                self._lock_wait_times.append(duration)
                # Keep only last 1000 measurements
                self._lock_wait_times = self._lock_wait_times[-1000:]

            # Update operation counts
            if operation_type == "read":
                self._operation_counts["reads"] += 1
            elif operation_type == "write":
                self._operation_counts["writes"] += 1

    def get_metrics(self) -> Dict[str, Any]:
        """Get current monitoring metrics"""
        return {
            "operation_counts": self._operation_counts.copy(),
            "lock_stats": {
                "avg_wait_time": sum(self._lock_wait_times) / len(self._lock_wait_times) if self._lock_wait_times else 0,
                "max_wait_time": max(self._lock_wait_times) if self._lock_wait_times else 0,
                "samples": len(self._lock_wait_times)
            },
            "slow_queries": {
                "count": len(self._slow_queries),
                "recent": self._slow_queries[-10:]  # Last 10 slow queries
            },
            "timestamp": datetime.now().isoformat()
        }

    def reset_metrics(self):
        """Reset all metrics counters"""
        self._lock_wait_times.clear()
        self._operation_counts = {
            "reads": 0,
            "writes": 0,
            "errors": 0
        }
        self._slow_queries.clear()

# Global monitor instance
db_monitor = DatabaseMonitor()
