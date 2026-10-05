"""
Health Check Routes

Provides detailed health and status information for monitoring and debugging.
"""

import os
import time
import psutil
from datetime import datetime
from typing import Dict, Any
from pathlib import Path
from sqlalchemy.exc import OperationalError

from fastapi import APIRouter, status, Request, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from app.security.session import verify_session, verify_session_api

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.auto_reload = True  # Reload templates on changes

# Track application start time
START_TIME = time.time()


def get_database_health() -> Dict[str, Any]:
    """Check database connectivity and stats."""
    try:
        from app.database import Database
        db_instance = Database()
        conn = db_instance.get_connection()

        # Test query
        cursor = conn.cursor()
        result = cursor.execute("SELECT COUNT(*) as count FROM articles").fetchone()
        article_count = result[0] if result else 0

        # Get database file size (SQLite only)
        db_path = Path("app/data/fnaapp.db")
        db_size_mb = db_path.stat().st_size / (1024 * 1024) if db_path.exists() else 0

        # Check for locked database (different approach for PostgreSQL vs SQLite)
        locked = False
        if db_instance.db_type == 'sqlite':
            try:
                cursor.execute("BEGIN IMMEDIATE")
                cursor.execute("ROLLBACK")
                locked = False
            except OperationalError:
                locked = True
        # PostgreSQL doesn't have the same locking behavior, always report as not locked

        return {
            "status": "healthy",
            "article_count": article_count,
            "size_mb": round(db_size_mb, 2),
            "locked": locked
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


def get_file_descriptor_stats() -> Dict[str, Any]:
    """Get file descriptor usage statistics."""
    try:
        process = psutil.Process()
        num_fds = process.num_fds()

        # Get limits
        import resource
        soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)

        usage_percent = (num_fds / soft_limit * 100) if soft_limit else 0

        # Get breakdown
        try:
            connections = len(process.connections())
            files = len(process.open_files())
        except:
            connections = 0
            files = 0

        return {
            "open": num_fds,
            "soft_limit": soft_limit,
            "hard_limit": hard_limit,
            "usage_percent": round(usage_percent, 2),
            "available": soft_limit - num_fds,
            "connections": connections,
            "files": files,
            "status": "critical" if usage_percent >= 90 else "warning" if usage_percent >= 75 else "ok"
        }
    except Exception as e:
        return {"error": str(e)}


def get_memory_stats() -> Dict[str, Any]:
    """Get detailed memory statistics."""
    try:
        process = psutil.Process()
        mem_info = process.memory_info()
        mem_percent = process.memory_percent()

        # System memory
        vm = psutil.virtual_memory()

        return {
            "process": {
                "rss_mb": round(mem_info.rss / (1024 * 1024), 2),
                "vms_mb": round(mem_info.vms / (1024 * 1024), 2),
                "percent": round(mem_percent, 2),
                "num_threads": process.num_threads()
            },
            "system": {
                "total_gb": round(vm.total / (1024**3), 2),
                "available_gb": round(vm.available / (1024**3), 2),
                "used_gb": round(vm.used / (1024**3), 2),
                "percent": vm.percent
            }
        }
    except Exception as e:
        return {"error": str(e)}


