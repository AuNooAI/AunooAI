"""
Finetuning Service

Manages the finetuning pipeline for DeBERTa enrichment model.
Handles training job scheduling, status tracking, and model hot-swapping.

Usage:
    from app.services.finetuning_service import get_finetuning_service

    service = get_finetuning_service()

    # Check if ready for finetuning
    readiness = await service.check_readiness()

    # Trigger finetuning
    run_id = await service.trigger_finetune(topics=["AI", "Climate"])

    # Get run status
    status = await service.get_run_status(run_id)

    # Hot-swap model after training
    await service.hot_swap_model(run_id)
"""

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.training_bootstrap_service import (
    get_training_bootstrap_service,
    TRAINING_THRESHOLDS,
    ENRICHMENT_FIELDS,
)

logger = logging.getLogger(__name__)

# Model paths
BASE_DIR = Path(__file__).parent.parent.parent
MODELS_DIR = BASE_DIR / "models" / "enrichment_model"
CURRENT_MODEL_PATH = MODELS_DIR / "final"
BACKUP_MODEL_PATH = MODELS_DIR / "backup"
TRAINING_OUTPUT_DIR = MODELS_DIR / "training_runs"


class FinetuningService:
    """
    Manages finetuning pipeline for enrichment models.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if FinetuningService._initialized:
            return

        self._db = None
        self._bootstrap_service = None

        FinetuningService._initialized = True

    def _get_db(self):
        """Lazy-load database connection."""
        if self._db is None:
            from app.database import Database
            self._db = Database()
        return self._db

    def _get_bootstrap_service(self):
        """Lazy-load bootstrap service."""
        if self._bootstrap_service is None:
            self._bootstrap_service = get_training_bootstrap_service()
        return self._bootstrap_service

    async def check_readiness(self, topics: List[str] = None) -> Dict[str, Any]:
        """
        Check if there are enough samples for finetuning.

        Args:
            topics: Optional list of topics to check (default: all topics)

        Returns:
            Dict with readiness status and details
        """
        bootstrap = self._get_bootstrap_service()

        # Get all topics status
        all_status = await bootstrap.get_all_topics_status()

        if topics:
            all_status = [s for s in all_status if s["topic"] in topics]

        # Calculate totals
        total_samples = sum(s["total_samples"] for s in all_status)
        ready_topics = [s for s in all_status if s["overall_status"] in ("ready", "partial")]
        green_fields_count = sum(
            sum(1 for r in s["field_readiness"].values() if r == "green")
            for s in all_status
        )

        # Check minimum requirements
        min_samples_met = total_samples >= TRAINING_THRESHOLDS["finetune_min"]
        has_ready_topics = len(ready_topics) > 0

        return {
            "ready": min_samples_met and has_ready_topics,
            "total_samples": total_samples,
            "min_required": TRAINING_THRESHOLDS["finetune_min"],
            "topics_count": len(all_status),
            "ready_topics_count": len(ready_topics),
            "ready_topics": [t["topic"] for t in ready_topics],
            "green_fields_count": green_fields_count,
            "topics_status": all_status,
        }

    async def trigger_finetune(
        self,
        topics: List[str] = None,
        fields: List[str] = None,
    ) -> str:
        """
        Trigger a finetuning run.

        Args:
            topics: Topics to include (default: all ready topics)
            fields: Fields to train (default: all fields)

        Returns:
            Run ID for tracking
        """
        db = self._get_db()
        run_id = f"run_{uuid.uuid4().hex[:12]}"

        # Check readiness first
        readiness = await self.check_readiness(topics)

        if not readiness["ready"]:
            raise ValueError(
                f"Not enough samples for finetuning. "
                f"Have {readiness['total_samples']}, need {readiness['min_required']}"
            )

        # Use ready topics if not specified
        if topics is None:
            topics = readiness["ready_topics"]

        if fields is None:
            fields = ENRICHMENT_FIELDS

        # Create training run record
        try:
            import json
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO training_runs
                    (run_id, status, topics_included, fields_included, sample_count, created_at)
                    VALUES (:run_id, :status, :topics, :fields, :count, NOW())
                """, {
                    'run_id': run_id,
                    'status': 'pending',
                    'topics': json.dumps(topics),
                    'fields': json.dumps(fields),
                    'count': readiness["total_samples"],
                })
                conn.commit()

            logger.info(f"Created finetuning run {run_id} with {readiness['total_samples']} samples")

            # Start async training (in production, this would use a task queue)
            await self._start_training(run_id, topics, fields)

            return run_id

        except Exception as e:
            logger.error(f"Failed to create training run: {e}")
            raise

    async def _start_training(
        self,
        run_id: str,
        topics: List[str],
        fields: List[str],
    ):
        """
        Start the actual training process as a background job.

        1. Exports training data from database
        2. Runs DeBERTa training script
        3. Updates run status on completion
        4. Can be monitored via get_run_status()
        """
        import subprocess
        import threading

        db = self._get_db()

        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE training_runs
                    SET status = 'running', started_at = NOW()
                    WHERE run_id = :run_id
                """, {'run_id': run_id})
                conn.commit()

            # Create output directory for this run
            output_dir = TRAINING_OUTPUT_DIR / run_id
            output_dir.mkdir(parents=True, exist_ok=True)

            # Start training in background thread
            def run_training():
                try:
                    self._execute_training(run_id, topics, fields, output_dir)
                except Exception as e:
                    logger.error(f"Training failed: {e}")
                    self._update_run_status(run_id, 'failed', error_message=str(e))

            thread = threading.Thread(target=run_training, daemon=True)
            thread.start()

            logger.info(f"Training job {run_id} started in background")

        except Exception as e:
            logger.error(f"Failed to start training: {e}")
            self._update_run_status(run_id, 'failed', error_message=str(e))
            raise

    def _execute_training(
        self,
        run_id: str,
        topics: List[str],
        fields: List[str],
        output_dir: Path,
    ):
        """Execute the training pipeline (runs in background thread)."""
        import subprocess
        import json

        logger.info(f"[{run_id}] Starting training pipeline...")

        try:
            # Step 1: Export training data
            logger.info(f"[{run_id}] Step 1/3: Exporting training data...")
            self._update_run_status(run_id, 'exporting')

            # Use venv python
            python_path = str(BASE_DIR / ".venv" / "bin" / "python")

            export_cmd = [
                python_path, "scripts/export_training_data_for_deberta.py",
                "--min-samples", "20",
            ]
            if topics:
                export_cmd.extend(["--topics"] + topics)

            result = subprocess.run(
                export_cmd,
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                timeout=300,  # 5 min timeout for export
            )

            if result.returncode != 0:
                raise Exception(f"Export failed: {result.stderr}")

            logger.info(f"[{run_id}] Export complete")

            # Step 2: Train model
            logger.info(f"[{run_id}] Step 2/3: Training DeBERTa model...")
            self._update_run_status(run_id, 'training')

            train_cmd = [
                python_path, "scripts/train_enrichment_model.py",
                "--epochs", "3",
                "--batch-size", "16",
                "--device", "cpu",  # GPU occupied by vLLM
            ]

            result = subprocess.run(
                train_cmd,
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout for training
            )

            if result.returncode != 0:
                raise Exception(f"Training failed: {result.stderr}")

            logger.info(f"[{run_id}] Training complete")

            # Step 3: Copy model to run directory and mark complete
            logger.info(f"[{run_id}] Step 3/3: Finalizing...")

            model_path = MODELS_DIR / "final"
            if model_path.exists():
                import shutil
                run_model_path = output_dir / "model"
                if run_model_path.exists():
                    shutil.rmtree(run_model_path)
                shutil.copytree(model_path, run_model_path)

                # Parse metrics from training output
                metrics = self._parse_training_metrics(result.stdout)

                self._update_run_status(
                    run_id, 'completed',
                    model_path=str(run_model_path),
                    metrics=metrics
                )

                logger.info(f"[{run_id}] Training pipeline complete! Model at: {run_model_path}")
            else:
                raise Exception("Model output not found after training")

        except subprocess.TimeoutExpired:
            raise Exception("Training timed out")
        except Exception as e:
            raise

    def _parse_training_metrics(self, output: str) -> dict:
        """Parse metrics from training script output."""
        import re

        metrics = {}

        # Try to find F1 and accuracy scores
        f1_match = re.search(r"avg_f1_weighted['\"]?\s*[:=]\s*([0-9.]+)", output)
        if f1_match:
            metrics['avg_f1_weighted'] = float(f1_match.group(1))

        acc_match = re.search(r"accuracy['\"]?\s*[:=]\s*([0-9.]+)", output)
        if acc_match:
            metrics['accuracy'] = float(acc_match.group(1))

        return metrics

    def _update_run_status(
        self,
        run_id: str,
        status: str,
        error_message: str = None,
        model_path: str = None,
        metrics: dict = None,
    ):
        """Update training run status in database."""
        db = self._get_db()

        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()

                if status == 'completed':
                    import json
                    cursor.execute("""
                        UPDATE training_runs
                        SET status = :status,
                            completed_at = NOW(),
                            model_path = :model_path,
                            metrics = :metrics
                        WHERE run_id = :run_id
                    """, {
                        'run_id': run_id,
                        'status': status,
                        'model_path': model_path,
                        'metrics': json.dumps(metrics) if metrics else None,
                    })
                elif status == 'failed':
                    cursor.execute("""
                        UPDATE training_runs
                        SET status = :status,
                            completed_at = NOW(),
                            error_message = :error
                        WHERE run_id = :run_id
                    """, {
                        'run_id': run_id,
                        'status': status,
                        'error': error_message,
                    })
                else:
                    cursor.execute("""
                        UPDATE training_runs
                        SET status = :status
                        WHERE run_id = :run_id
                    """, {'run_id': run_id, 'status': status})

                conn.commit()
        except Exception as e:
            logger.error(f"Failed to update run status: {e}")

    async def get_run_status(self, run_id: str) -> Optional[Dict[str, Any]]:
        """
        Get status of a training run.

        Args:
            run_id: Training run ID

        Returns:
            Dict with run status or None if not found
        """
        db = self._get_db()

        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT run_id, status, topics_included, fields_included,
                           sample_count, metrics, started_at, completed_at,
                           model_path, error_message, created_at
                    FROM training_runs
                    WHERE run_id = :run_id
                """, {'run_id': run_id})

                row = cursor.fetchone()
                if not row:
                    return None

                return {
                    "run_id": row[0],
                    "status": row[1],
                    "topics_included": row[2],
                    "fields_included": row[3],
                    "sample_count": row[4],
                    "metrics": row[5],
                    "started_at": row[6].isoformat() if row[6] else None,
                    "completed_at": row[7].isoformat() if row[7] else None,
                    "model_path": row[8],
                    "error_message": row[9],
                    "created_at": row[10].isoformat() if row[10] else None,
                }

        except Exception as e:
            logger.error(f"Failed to get run status: {e}")
            return None

    async def list_runs(
        self,
        status: str = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        List training runs.

        Args:
            status: Filter by status (optional)
            limit: Maximum number of runs to return

        Returns:
            List of training run records
        """
        db = self._get_db()

        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                if status:
                    cursor.execute(f"""
                        SELECT run_id, status, topics_included, fields_included,
                               sample_count, metrics, started_at, completed_at,
                               created_at, error_message
                        FROM training_runs
                        WHERE status = :status
                        ORDER BY created_at DESC
                        LIMIT {limit}
                    """, {'status': status})
                else:
                    cursor.execute(f"""
                        SELECT run_id, status, topics_included, fields_included,
                               sample_count, metrics, started_at, completed_at,
                               created_at, error_message
                        FROM training_runs
                        ORDER BY created_at DESC
                        LIMIT {limit}
                    """)

                rows = cursor.fetchall()

                return [
                    {
                        "run_id": row[0],
                        "status": row[1],
                        "topics_included": row[2],
                        "fields_included": row[3],
                        "sample_count": row[4],
                        "metrics": row[5],
                        "started_at": row[6].isoformat() if row[6] else None,
                        "completed_at": row[7].isoformat() if row[7] else None,
                        "created_at": row[8].isoformat() if row[8] else None,
                        "error_message": row[9],
                    }
                    for row in rows
                ]

        except Exception as e:
            logger.error(f"Failed to list runs: {e}")
            return []

    async def hot_swap_model(self, run_id: str) -> bool:
        """
        Hot-swap the production model with a newly trained one.

        Args:
            run_id: Training run ID to deploy

        Returns:
            True if successful, False otherwise
        """
        db = self._get_db()

        try:
            # Get run details
            status = await self.get_run_status(run_id)
            if not status:
                raise ValueError(f"Run {run_id} not found")

            if status["status"] != "completed":
                raise ValueError(f"Run {run_id} is not completed (status: {status['status']})")

            model_path = status.get("model_path")
            if not model_path or not Path(model_path).exists():
                raise ValueError(f"Model path not found: {model_path}")

            # Backup current model
            import shutil
            if CURRENT_MODEL_PATH.exists():
                if BACKUP_MODEL_PATH.exists():
                    shutil.rmtree(BACKUP_MODEL_PATH)
                shutil.move(str(CURRENT_MODEL_PATH), str(BACKUP_MODEL_PATH))
                logger.info(f"Backed up current model to {BACKUP_MODEL_PATH}")

            # Copy new model
            shutil.copytree(model_path, CURRENT_MODEL_PATH)
            logger.info(f"Deployed new model from {model_path}")

            # Update run status
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE training_runs
                    SET status = 'deployed'
                    WHERE run_id = :run_id
                """, {'run_id': run_id})
                conn.commit()

            # Reload enrichment service
            from app.services.enrichment_service import get_enrichment_service
            enrichment = get_enrichment_service()
            enrichment.load_models(force_reload=True)
            logger.info("Enrichment service reloaded with new model")

            return True

        except Exception as e:
            logger.error(f"Hot swap failed: {e}")
            return False

    async def rollback_model(self) -> bool:
        """
        Rollback to the previous model version.

        Returns:
            True if successful, False otherwise
        """
        try:
            import shutil

            if not BACKUP_MODEL_PATH.exists():
                raise ValueError("No backup model available for rollback")

            # Remove current and restore backup
            if CURRENT_MODEL_PATH.exists():
                shutil.rmtree(CURRENT_MODEL_PATH)

            shutil.move(str(BACKUP_MODEL_PATH), str(CURRENT_MODEL_PATH))
            logger.info("Rolled back to previous model version")

            # Reload enrichment service
            from app.services.enrichment_service import get_enrichment_service
            enrichment = get_enrichment_service()
            enrichment.load_models(force_reload=True)
            logger.info("Enrichment service reloaded after rollback")

            return True

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False

    async def delete_run(self, run_id: str) -> bool:
        """
        Delete a training run record and its associated files.

        Args:
            run_id: Training run ID to delete

        Returns:
            True if successful, False if run not found
        """
        db = self._get_db()

        try:
            # Check if run exists
            status = await self.get_run_status(run_id)
            if not status:
                return False

            # Delete associated files if they exist
            import shutil
            run_dir = TRAINING_OUTPUT_DIR / run_id
            if run_dir.exists():
                shutil.rmtree(run_dir)
                logger.info(f"Deleted run directory: {run_dir}")

            # Delete from database
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM training_runs
                    WHERE run_id = :run_id
                """, {'run_id': run_id})
                conn.commit()

            logger.info(f"Deleted training run: {run_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete run {run_id}: {e}")
            raise

    def get_status(self) -> Dict[str, Any]:
        """Get service status information."""
        return {
            "models_dir": str(MODELS_DIR),
            "current_model_exists": CURRENT_MODEL_PATH.exists(),
            "backup_model_exists": BACKUP_MODEL_PATH.exists(),
            "thresholds": TRAINING_THRESHOLDS,
        }


# Singleton accessor
_service_instance = None


def get_finetuning_service() -> FinetuningService:
    """Get the singleton finetuning service."""
    global _service_instance
    if _service_instance is None:
        _service_instance = FinetuningService()
    return _service_instance
