"""Analysis module registry for optional, tenant-configurable features."""

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ModuleTask:
    """A background task associated with an analysis module."""
    module: str
    function: str
    delay: int


@dataclass
class AnalysisModule:
    """Definition of a pluggable analysis module."""
    id: str                          # "science_funding"
    name: str                        # "ScienceWatch"
    description: str
    route_module: str                # "app.routes.science_funding_routes"
    route_prefix: str                # "/api/science-funding"
    route_attr: str = "router"
    task_module: str | None = None   # "app.tasks.science_funding_monitor"
    task_function: str | None = None # "run_science_funding_monitor"
    task_delay: int = 45             # startup delay seconds
    extra_tasks: list[ModuleTask] = field(default_factory=list)
    model_path: str | None = None    # "models/science_funding_classifier/final"
    migration_prefix: str | None = None  # informational only — migrations always run
    frontend_tab_id: str | None = None   # "science"
    frontend_tab_label: str | None = None  # "ScienceWatch"
    frontend_tab_icon: str | None = None   # "Microscope"


# ---------------------------------------------------------------------------
# Module registry
# ---------------------------------------------------------------------------

_MODULES: dict[str, AnalysisModule] = {}


def _register(module: AnalysisModule) -> None:
    _MODULES[module.id] = module


# --- Geopolitical Hotspots ---------------------------------------------------
_register(AnalysisModule(
    id="geopolitical_hotspots",
    name="GeoHotSpots",
    description="Geopolitical hotspot monitoring with trend analysis and map visualisation.",
    route_module="app.routes.geopolitical_hotspots_routes",
    route_prefix="/api/geopolitical-hotspots",
    task_module="app.tasks.geopolitical_hotspots_monitor",
    task_function="run_geopolitical_hotspots_monitor",
    task_delay=30,
    extra_tasks=[
        ModuleTask(
            module="app.tasks.geopolitical_hotspots_monitor",
            function="run_hotspot_trend_updates",
            delay=35,
        ),
    ],
    migration_prefix="gh_",
    frontend_tab_id="geopolitical",
    frontend_tab_label="GeoHotSpots",
    frontend_tab_icon="Globe",
))

# --- Policy Tracker -----------------------------------------------------------
_register(AnalysisModule(
    id="policy_tracker",
    name="US Crisis Tracker",
    description="Tracks US policy developments and executive actions.",
    route_module="app.routes.policy_tracker_routes",
    route_prefix="/api/policy-tracker",
    task_module="app.tasks.policy_tracker_monitor",
    task_function="run_policy_tracker_monitor",
    task_delay=40,
    migration_prefix="pt_",
    frontend_tab_id="policy",
    frontend_tab_label="US Crisis Tracker",
    frontend_tab_icon="Scale",
))

# --- ScienceWatch -------------------------------------------------------------
_register(AnalysisModule(
    id="science_funding",
    name="ScienceWatch",
    description="Science funding and research policy analysis with DeBERTa classifier.",
    route_module="app.routes.science_funding_routes",
    route_prefix="/api/science-funding",
    task_module="app.tasks.science_funding_monitor",
    task_function="run_science_funding_monitor",
    task_delay=45,
    model_path="models/science_funding_classifier/final",
    migration_prefix="sf_",
    frontend_tab_id="science",
    frontend_tab_label="ScienceWatch",
    frontend_tab_icon="Microscope",
))

# --- Brand Watcher ------------------------------------------------------------
_register(AnalysisModule(
    id="brand_watcher",
    name="Brand Watcher",
    description="Multi-brand intelligence tracking with sentiment, competitive analysis, and reputation monitoring.",
    route_module="app.routes.brand_watcher_routes",
    route_prefix="/api/brand-watcher",
    task_module="app.tasks.brand_watcher_monitor",
    task_function="run_brand_watcher_monitor",
    task_delay=50,
    model_path="models/brand_watcher_classifier/final",
    migration_prefix="bw_",
    frontend_tab_id="brand_watcher",
    frontend_tab_label="Brand Watcher",
    frontend_tab_icon="Target",
))