def get_disk_stats() -> Dict[str, Any]:
    """Get disk usage statistics."""
    try:
        disk = psutil.disk_usage('/')

        # Get database partition if different
        db_path = Path("app/data/fnaapp.db")
        if db_path.exists():
            db_disk = psutil.disk_usage(str(db_path.parent))
            db_partition = {
                "total_gb": round(db_disk.total / (1024**3), 2),
                "used_gb": round(db_disk.used / (1024**3), 2),
                "free_gb": round(db_disk.free / (1024**3), 2),
                "percent": db_disk.percent
            }
        else:
            db_partition = None

        return {
            "root": {
                "total_gb": round(disk.total / (1024**3), 2),
                "used_gb": round(disk.used / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "percent": disk.percent
            },
            "database_partition": db_partition
        }
    except Exception as e:
        return {"error": str(e)}


def get_chromadb_stats() -> Dict[str, Any]:
    """Get ChromaDB statistics."""
    try:
        from app.vector_store import get_chroma_client

        client = get_chroma_client()
        collection = client.get_or_create_collection("articles")

        count = collection.count()

        # Get ChromaDB directory size
        # ChromaDB is stored at project root in 'chromadb' directory
        chroma_path = Path(os.getenv("CHROMA_DB_DIR", "chromadb"))

        # Make it absolute if relative
        if not chroma_path.is_absolute():
            # Get the project root (parent of app directory)
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent.parent  # health_routes.py -> routes -> app -> project_root
            chroma_path = project_root / chroma_path

        if chroma_path.exists():
            total_size = sum(f.stat().st_size for f in chroma_path.rglob('*') if f.is_file())
            size_mb = total_size / (1024 * 1024)
        else:
            size_mb = 0

        return {
            "status": "healthy",
            "vector_count": count,
            "size_mb": round(size_mb, 2)
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def get_environment_info() -> Dict[str, Any]:
    """Get environment and configuration info."""
    try:
        return {
            "environment": os.getenv("ENVIRONMENT", "production"),
            "python_version": f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}",
            "instance": os.getenv("INSTANCE_NAME", "wip"),
            "port": int(os.getenv("PORT", 10001))
        }
    except Exception as e:
        return {"error": str(e)}


def get_api_health() -> Dict[str, Any]:
    """Check API accessibility and configuration for the 3 required service categories."""
    try:
        api_status = {
            "status": "healthy",
            "apis": {}
        }

        # Check for at least one news collector (NewsAPI OR TheNewsAPI OR NewsData.io)
        newsapi_key = os.getenv("PROVIDER_NEWSAPI_API_KEY") or os.getenv("PROVIDER_NEWSAPI_KEY")
        thenewsapi_key = os.getenv("PROVIDER_THENEWSAPI_API_KEY") or os.getenv("PROVIDER_THENEWSAPI_KEY")
        newsdata_key = os.getenv("PROVIDER_NEWSDATA_API_KEY") or os.getenv("NEWSDATA_API_KEY")

        collector_configured = bool(newsapi_key or thenewsapi_key or newsdata_key)
        api_status["apis"]["collector"] = "configured" if collector_configured else "missing"

        # Check for at least one AI provider (OpenAI OR Anthropic OR Google/Gemini)
        openai_key = os.getenv("OPENAI_API_KEY")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        gemini_key = os.getenv("GEMINI_API_KEY")

        ai_configured = bool(openai_key or anthropic_key or gemini_key)
        api_status["apis"]["ai_provider"] = "configured" if ai_configured else "missing"

        # Check Firecrawl (required web scraper)
        firecrawl_key = (os.getenv("PROVIDER_FIRECRAWL_API_KEY") or
                        os.getenv("PROVIDER_FIRECRAWL_KEY") or
                        os.getenv("FIRECRAWL_API_KEY"))
        api_status["apis"]["firecrawl"] = "configured" if firecrawl_key else "missing"

        # Count configured service categories (should be exactly 3)
        configured = sum(1 for v in api_status["apis"].values() if v == "configured")
        api_status["configured_count"] = configured
        api_status["total_checked"] = 3  # Fixed: always checking exactly 3 categories

        # Set overall status
        if configured == 0:
            api_status["status"] = "critical"
        elif configured < 3:
            api_status["status"] = "degraded"

        return api_status
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def get_autopolling_status() -> Dict[str, Any]:
    """Check autopolling/keyword monitor status."""
    try:
        from app.database import Database
        from sqlalchemy import text

        db_instance = Database()
        db_type = os.getenv('DB_TYPE', 'sqlite').lower()

        # Get raw connection for database-agnostic queries
        conn = db_instance._temp_get_connection()

        # Check if tables exist - database-agnostic approach
        if db_type == 'postgresql':
            result = conn.execute(text("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename IN ('keyword_monitor_settings', 'keyword_monitor_status')
                ORDER BY tablename
            """))
            tables = [row[0] for row in result]
        else:  # sqlite
            result = conn.execute(text("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name IN ('keyword_monitor_settings', 'keyword_monitor_status')
                ORDER BY name
            """))
            tables = [row[0] for row in result]

        if not tables:
            return {
                "status": "unknown",
                "message": "Keyword monitor not configured"
            }

        # Get settings from keyword_monitor_settings
        result = conn.execute(text("""
            SELECT is_enabled, daily_request_limit
            FROM keyword_monitor_settings
            LIMIT 1
        """))

        settings_row = result.fetchone()
        if not settings_row:
            return {
                "status": "unknown",
                "message": "No settings found"
            }

        is_enabled, daily_request_limit = settings_row

        # Get status from keyword_monitor_status
        result = conn.execute(text("""
            SELECT requests_today, last_check_time, last_error
            FROM keyword_monitor_status
            LIMIT 1
        """))

        status_row = result.fetchone()
        requests_today = 0
        last_check_time = None
        last_error = None

        if status_row:
            requests_today, last_check_time, last_error = status_row

        # CRITICAL: Commit to close transaction
        conn.commit()

        return {
            "status": "enabled" if is_enabled else "disabled",
            "is_enabled": bool(is_enabled),
            "requests_today": requests_today or 0,
            "daily_request_limit": daily_request_limit or 100,
            "last_poll_time": last_check_time,
            "last_error": last_error,
            "usage_percent": round((requests_today or 0) / (daily_request_limit or 100) * 100, 2)
        }

    except Exception as e:
        # Rollback on error
        try:
            conn.rollback()
        except:
            pass
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/health", tags=["Health"])
async def health_check():
    """
    Simple health check endpoint.

    Returns basic status for uptime monitoring and load balancers.
    """
    uptime = time.time() - START_TIME

    return {
        "status": "healthy",
        "uptime_seconds": round(uptime, 2),
        "timestamp": datetime.now().isoformat()
    }


@router.get("/api/health")
async def api_health():
    """
    API health endpoint for React frontend.

    Returns detailed health metrics in a format suitable for the Operations HQ dashboard.
    """
    uptime = time.time() - START_TIME

    try:
        process = psutil.Process()

        health_data = {
            "status": "healthy",
            "uptime": {
                "days": int(uptime / 86400),
                "hours": int(uptime / 3600),
                "minutes": int(uptime / 60)
            },
            "warnings": [],
            "cpu": {
                "process_percent": round(process.cpu_percent(interval=0.1), 2),
                "system_percent": round(psutil.cpu_percent(interval=0.1), 2),
                "core_count": psutil.cpu_count(),
                "load_average": list(os.getloadavg()) if hasattr(os, 'getloadavg') else None
            },
            "memory": get_memory_stats(),
            "disk": get_disk_stats(),
            "file_descriptors": get_file_descriptor_stats()
        }

        # Check for warnings
        warnings = []
        if health_data["memory"]["system"]["percent"] >= 90:
            warnings.append("Memory usage is critically high (>90%)")
        elif health_data["memory"]["system"]["percent"] >= 75:
            warnings.append("Memory usage is elevated (>75%)")

        if health_data["disk"]["root"]["percent"] >= 90:
            warnings.append("Disk space is critically low (<10% free)")
        elif health_data["disk"]["root"]["percent"] >= 75:
            warnings.append("Disk space is running low (<25% free)")

        if health_data["file_descriptors"]["usage_percent"] >= 90:
            warnings.append("File descriptor usage is critically high (>90%)")

        health_data["warnings"] = warnings

        # Set status based on warnings
        if any("critically" in w.lower() for w in warnings):
            health_data["status"] = "critical"
        elif warnings:
            health_data["status"] = "degraded"

        return health_data

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "uptime": {
                "days": 0,
                "hours": 0,
                "minutes": 0
            },
            "warnings": [f"Error collecting health metrics: {str(e)}"]
        }


