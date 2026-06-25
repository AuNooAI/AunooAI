"""
Preclassifier Training Service

Registry-based service for managing DeBERTa preclassifier training.
Supports sample counting, data export, training subprocess management, and model reload.

First entry: Brand Watcher (11-category article classifier).
"""

import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent.parent


@dataclass
class PreclassifierDef:
    """Definition of a preclassifier in the registry."""
    id: str
    display_name: str
    description: str
    model_dir: Path
    export_script: str
    train_script: str
    sample_query: str
    categories: List[str]
    min_samples: int = 100
    reload_fn: Optional[Callable] = None
    status_fn: Optional[Callable] = None


# ============================================================================
# Brand Watcher helpers
# ============================================================================

def _reload_bw_model():
    """Force-reload the brand watcher classifier model."""
    try:
        from app.services.brand_watcher_classifier_service import get_brand_watcher_classifier
        classifier = get_brand_watcher_classifier()
        return classifier.load_models(force_reload=True)
    except Exception as e:
        logger.error(f"Failed to reload brand watcher model: {e}")
        return False


def _get_bw_status():
    """Get brand watcher classifier status."""
    try:
        from app.services.brand_watcher_classifier_service import get_brand_watcher_classifier
        classifier = get_brand_watcher_classifier()
        return classifier.get_status()
    except Exception as e:
        return {"available": False, "error": str(e)}


# ============================================================================
# Registry
# ============================================================================

BW_CATEGORIES = [
    "Product & Innovation",
    "Financial Performance",
    "Leadership & Governance",
    "Brand Sentiment & Perception",
    "Competitive Landscape",
    "Legal & Regulatory",
    "Partnerships & Alliances",
    "ESG & Social Responsibility",
    "Customer & Product Issues",
    "Market Strategy & Expansion",
    "Media & Advertising",
]

PRECLASSIFIER_REGISTRY: Dict[str, PreclassifierDef] = {
    "brand-watcher": PreclassifierDef(
        id="brand-watcher",
        display_name="Brand Watcher",
        description="11-category brand article classifier (DeBERTa)",
        model_dir=BASE_DIR / "models" / "brand_watcher_classifier" / "final",
        export_script="scripts/export_brand_watcher_training_data.py",
        train_script="scripts/train_brand_watcher_classifier.py",
        sample_query="""
            SELECT category, COUNT(DISTINCT article_uri) as cnt
            FROM bw_article_categories
            WHERE classification_method = 'llm_semantic'
            GROUP BY category
        """,
        categories=BW_CATEGORIES,
        min_samples=100,
        reload_fn=_reload_bw_model,
        status_fn=_get_bw_status,
    ),
}


# ============================================================================
# Service
# ============================================================================

