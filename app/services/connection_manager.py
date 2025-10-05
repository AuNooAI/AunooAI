"""
Centralized connection manager for LiteLLM and httpx clients.

This service:
1. Tracks active connections and file descriptors
2. Automatically closes idle connections
3. Forces cleanup when approaching FD limits
4. Provides monitoring metrics
"""

import logging
import asyncio
import psutil
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages HTTP connections and file descriptors for the application"""

    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.last_cleanup = datetime.now()
        self.cleanup_interval = 300  # 5 minutes
        self.fd_warning_threshold = 0.7  # 70%
        self.fd_critical_threshold = 0.9  # 90%
        self._cleanup_task = None

    def get_fd_stats(self) -> Dict:
        """Get current file descriptor usage statistics"""
        try:
            # Get open file descriptors
            open_files = self.process.open_files()
            connections = self.process.connections()

            # Get FD limits
            import resource
            soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)

            # Count connections by state
            conn_states = {}
            for conn in connections:
                state = conn.status
                conn_states[state] = conn_states.get(state, 0) + 1

            # Total FDs (files + connections + sockets)
            try:
                num_fds = self.process.num_fds()
            except AttributeError:
                # Fallback for non-Linux systems
                num_fds = len(open_files) + len(connections)

            usage_percent = (num_fds / soft_limit) * 100 if soft_limit > 0 else 0

            return {
                "num_fds": num_fds,
                "soft_limit": soft_limit,
                "hard_limit": hard_limit,
                "usage_percent": usage_percent,
                "open_files_count": len(open_files),
                "connections_count": len(connections),
                "connection_states": conn_states,
                "status": self._get_fd_status(usage_percent),
                "last_cleanup": self.last_cleanup.isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting FD stats: {e}")
            return {
                "error": str(e),
                "status": "unknown"
            }

    def _get_fd_status(self, usage_percent: float) -> str:
        """Determine FD status based on usage percentage"""
        if usage_percent >= self.fd_critical_threshold * 100:
            return "critical"
        elif usage_percent >= self.fd_warning_threshold * 100:
            return "warning"
        else:
            return "healthy"

    async def cleanup_connections(self, force: bool = False) -> Dict:
        """
        Clean up idle connections and close file descriptors.

        Args:
            force: If True, aggressively clean up all possible connections

        Returns:
            Dictionary with cleanup statistics
        """
        stats_before = self.get_fd_stats()
        closed_count = 0

        try:
            # Force Python's garbage collection
            import gc
            gc.collect()

            # Close any httpx clients that might be lingering
            # This is a safety measure - proper code should close clients explicitly
            if force:
                # Get all httpx.AsyncClient instances from gc
                for obj in gc.get_objects():
                    try:
                        if isinstance(obj, httpx.AsyncClient):
                            if not obj.is_closed:
                                await obj.aclose()
                                closed_count += 1
                    except Exception as e:
                        logger.debug(f"Error closing httpx client: {e}")

            # Force LiteLLM to clean up its connection pools
            try:
                import litellm
                # Clear any cached clients
                if hasattr(litellm, 'client_session'):
                    litellm.client_session = None
                if hasattr(litellm, '_client_session'):
                    litellm._client_session = None
            except Exception as e:
                logger.debug(f"Error cleaning LiteLLM clients: {e}")

            # Final garbage collection
            gc.collect()

            self.last_cleanup = datetime.now()
            stats_after = self.get_fd_stats()

            fds_freed = stats_before.get('num_fds', 0) - stats_after.get('num_fds', 0)

            logger.info(f"Connection cleanup completed: {fds_freed} FDs freed, {closed_count} clients closed")

            return {
                "success": True,
                "fds_before": stats_before.get('num_fds', 0),
                "fds_after": stats_after.get('num_fds', 0),
                "fds_freed": fds_freed,
                "clients_closed": closed_count,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error during connection cleanup: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    async def check_and_cleanup_if_needed(self):
        """Check FD usage and cleanup if approaching limits"""
        stats = self.get_fd_stats()
        status = stats.get('status', 'unknown')

        if status == 'critical':
            logger.error(f"CRITICAL: File descriptor usage at {stats['usage_percent']:.1f}% - forcing cleanup")
            await self.cleanup_connections(force=True)
        elif status == 'warning':
            logger.warning(f"WARNING: File descriptor usage at {stats['usage_percent']:.1f}% - performing cleanup")
            await self.cleanup_connections(force=False)
        elif (datetime.now() - self.last_cleanup).total_seconds() > self.cleanup_interval:
            logger.info("Performing scheduled connection cleanup")
            await self.cleanup_connections(force=False)

    async def start_monitoring(self):
        """Start background monitoring task"""
        if self._cleanup_task is not None:
            return

        async def monitor_loop():
            while True:
                try:
                    await self.check_and_cleanup_if_needed()
                    await asyncio.sleep(60)  # Check every minute
                except Exception as e:
                    logger.error(f"Error in connection monitor loop: {e}")
                    await asyncio.sleep(60)

        self._cleanup_task = asyncio.create_task(monitor_loop())
        logger.info("Connection monitoring started")

    async def stop_monitoring(self):
        """Stop background monitoring task"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Connection monitoring stopped")


# Global instance
_connection_manager = None


def get_connection_manager() -> ConnectionManager:
    """Get or create the global connection manager instance"""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
    return _connection_manager