@router.get("/health/detailed", tags=["Health"], dependencies=[Depends(verify_session_api)])
async def detailed_health():
    """
    Detailed health check with system metrics.

    Provides comprehensive information about:
    - System resources (CPU, memory, disk)
    - Database health
    - File descriptor usage
    - Process information
    - API accessibility
    - Autopolling status
    """
    uptime = time.time() - START_TIME

    try:
        process = psutil.Process()

        health_data = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "uptime": {
                "seconds": round(uptime, 2),
                "minutes": round(uptime / 60, 2),
                "hours": round(uptime / 3600, 2),
                "days": round(uptime / 86400, 2)
            },
            "cpu": {
                "process_percent": round(process.cpu_percent(interval=0.1), 2),
                "system_percent": psutil.cpu_percent(interval=0.1),
                "core_count": psutil.cpu_count(),
                "load_average": os.getloadavg() if hasattr(os, 'getloadavg') else None
            },
            "memory": get_memory_stats(),
            "disk": get_disk_stats(),
            "file_descriptors": get_file_descriptor_stats(),
            "database": get_database_health(),
            "vector_store": get_chromadb_stats(),
            "environment": get_environment_info(),
            "api_health": get_api_health(),
            "autopolling": get_autopolling_status()
        }

        # Determine overall health status
        fd_stats = health_data["file_descriptors"]
        db_stats = health_data["database"]
        api_stats = health_data["api_health"]
        polling_stats = health_data["autopolling"]

        warnings = []
        if fd_stats.get("status") == "critical":
            warnings.append("Critical: File descriptor usage above 90%")
            health_data["status"] = "degraded"
        elif fd_stats.get("status") == "warning":
            warnings.append("Warning: File descriptor usage above 75%")

        if db_stats.get("status") == "unhealthy":
            warnings.append(f"Database unhealthy: {db_stats.get('error')}")
            health_data["status"] = "degraded"

        if api_stats.get("status") == "critical":
            warnings.append("Critical: No API keys configured")
            health_data["status"] = "degraded"
        elif api_stats.get("status") == "degraded":
            warnings.append(f"Warning: Only {api_stats.get('configured_count')}/{api_stats.get('total_checked')} APIs configured")

        if polling_stats.get("status") == "error":
            warnings.append(f"Autopolling error: {polling_stats.get('error')}")

        if warnings:
            health_data["warnings"] = warnings

        return health_data

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )


