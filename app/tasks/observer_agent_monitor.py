"""
Monitor and schedule observer agent (signal instruction) execution.
Follows the same pattern as keyword_monitor.py and emerging_topics_monitor.py.
"""

import logging
import asyncio
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, Optional, Any, List
from sqlalchemy import text

from app.database import Database

logger = logging.getLogger(__name__)

# Global variable to track task status
_background_task_status = {
    "running": False,
    "last_check_time": None,
    "last_error": None,
    "agents_checked": 0,
    "agents_run": 0,
    "is_checking": False
}


def get_task_status() -> Dict:
    """Get the current status of the observer agent monitor background task"""
    return _background_task_status.copy()


def calculate_next_run(
    schedule_type: str,
    schedule_interval: Optional[int],
    schedule_unit: Optional[str],
    schedule_time: Optional[dt_time],
    from_time: Optional[datetime] = None
) -> datetime:
    """
    Calculate the next run time based on schedule configuration.

    Args:
        schedule_type: 'interval' or 'daily'
        schedule_interval: Interval value (for interval type)
        schedule_unit: 'minutes', 'hours', or 'days' (for interval type)
        schedule_time: Time of day to run (for daily type)
        from_time: Base time to calculate from (defaults to now)

    Returns:
        datetime: Next scheduled run time
    """
    now = from_time or datetime.now()

    if schedule_type == 'daily' and schedule_time:
        # For daily schedules, find the next occurrence of schedule_time
        next_run = now.replace(
            hour=schedule_time.hour,
            minute=schedule_time.minute,
            second=0,
            microsecond=0
        )
        if next_run <= now:
            next_run += timedelta(days=1)
        return next_run

    elif schedule_type == 'interval' and schedule_interval and schedule_unit:
        # For interval schedules, add the interval to now
        if schedule_unit == 'minutes':
            delta = timedelta(minutes=schedule_interval)
        elif schedule_unit == 'hours':
            delta = timedelta(hours=schedule_interval)
        elif schedule_unit == 'days':
            delta = timedelta(days=schedule_interval)
        else:
            delta = timedelta(hours=schedule_interval)  # Default to hours
        return now + delta

    # Default: run in 24 hours
    return now + timedelta(hours=24)


