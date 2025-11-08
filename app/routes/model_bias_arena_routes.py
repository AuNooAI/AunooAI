#!/usr/bin/env python3
"""Model Bias Arena Routes - API endpoints for model bias monitoring."""

import logging
import asyncio
import io
import csv
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from app.database import Database, get_database_instance
from app.security.session import verify_session
from app.services.model_bias_arena_service import ModelBiasArenaService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/model-bias-arena",
    tags=["model_bias_arena"]
)


# Request Models
class CreateRunRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    benchmark_model: str = Field(..., min_length=1)
    selected_models: List[str] = Field(..., min_items=1, max_items=6)
    article_count: int = Field(25, ge=1, le=100)
    rounds: int = Field(1, ge=1, le=5)
    topic: Optional[str] = None


class RunResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    benchmark_model: str
    selected_models: List[str]
    article_count: int
    rounds: int
    current_round: int
    created_at: str
    completed_at: Optional[str]
    status: str


class ModelStatsResponse(BaseModel):
    mean_bias_score: float
    std_bias_score: float
    mean_confidence_score: float
    std_confidence_score: float
    mean_response_time: float
    successful_evaluations: int
    error_count: int
    total_evaluations: int
    success_rate: float


class RunResultsResponse(BaseModel):
    run_details: Dict[str, Any]
    statistics: Dict[str, ModelStatsResponse]


# Dependency to get service
def get_bias_arena_service(db: Database = Depends(get_database_instance)) -> ModelBiasArenaService:
    return ModelBiasArenaService(db)


@router.get("/models")
async def get_available_models(
    session=Depends(verify_session),
    service: ModelBiasArenaService = Depends(get_bias_arena_service)
):
    """Get list of available configured models."""
    try:
        models = service.get_available_models()
        return JSONResponse(content={"models": models})
    except Exception as e:
        logger.error(f"Error getting available models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runs")
async def create_run(
    request: CreateRunRequest,
    background_tasks: BackgroundTasks,
    session=Depends(verify_session),
    service: ModelBiasArenaService = Depends(get_bias_arena_service)
):
    """Create a new bias evaluation run."""
    try:
        # Validate models exist
        available_models = service.get_available_models()
        available_model_names = [m["name"] for m in available_models]
        
        if request.benchmark_model not in available_model_names:
            raise HTTPException(
                status_code=400, 
                detail=f"Benchmark model '{request.benchmark_model}' not available"
            )
        
        for model in request.selected_models:
            if model not in available_model_names:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Model '{model}' not available"
                )
        
        # Get username for notification
        username = session.get("user", {}).get("username")

        # Create the run and start evaluation in background (non-blocking)
        background_tasks.add_task(
            service.create_and_evaluate_run,
            name=request.name,
            description=request.description,
            benchmark_model=request.benchmark_model,
            selected_models=request.selected_models,
            article_count=request.article_count,
            topic=request.topic,
            rounds=request.rounds,
            username=username
        )

        # Return immediately without waiting for article sampling or evaluation
        run_id = -1  # Placeholder - actual ID will be created in background

        return JSONResponse(content={"run_id": run_id, "status": "started"})
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating bias evaluation run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs")
async def get_runs(
    session=Depends(verify_session),
    service: ModelBiasArenaService = Depends(get_bias_arena_service)
):
    """Get list of all bias evaluation runs."""
    try:
        runs = service.get_runs()
        
        # Convert to response model format
        response_runs = []
        for run in runs:
            response_runs.append(RunResponse(
                id=run["id"],
                name=run["name"],
                description=run["description"],
                benchmark_model=run["benchmark_model"],
                selected_models=run["selected_models"],
                article_count=run["article_count"],
                rounds=run["rounds"],
                current_round=run["current_round"],
                created_at=run["created_at"],
                completed_at=run["completed_at"],
                status=run["status"]
            ))
        
        return JSONResponse(content={"runs": [run.dict() for run in response_runs]})
        
    except Exception as e:
        logger.error(f"Error getting runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}")
async def get_run_details(
    run_id: int,
    session=Depends(verify_session),
    service: ModelBiasArenaService = Depends(get_bias_arena_service)
):
    """Get details for a specific run."""
    try:
        run_details = service.get_run_details(run_id)
        if not run_details:
            raise HTTPException(status_code=404, detail="Run not found")
        
        return JSONResponse(content={"run": run_details})
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting run details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/results")
async def get_run_results(
    run_id: int,
    session=Depends(verify_session),
    service: ModelBiasArenaService = Depends(get_bias_arena_service)
):
    """Get comprehensive results for a run."""
    try:
        results = service.get_run_results(run_id)
        if not results:
            raise HTTPException(status_code=404, detail="Run not found or no results available")
        
        return JSONResponse(content=results)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting run results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/articles")