@router.get("/health/database", tags=["Health"], dependencies=[Depends(verify_session_api)])
async def database_health():
    """
    Database-specific health check.

    Returns information about:
    - Database connectivity
    - Record counts
    - Database size
    - Lock status
    """
    return get_database_health()


@router.get("/health/resources", tags=["Health"], dependencies=[Depends(verify_session_api)])
async def resource_health():
    """
    System resource health check.

    Focuses on resource usage that could impact performance:
    - File descriptor usage
    - Memory usage
    - Disk space
    """
    fd_stats = get_file_descriptor_stats()
    mem_stats = get_memory_stats()
    disk_stats = get_disk_stats()

    # Determine status
    status_level = "healthy"
    issues = []

    if fd_stats.get("status") == "critical":
        status_level = "critical"
        issues.append(f"File descriptors at {fd_stats.get('usage_percent')}%")
    elif fd_stats.get("status") == "warning":
        status_level = "warning"
        issues.append(f"File descriptors at {fd_stats.get('usage_percent')}%")

    if mem_stats.get("system", {}).get("percent", 0) > 90:
        status_level = "critical" if status_level != "critical" else status_level
        issues.append(f"System memory at {mem_stats['system']['percent']}%")

    if disk_stats.get("root", {}).get("percent", 0) > 90:
        status_level = "critical" if status_level != "critical" else status_level
        issues.append(f"Disk usage at {disk_stats['root']['percent']}%")

    return {
        "status": status_level,
        "file_descriptors": fd_stats,
        "memory": mem_stats,
        "disk": disk_stats,
        "issues": issues if issues else None,
        "timestamp": datetime.now().isoformat()
    }