class ObserverAgentMonitor:
    """Monitor for scheduled observer agent execution."""

    def __init__(self, db: Database):
        self.db = db
        self.running_agents: set = set()

    def get_due_agents(self) -> List[Dict]:
        """Get all agents that are due to run (next_run_at <= NOW())."""
        try:
            conn = self.db._temp_get_connection()
            result = conn.execute(text("""
                SELECT id, name, instruction, topic, config,
                       schedule_type, schedule_interval, schedule_unit, schedule_time,
                       last_run_at, next_run_at, run_count
                FROM signal_instructions
                WHERE schedule_enabled = true
                  AND is_active = true
                  AND (next_run_at IS NULL OR next_run_at <= NOW())
                ORDER BY next_run_at ASC NULLS FIRST
            """))
            agents = [dict(row._mapping) for row in result]
            conn.close()
            return agents
        except Exception as e:
            logger.error(f"Error getting due agents: {e}")
            return []

    def update_agent_status(
        self,
        agent_id: int,
        status: str,
        error: Optional[str] = None,
        next_run_at: Optional[datetime] = None
    ) -> None:
        """Update an agent's run status and next run time."""
        try:
            conn = self.db._temp_get_connection()

            updates = ["last_run_at = NOW()", "last_run_status = :status"]
            params = {"id": agent_id, "status": status}

            if error:
                updates.append("last_run_error = :error")
                params["error"] = error
            else:
                updates.append("last_run_error = NULL")

            if next_run_at:
                updates.append("next_run_at = :next_run")
                params["next_run"] = next_run_at

            if status == 'success':
                updates.append("run_count = run_count + 1")

            updates.append("updated_at = NOW()")

            conn.execute(text(f"""
                UPDATE signal_instructions
                SET {', '.join(updates)}
                WHERE id = :id
            """), params)
            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Error updating agent status: {e}")

    async def run_agent(self, agent: Dict) -> Dict[str, Any]:
        """
        Execute a single agent using the existing run-signals logic.

        Returns:
            Dict with success status and results
        """
        agent_id = agent['id']
        agent_name = agent['name']

        result = {
            "success": False,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "alerts_created": 0,
            "error": None
        }

        if agent_id in self.running_agents:
            logger.info(f"Agent {agent_name} is already running, skipping")
            return result

        self.running_agents.add(agent_id)
        self.update_agent_status(agent_id, 'running')

        try:
            # Import the signal running logic
            from app.routes.vector_routes import _run_signal_instruction_internal

            # Get config for days_back and other settings
            config = agent.get('config') or {}
            days_back = config.get('days_back', 7)

            # Run the agent
            logger.info(f"Running scheduled agent: {agent_name} (ID: {agent_id})")
            run_result = await _run_signal_instruction_internal(
                instruction_id=agent_id,
                days_back=days_back,
                tag_articles=config.get('tag_articles', True)
            )

            result["success"] = True
            result["alerts_created"] = run_result.get("alerts_created", 0)

            # Calculate next run time
            next_run = calculate_next_run(
                schedule_type=agent.get('schedule_type', 'interval'),
                schedule_interval=agent.get('schedule_interval'),
                schedule_unit=agent.get('schedule_unit'),
                schedule_time=agent.get('schedule_time')
            )

            self.update_agent_status(agent_id, 'success', next_run_at=next_run)
            logger.info(f"Agent {agent_name} completed. {result['alerts_created']} alerts. Next run: {next_run}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error running agent {agent_name}: {error_msg}", exc_info=True)
            result["error"] = error_msg

            # Still calculate next run time even on error
            next_run = calculate_next_run(
                schedule_type=agent.get('schedule_type', 'interval'),
                schedule_interval=agent.get('schedule_interval'),
                schedule_unit=agent.get('schedule_unit'),
                schedule_time=agent.get('schedule_time')
            )
            self.update_agent_status(agent_id, 'error', error=error_msg, next_run_at=next_run)

        finally:
            self.running_agents.discard(agent_id)

        return result


async def run_observer_agent_monitor():
    """Background task to periodically check and run scheduled observer agents."""
    global _background_task_status

    db = Database()
    monitor = ObserverAgentMonitor(db)

    logger.info("Observer agent monitor background task started")
    _background_task_status["running"] = True

    # Check every 60 seconds
    check_interval = 60

    while True:
        try:
            _background_task_status["is_checking"] = True
            _background_task_status["last_check_time"] = datetime.now()

            # Get agents that are due to run
            due_agents = monitor.get_due_agents()
            _background_task_status["agents_checked"] = len(due_agents)

            if due_agents:
                logger.info(f"Found {len(due_agents)} agents due to run")

                # Run each due agent
                for agent in due_agents:
                    try:
                        result = await monitor.run_agent(agent)
                        if result["success"]:
                            _background_task_status["agents_run"] += 1
                    except Exception as e:
                        logger.error(f"Error running agent {agent.get('name')}: {e}")

            _background_task_status["last_error"] = None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Observer agent monitor error: {error_msg}", exc_info=True)
            _background_task_status["last_error"] = error_msg

        finally:
            _background_task_status["is_checking"] = False

        # Wait before next check
        await asyncio.sleep(check_interval)


async def run_agent_now(db: Database, agent_id: int) -> Dict[str, Any]:
    """Run a specific agent immediately (for manual triggering)."""
    monitor = ObserverAgentMonitor(db)

    # Get the agent details
    try:
        conn = db._temp_get_connection()
        result = conn.execute(text("""
            SELECT id, name, instruction, topic, config,
                   schedule_type, schedule_interval, schedule_unit, schedule_time,
                   last_run_at, next_run_at, run_count
            FROM signal_instructions
            WHERE id = :id
        """), {"id": agent_id})
        row = result.mappings().first()
        conn.close()

        if not row:
            return {"success": False, "error": "Agent not found"}

        agent = dict(row)
        return await monitor.run_agent(agent)

    except Exception as e:
        return {"success": False, "error": str(e)}