class PreclassifierTrainingService:
    """Singleton service for managing preclassifier training."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._training_state: Dict[str, dict] = {}
        self._init_states()

    def _init_states(self):
        """Initialize training state from persisted files."""
        for pid, defn in PRECLASSIFIER_REGISTRY.items():
            status_file = self._status_file(defn)
            state = {
                "status": "idle",
                "pid": None,
                "last_train_started": None,
                "last_train_completed": None,
                "sample_count": None,
                "error": None,
            }

            if status_file.exists():
                try:
                    with open(status_file) as f:
                        persisted = json.load(f)
                    state.update(persisted)
                    # Reset stale training status
                    if state["status"] == "training":
                        state["status"] = "interrupted"
                        state["error"] = "Training was interrupted (service restarted)"
                except Exception as e:
                    logger.warning(f"Failed to load persisted state for {pid}: {e}")

            self._training_state[pid] = state

    def _status_file(self, defn: PreclassifierDef) -> Path:
        """Get the status JSON file path for a preclassifier."""
        return defn.model_dir.parent / "training_status.json"

    def _persist_state(self, classifier_id: str):
        """Save training state to disk."""
        defn = PRECLASSIFIER_REGISTRY.get(classifier_id)
        if not defn:
            return
        status_file = self._status_file(defn)
        status_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(status_file, "w") as f:
                json.dump(self._training_state[classifier_id], f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to persist state for {classifier_id}: {e}")

    def _get_connection(self):
        """Get a database connection."""
        from app.database import get_database_instance
        db = get_database_instance()
        return db._temp_get_connection()

    # ------------------------------------------------------------------
    # Sample counting
    # ------------------------------------------------------------------

    def get_sample_counts(self, classifier_id: str) -> dict:
        """Get per-category sample counts for a preclassifier."""
        defn = PRECLASSIFIER_REGISTRY.get(classifier_id)
        if not defn:
            raise ValueError(f"Unknown preclassifier: {classifier_id}")

        conn = None
        try:
            from sqlalchemy import text
            conn = self._get_connection()

            result = conn.execute(text(defn.sample_query))
            rows = result.fetchall()

            category_counts = {}
            total = 0
            for row in rows:
                cat, cnt = row[0], row[1]
                category_counts[cat] = cnt
                total += cnt

            # Fill in zeros for missing categories
            for cat in defn.categories:
                if cat not in category_counts:
                    category_counts[cat] = 0

            # Calculate readiness
            categories_ready = sum(
                1 for c in defn.categories
                if category_counts.get(c, 0) >= defn.min_samples
            )

            if categories_ready == len(defn.categories):
                overall_readiness = "ready"
            elif categories_ready > 0:
                overall_readiness = "partial"
            else:
                overall_readiness = "not_ready"

            return {
                "total_samples": total,
                "category_counts": category_counts,
                "categories_ready": categories_ready,
                "categories_total": len(defn.categories),
                "overall_readiness": overall_readiness,
                "min_samples_per_category": defn.min_samples,
            }

        except Exception as e:
            logger.error(f"Error getting sample counts for {classifier_id}: {e}")
            raise
        finally:
            if conn:
                conn.close()

    # ------------------------------------------------------------------
    # Full status
    # ------------------------------------------------------------------

    def get_status(self, classifier_id: str) -> dict:
        """Get full status for a preclassifier."""
        defn = PRECLASSIFIER_REGISTRY.get(classifier_id)
        if not defn:
            raise ValueError(f"Unknown preclassifier: {classifier_id}")

        # Sample counts
        try:
            sample_info = self.get_sample_counts(classifier_id)
        except Exception:
            sample_info = {
                "total_samples": 0,
                "category_counts": {c: 0 for c in defn.categories},
                "categories_ready": 0,
                "categories_total": len(defn.categories),
                "overall_readiness": "not_ready",
                "min_samples_per_category": defn.min_samples,
            }

        # Model status
        model_status = None
        model_available = False
        if defn.status_fn:
            model_status = defn.status_fn()
            model_available = model_status.get("available", False) if model_status else False

        # Training state
        state = self._training_state.get(classifier_id, {})

        # Check if model dir has weights
        has_model = defn.model_dir.exists() and any(
            defn.model_dir.glob("*.bin")
        ) or any(defn.model_dir.glob("*.safetensors")) if defn.model_dir.exists() else False

        return {
            "id": defn.id,
            "display_name": defn.display_name,
            "description": defn.description,
            "model_available": model_available,
            "training_status": state.get("status", "idle"),
            **sample_info,
            "last_trained": state.get("last_train_completed"),
            "error": state.get("error"),
            "model_status": model_status,
            "pid": state.get("pid"),
            "last_train_started": state.get("last_train_started"),
            "last_train_completed": state.get("last_train_completed"),
            "sample_count": state.get("sample_count"),
        }

    # ------------------------------------------------------------------
    # List all preclassifiers
    # ------------------------------------------------------------------

    def list_all(self) -> List[dict]:
        """List all registered preclassifiers with status."""
        results = []
        for cid in PRECLASSIFIER_REGISTRY:
            try:
                status = self.get_status(cid)
                results.append(status)
            except Exception as e:
                logger.error(f"Error getting status for {cid}: {e}")
                defn = PRECLASSIFIER_REGISTRY[cid]
                results.append({
                    "id": defn.id,
                    "display_name": defn.display_name,
                    "description": defn.description,
                    "model_available": False,
                    "training_status": "error",
                    "total_samples": 0,
                    "category_counts": {},
                    "categories_ready": 0,
                    "categories_total": len(defn.categories),
                    "overall_readiness": "not_ready",
                    "min_samples_per_category": defn.min_samples,
                    "last_trained": None,
                    "error": str(e),
                })
        return results

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(self, classifier_id: str, epochs: int = None, batch_size: int = None) -> dict:
        """Export data and trigger training in a background subprocess."""
        defn = PRECLASSIFIER_REGISTRY.get(classifier_id)
        if not defn:
            raise ValueError(f"Unknown preclassifier: {classifier_id}")

        state = self._training_state.get(classifier_id, {})
        if state.get("status") == "training":
            raise ValueError(f"{defn.display_name} is already training (PID: {state.get('pid')})")

        # Step 1: Export data
        export_path = BASE_DIR / defn.export_script
        if not export_path.exists():
            raise FileNotFoundError(f"Export script not found: {export_path}")

        logger.info(f"Exporting training data for {defn.display_name}...")
        try:
            export_result = subprocess.run(
                ["python", str(export_path)],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(BASE_DIR),
            )
            if export_result.returncode != 0:
                error_msg = export_result.stderr.strip() or "Export failed"
                raise RuntimeError(f"Export failed: {error_msg}")
            logger.info(f"Export completed: {export_result.stdout.strip()}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Export timed out after 60 seconds")

        # Get sample count after export
        try:
            sample_info = self.get_sample_counts(classifier_id)
            sample_count = sample_info["total_samples"]
        except Exception:
            sample_count = 0

        # Step 2: Start training subprocess
        train_path = BASE_DIR / defn.train_script
        if not train_path.exists():
            raise FileNotFoundError(f"Training script not found: {train_path}")

        cmd = ["python", str(train_path)]
        if epochs:
            cmd.extend(["--epochs", str(epochs)])
        if batch_size:
            cmd.extend(["--batch-size", str(batch_size)])

        logger.info(f"Starting training for {defn.display_name}: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            cwd=str(BASE_DIR),
        )

        # Update state
        now = datetime.utcnow().isoformat()
        self._training_state[classifier_id] = {
            "status": "training",
            "pid": process.pid,
            "last_train_started": now,
            "last_train_completed": state.get("last_train_completed"),
            "sample_count": sample_count,
            "error": None,
        }
        self._persist_state(classifier_id)

        # Start daemon monitor thread
        thread = threading.Thread(
            target=self._monitor_training,
            args=(classifier_id, process),
            daemon=True,
            name=f"preclassifier-monitor-{classifier_id}",
        )
        thread.start()

        return {
            "status": "training",
            "pid": process.pid,
            "message": f"Exported {sample_count} samples. Training started for {defn.display_name}",
        }

    def _monitor_training(self, classifier_id: str, process: subprocess.Popen):
        """Monitor a training subprocess and update state on completion."""
        defn = PRECLASSIFIER_REGISTRY.get(classifier_id)
        try:
            stdout, stderr = process.communicate(timeout=7200)  # 2 hour timeout
            now = datetime.utcnow().isoformat()

            if process.returncode == 0:
                logger.info(f"Training completed for {classifier_id}")
                self._training_state[classifier_id].update({
                    "status": "completed",
                    "last_train_completed": now,
                    "pid": None,
                    "error": None,
                })

                # Auto-reload model
                if defn and defn.reload_fn:
                    try:
                        success = defn.reload_fn()
                        if success:
                            logger.info(f"Model reloaded for {classifier_id}")
                        else:
                            logger.warning(f"Model reload returned False for {classifier_id}")
                    except Exception as e:
                        logger.error(f"Model reload failed for {classifier_id}: {e}")
            else:
                error_msg = stderr.decode() if isinstance(stderr, bytes) else stderr
                error_msg = error_msg.strip()[-500:] if error_msg else "Training failed"
                logger.error(f"Training failed for {classifier_id}: {error_msg}")
                self._training_state[classifier_id].update({
                    "status": "failed",
                    "pid": None,
                    "error": error_msg,
                })

        except subprocess.TimeoutExpired:
            process.kill()
            self._training_state[classifier_id].update({
                "status": "failed",
                "pid": None,
                "error": "Training timed out after 2 hours",
            })
        except Exception as e:
            logger.error(f"Monitor error for {classifier_id}: {e}")
            self._training_state[classifier_id].update({
                "status": "failed",
                "pid": None,
                "error": str(e),
            })
        finally:
            self._persist_state(classifier_id)

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload_model(self, classifier_id: str) -> dict:
        """Force-reload a preclassifier model."""
        defn = PRECLASSIFIER_REGISTRY.get(classifier_id)
        if not defn:
            raise ValueError(f"Unknown preclassifier: {classifier_id}")

        if not defn.reload_fn:
            raise ValueError(f"No reload function for {classifier_id}")

        success = defn.reload_fn()
        model_status = defn.status_fn() if defn.status_fn else None

        return {
            "status": "reloaded" if success else "failed",
            "model_available": success,
            "model_status": model_status,
        }


# ============================================================================
# Singleton accessor
# ============================================================================

_service: Optional[PreclassifierTrainingService] = None


def get_preclassifier_training_service() -> PreclassifierTrainingService:
    global _service
    if _service is None:
        _service = PreclassifierTrainingService()
    return _service