@router.get("/health/ready", tags=["Health"])
async def readiness_check():
    """
    Readiness check for Kubernetes/container orchestration.

    Returns 200 if the application is ready to serve traffic,
    503 if it's not ready.
    """
    try:
        # Check critical dependencies
        db_health = get_database_health()

        if db_health.get("status") != "healthy":
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "ready": False,
                    "reason": "Database not healthy",
                    "timestamp": datetime.now().isoformat()
                }
            )

        return {
            "ready": True,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "ready": False,
                "reason": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )


@router.get("/health/live", tags=["Health"])
async def liveness_check():
    """
    Liveness check for Kubernetes/container orchestration.

    Returns 200 if the application process is alive,
    even if it's not ready to serve traffic.
    """
    return {
        "live": True,
        "uptime_seconds": round(time.time() - START_TIME, 2),
        "timestamp": datetime.now().isoformat()
    }


@router.get("/health/startup", tags=["Health"])
async def startup_check():
    """
    Startup check for Kubernetes/container orchestration.

    Returns 200 once the application has finished starting up.
    """
    uptime = time.time() - START_TIME

    # Consider startup complete after 10 seconds
    startup_complete = uptime > 10

    if not startup_complete:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "started": False,
                "uptime_seconds": round(uptime, 2),
                "timestamp": datetime.now().isoformat()
            }
        )

    return {
        "started": True,
        "uptime_seconds": round(uptime, 2),
        "timestamp": datetime.now().isoformat()
    }