# --- Threat Intelligence ----------------------------------------------------
_register(AnalysisModule(
    id="threat_intel",
    name="Threat Intelligence",
    description="Cyber threat monitoring with actor tracking, IOC management, and campaign analysis.",
    route_module="app.routes.threat_intelligence_routes",
    route_prefix="/api/threat-intelligence",
    task_module="app.tasks.threat_intelligence_monitor",
    task_function="run_threat_intelligence_monitor",
    task_delay=55,
    migration_prefix="ti_",
    frontend_tab_id="threat_intel",
    frontend_tab_label="Threat Intelligence",
    frontend_tab_icon="Shield",
))


# ---------------------------------------------------------------------------
# DB helpers — module_config table
# ---------------------------------------------------------------------------

def _get_db_overrides() -> dict[str, bool] | None:
    """Query module_config table. Returns {module_id: enabled} or None if empty/unavailable."""
    try:
        from app.database import get_database_instance
        db = get_database_instance()
        conn = db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT module_id, enabled FROM module_config")
            rows = cursor.fetchall()
            if not rows:
                return None
            return {row[0]: bool(row[1]) for row in rows}
        finally:
            conn.close()
    except Exception as e:
        logger.debug(f"module_config not available (expected on first run): {e}")
        return None


def _get_env_enabled_ids() -> list[str]:
    """Read ENABLED_MODULES env var. Returns list of module IDs."""
    raw = os.environ.get("ENABLED_MODULES", "*").strip()
    if raw == "*" or raw == "":
        return list(_MODULES.keys())
    if raw.lower() == "none":
        return []
    return [mid.strip() for mid in raw.split(",") if mid.strip()]


def _seed_from_env() -> None:
    """Seed module_config with current env-var state (called on first toggle)."""
    env_ids = set(_get_env_enabled_ids())
    from app.database import get_database_instance
    db = get_database_instance()
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        for mid in _MODULES:
            cursor.execute(
                "INSERT INTO module_config (module_id, enabled) VALUES (:module_id, :enabled) "
                "ON CONFLICT (module_id) DO NOTHING",
                {"module_id": mid, "enabled": mid in env_ids},
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_module_enabled(module_id: str, enabled: bool, username: str | None = None) -> None:
    """Toggle a module on/off in the DB. Seeds from env on first call."""
    from app.database import get_database_instance
    db = get_database_instance()
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        # Check if table has any rows — if not, seed first
        cursor.execute("SELECT COUNT(*) FROM module_config")
        count = cursor.fetchone()[0]
        if count == 0:
            conn.close()
            _seed_from_env()
            conn = db.get_connection()
            cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO module_config (module_id, enabled, updated_at, updated_by) "
            "VALUES (:module_id, :enabled, NOW(), :updated_by) "
            "ON CONFLICT (module_id) DO UPDATE SET enabled = EXCLUDED.enabled, "
            "updated_at = EXCLUDED.updated_at, updated_by = EXCLUDED.updated_by",
            {"module_id": module_id, "enabled": enabled, "updated_by": username},
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_enabled_module_ids() -> list[str]:
    """Return list of enabled module IDs.

    Checks DB first (module_config table). If empty or unavailable,
    falls back to ENABLED_MODULES env var.
    """
    overrides = _get_db_overrides()
    if overrides is not None:
        return [mid for mid, enabled in overrides.items() if enabled]
    return _get_env_enabled_ids()


def get_enabled_modules() -> list[AnalysisModule]:
    """Return AnalysisModule objects for all enabled modules."""
    ids = get_enabled_module_ids()
    modules = []
    for mid in ids:
        if mid in _MODULES:
            modules.append(_MODULES[mid])
        else:
            logger.warning(f"Unknown module ID in ENABLED_MODULES: '{mid}'")
    return modules


def is_module_enabled(module_id: str) -> bool:
    """Check whether a single module is enabled."""
    return module_id in get_enabled_module_ids()


def get_all_modules() -> list[AnalysisModule]:
    """Return all registered modules regardless of enablement."""
    return list(_MODULES.values())