async def get_run_articles(
    run_id: int,
    session=Depends(verify_session),
    service: ModelBiasArenaService = Depends(get_bias_arena_service)
):
    """Get articles used in a specific run."""
    try:
        articles = service.get_run_articles(run_id)
        return JSONResponse(content={"articles": articles})
        
    except Exception as e:
        logger.error(f"Error getting run articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/runs/{run_id}")
async def delete_run(
    run_id: int,
    session=Depends(verify_session),
    service: ModelBiasArenaService = Depends(get_bias_arena_service)
):
    """Delete a bias evaluation run."""
    try:
        success = service.delete_run(run_id)
        if not success:
            raise HTTPException(status_code=404, detail="Run not found")
        
        return JSONResponse(content={"message": "Run deleted successfully"})
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sample-articles")
async def sample_articles(
    count: int = 25,
    topic: Optional[str] = None,
    session=Depends(verify_session),
    service: ModelBiasArenaService = Depends(get_bias_arena_service)
):
    """Sample articles from the database for preview."""
    try:
        if count < 1 or count > 100:
            raise HTTPException(status_code=400, detail="Count must be between 1 and 100")
        
        articles = service.sample_articles(count=count, topic=topic)
        return JSONResponse(content={"articles": articles, "count": len(articles)})
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sampling articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/export/pdf")
async def export_run_to_pdf(
    run_id: int,
    session=Depends(verify_session),
    service: ModelBiasArenaService = Depends(get_bias_arena_service)
):
    """Export a run to PDF format (HTML report)."""
    try:
        html_data = service.export_run_to_pdf(run_id)
        if not html_data:
            raise HTTPException(status_code=404, detail="Run not found or no report data available")
        
        # Return as HTML that can be printed to PDF by the browser
        return Response(
            content=html_data, 
            media_type="text/html",
            headers={"Content-Disposition": f"inline; filename=model_bias_arena_report_{run_id}.html"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting run to PDF: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/export/png")
async def export_run_to_png(
    run_id: int,
    session=Depends(verify_session),
    service: ModelBiasArenaService = Depends(get_bias_arena_service)
):
    """Export a run to PNG format (ASCII art visualization)."""
    try:
        visualization_data = service.export_run_to_png(run_id)
        if not visualization_data:
            raise HTTPException(status_code=404, detail="Run not found or no visualization data available")
        
        # Return as text file with ASCII art visualization
        return Response(
            content=visualization_data, 
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename=model_bias_arena_visualization_{run_id}.txt"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting run to PNG: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/export/csv")
async def export_run_to_csv(
    run_id: int,
    session=Depends(verify_session),
    service: ModelBiasArenaService = Depends(get_bias_arena_service)
):
    """Export a run to CSV format."""
    try:
        csv_data = service.export_run_to_csv(run_id)
        if not csv_data:
            raise HTTPException(status_code=404, detail="Run not found or no CSV data available")
        
        return StreamingResponse(
            iter([csv_data]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=model_bias_arena_summary_{run_id}.csv"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting run to CSV: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/export-results/csv")
async def export_run_results_to_csv(
    run_id: int,
    session=Depends(verify_session),
    service: ModelBiasArenaService = Depends(get_bias_arena_service)
):
    """Export run results in detailed CSV format."""
    try:
        csv_data = service.export_run_results_to_csv(run_id)
        if not csv_data:
            raise HTTPException(status_code=404, detail="Run not found or no results data available")
        
        return StreamingResponse(
            iter([csv_data]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=model_bias_arena_detailed_{run_id}.csv"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting run results to CSV: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/validation")
async def get_bias_validation_results(
    run_id: int,
    session=Depends(verify_session),
    service: ModelBiasArenaService = Depends(get_bias_arena_service)
):
    """Get validation results comparing model predictions with known source bias."""
    try:
        validation_results = service.compare_results_with_source_bias(run_id)
        if not validation_results:
            raise HTTPException(status_code=404, detail="Run not found or no validation data available")
        
        return JSONResponse(content=validation_results)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting bias validation results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/source-bias-data")
async def get_source_bias_data(
    run_id: int,
    session=Depends(verify_session),
    service: ModelBiasArenaService = Depends(get_bias_arena_service)
):
    """Get known source bias data for articles in the run (for validation purposes)."""
    try:
        source_data = service.get_source_bias_validation_data(run_id)
        if not source_data:
            raise HTTPException(status_code=404, detail="Run not found or no source bias data available")
        
        return JSONResponse(content={"source_bias_data": source_data})
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting source bias data: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 