@router.get("/health/dashboard", tags=["Health"], response_class=HTMLResponse)
async def health_dashboard(request: Request, session=Depends(verify_session)):
    """
    Visual health dashboard with auto-refresh.

    Displays comprehensive system health metrics in a user-friendly web interface.
    Requires authentication.
    """
    try:
        # Get detailed health data
        uptime = time.time() - START_TIME
        process = psutil.Process()

        health_data = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "uptime": {
                "seconds": round(uptime, 2),
                "minutes": round(uptime / 60, 2),
                "hours": round(uptime / 3600, 2),
                "days": round(uptime / 86400, 2)
            },
            "cpu": {
                "process_percent": round(process.cpu_percent(interval=0.1), 2),
                "system_percent": psutil.cpu_percent(interval=0.1),
                "core_count": psutil.cpu_count(),
                "load_average": os.getloadavg() if hasattr(os, 'getloadavg') else None
            },
            "memory": get_memory_stats(),
            "disk": get_disk_stats(),
            "file_descriptors": get_file_descriptor_stats(),
            "database": get_database_health(),
            "vector_store": get_chromadb_stats(),
            "environment": get_environment_info(),
            "api_health": get_api_health(),
            "autopolling": get_autopolling_status()
        }

        # Determine overall health status
        fd_stats = health_data["file_descriptors"]
        db_stats = health_data["database"]
        api_stats = health_data["api_health"]
        polling_stats = health_data["autopolling"]

        warnings = []
        if fd_stats.get("status") == "critical":
            warnings.append("Critical: File descriptor usage above 90%")
            health_data["status"] = "degraded"
        elif fd_stats.get("status") == "warning":
            warnings.append("Warning: File descriptor usage above 75%")

        if db_stats.get("status") == "unhealthy":
            warnings.append(f"Database unhealthy: {db_stats.get('error')}")
            health_data["status"] = "degraded"

        if api_stats.get("status") == "critical":
            warnings.append("Critical: No API keys configured")
            health_data["status"] = "degraded"
        elif api_stats.get("status") == "degraded":
            warnings.append(f"Warning: Only {api_stats.get('configured_count')}/{api_stats.get('total_checked')} APIs configured")

        if polling_stats.get("status") == "error":
            warnings.append(f"Autopolling error: {polling_stats.get('error')}")

        if warnings:
            health_data["warnings"] = warnings

        return templates.TemplateResponse("health.html", {
            "request": request,
            "session": session,
            "current_page": "health",
            "health_data": health_data
        })

    except Exception as e:
        # Return error page
        return templates.TemplateResponse("health.html", {
            "request": request,
            "session": session,
            "current_page": "health",
            "health_data": {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        })


# ---------------------------------------------------------------------------
# Collection health (collector data quality spec, package 14)
# ---------------------------------------------------------------------------
#
# One JSON view of whether collection is actually happening: run records per
# provider, shared quota ledger, rejected-candidate ledger, feeds that need
# attention, and articles held back by configuration or enrichment. The
# alerts list is what scripts/collector_health_check.sh mails out.
#
# Unauthenticated like /api/health, so the cron probe can read it. It returns
# ids, provider names and feed names only; no feed URLs, no credentials.

import asyncio
import json
from datetime import timedelta, timezone

# Minutes between expected successful runs. Everything not listed here is a
# keyword provider polled a few times a day.
DEFAULT_EXPECTED_INTERVALS_MIN: Dict[str, int] = {"rss": 60}
DEFAULT_KEYWORD_INTERVAL_MIN = 12 * 60
FEED_FAILING_ALERT_HOURS = 24


def expected_intervals() -> Dict[str, int]:
    """Per-provider expected interval in minutes. COLLECTION_EXPECTED_INTERVALS
    may hold a JSON object such as {"rss": 30, "newsapi": 360} to override."""
    out = dict(DEFAULT_EXPECTED_INTERVALS_MIN)
    raw = os.getenv("COLLECTION_EXPECTED_INTERVALS", "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for key, val in parsed.items():
                    out[str(key)] = int(val)
        except (ValueError, TypeError):
            pass
    return out


def _interval_for(provider: str, intervals: Dict[str, int]) -> timedelta:
    minutes = intervals.get(provider or "", DEFAULT_KEYWORD_INTERVAL_MIN)
    return timedelta(minutes=max(1, int(minutes)))


def _parse_ts(value) -> "datetime | None":
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _hours(delta: timedelta) -> int:
    return int(delta.total_seconds() // 3600)


def build_collection_alerts(
    runs: Dict[str, Any],
    feeds: list,
    configuration_blocked: list,
    *,
    now: "datetime | None" = None,
    intervals: "Dict[str, int] | None" = None,
) -> list:
    """Alert strings from the summaries. A provider whose runs succeed with
    zero items is healthy and does not alert; only the absence of a success
    for two expected intervals does."""
    now = now or datetime.now(timezone.utc)
    intervals = intervals if intervals is not None else expected_intervals()
    alerts: list = []

    for p in runs.get("providers", []) or []:
        provider = p.get("provider") or "?"
        limit = 2 * _interval_for(provider, intervals)
        last_success = _parse_ts(p.get("last_success_at"))
        last_run = _parse_ts(p.get("last_run_at"))
        if last_success is not None:
            age = now - last_success
            if age > limit:
                alerts.append(f"no successful run for {provider} in {_hours(age)}h")
        elif last_run is not None and now - last_run > limit:
            alerts.append(
                f"no successful run for {provider} in {_hours(now - last_run)}h (never succeeded)"
            )

    for pi in runs.get("pending_intervals", []) or []:
        provider = pi.get("provider") or "?"
        updated = _parse_ts(pi.get("updated_at"))
        if updated is None:
            continue
        age = now - updated
        if age > 2 * _interval_for(provider, intervals):
            alerts.append(
                f"pending continuation for {provider} {pi.get('scope_key') or ''} "
                f"older than 2 intervals ({_hours(age)}h)".replace("  ", " ")
            )

    for f in feeds or []:
        if (f.get("polling_status") or "ok") == "ok":
            continue
        since = _parse_ts(f.get("first_failed_at"))
        if since is not None and now - since > timedelta(hours=FEED_FAILING_ALERT_HOURS):
            alerts.append(f"feed {f.get('id')} failing for >{FEED_FAILING_ALERT_HOURS}h")

    for row in configuration_blocked or []:
        n = int(row.get("count") or 0)
        if n > 0:
            alerts.append(f"{n} configuration-blocked articles in topic {row.get('topic')}")

    return alerts


def _collection_db():
    """The tenant Database; a seam so tests can hand in a stub."""
    from app.database import Database
    return Database()


def _rows(db, sql: str, params: "Dict[str, Any] | None" = None) -> list:
    from sqlalchemy import text
    conn = db._temp_get_connection()
    try:
        return list(conn.execute(text(sql), params or {}).fetchall())
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def _iso(value) -> "str | None":
    return value.isoformat() if isinstance(value, datetime) else (str(value) if value else None)


def _feed_health_rows(db) -> list:
    """Feeds that are not polling cleanly. Names only, never URLs."""
    rows = _rows(db, """
        SELECT id, name, polling_status, consecutive_error_count, first_failed_at,
               last_failed_at, last_error, parse_partial_count, needs_attention_reason,
               last_success_at, last_attempt_at
          FROM rss_feeds
         WHERE polling_status IS DISTINCT FROM 'ok'
            OR COALESCE(parse_partial_count, 0) >= 10
            OR (last_success_at IS NULL AND last_attempt_at IS NOT NULL)
         ORDER BY id
         LIMIT 200
    """)
    return [
        {
            "id": r[0], "name": r[1], "polling_status": r[2] or "ok",
            "consecutive_error_count": int(r[3] or 0),
            "first_failed_at": _iso(r[4]), "last_failed_at": _iso(r[5]),
            "last_error": (r[6] or "")[:200] or None,
            "parse_partial_count": int(r[7] or 0),
            "needs_attention_reason": r[8],
            "last_success_at": _iso(r[9]), "last_attempt_at": _iso(r[10]),
        }
        for r in rows
    ]


def _count_by_topic(db, ingest_status: str) -> list:
    rows = _rows(db, """
        SELECT COALESCE(topic, ''), COUNT(*) FROM articles
         WHERE ingest_status = :s GROUP BY topic ORDER BY 2 DESC LIMIT 100
    """, {"s": ingest_status})
    return [{"topic": r[0], "count": int(r[1])} for r in rows]


def _runs_summary(db) -> Dict[str, Any]:
    from app.services.collection_runs import health_summary
    return health_summary(db, since_hours=24)


def _quota_status() -> Dict[str, Any]:
    from app.services.shared_ledger import get_ledger
    out = dict(get_ledger().status())
    out.pop("ledger_path", None)  # a filesystem path has no place in an open endpoint
    return out


def _rejected_stats(db) -> Dict[str, Any]:
    from app.services.rejected_candidates import RejectedCandidateLedger
    return RejectedCandidateLedger(db).stats()


def _collect_collection_health() -> Dict[str, Any]:
    """Gather every section, each guarded so one broken source still leaves
    the rest readable."""
    out: Dict[str, Any] = {"timestamp": datetime.now(timezone.utc).isoformat(), "errors": {}}
    try:
        db = _collection_db()
    except Exception as exc:  # noqa: BLE001
        out["errors"]["database"] = str(exc)
        db = None

    def section(name, fn):
        try:
            out[name] = fn()
        except Exception as exc:  # noqa: BLE001
            out[name] = None
            out["errors"][name] = str(exc)

    section("runs", lambda: _runs_summary(db) if db else {"providers": [], "errors": [], "pending_intervals": []})
    section("quota", _quota_status)
    section("rejected_candidates", lambda: _rejected_stats(db) if db else {})
    section("feeds", lambda: _feed_health_rows(db) if db else [])
    section("configuration_blocked", lambda: _count_by_topic(db, "quarantined_config") if db else [])
    section("enrichment_failed", lambda: _count_by_topic(db, "enrichment_failed") if db else [])
    out["alerts"] = build_collection_alerts(
        out.get("runs") or {}, out.get("feeds") or [], out.get("configuration_blocked") or [],
    )
    if not out["errors"]:
        out.pop("errors")
    return out


@router.get("/api/health/collection", tags=["Health"])
async def collection_health():
    """Collection health: runs, quota, rejected candidates, feeds, blocked
    articles and the alerts derived from them. The queries are short but
    synchronous, so they run off the event loop."""
    return await asyncio.to_thread(_collect_collection_health)
