"""
Prompt Management API Routes

Provides REST API for managing AI prompts stored in data/prompts/.
Supports loading, saving, listing, and validating prompts.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from app.services.prompt_loader import PromptLoader
from app.security.session import verify_session
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/prompts", tags=["Prompt Management"])


class PromptRequest(BaseModel):
    """Request to load a specific prompt."""
    feature: str = Field(..., description="Feature name (e.g., 'market_signals')")
    prompt_name: str = Field(default="current", description="Prompt file name without .json")
    subfolder: Optional[str] = Field(None, description="Optional subfolder within feature")


class SavePromptRequest(BaseModel):
    """Request to save a new prompt version."""
    feature: str = Field(..., description="Feature name")
    prompt_data: Dict[str, Any] = Field(..., description="Prompt dictionary")
    set_as_current: bool = Field(default=False, description="Set as current.json")
    subfolder: Optional[str] = Field(None, description="Optional subfolder within feature")


class ValidatePromptRequest(BaseModel):
    """Request to validate prompt structure."""
    prompt_data: Dict[str, Any] = Field(..., description="Prompt dictionary to validate")


@router.get("/list/{feature}")
async def list_prompts(
    feature: str,
    subfolder: Optional[str] = None,
    session=Depends(verify_session)
):
    """List all prompts for a feature.

    Args:
        feature: Feature name (e.g., 'market_signals')
        subfolder: Optional subfolder within feature

    Returns:
        List of prompt metadata
    """
    try:
        prompts = PromptLoader.list_prompts(feature, subfolder)
        return {
            "success": True,
            "feature": feature,
            "subfolder": subfolder,
            "prompts": prompts,
            "count": len(prompts)
        }
    except Exception as e:
        logger.error(f"Error listing prompts for {feature}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list prompts: {str(e)}"
        )


@router.post("/load")
async def load_prompt(
    request: PromptRequest,
    session=Depends(verify_session)
):
    """Load a specific prompt.

    Args:
        request: Prompt load request

    Returns:
        Prompt data with metadata
    """
    try:
        prompt = PromptLoader.load_prompt(
            request.feature,
            request.prompt_name,
            request.subfolder
        )

        # Extract variables from prompt
        variables = PromptLoader.get_prompt_variables(prompt)

        return {
            "success": True,
            "prompt": prompt,
            "variables": variables,
            "feature": request.feature,
            "prompt_name": request.prompt_name
        }
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error loading prompt: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load prompt: {str(e)}"
        )


@router.post("/save")
async def save_prompt(
    request: SavePromptRequest,
    session=Depends(verify_session)
):
    """Save a new prompt version.

    Args:
        request: Save prompt request

    Returns:
        Path to saved prompt file
    """
    try:
        # Validate prompt structure first
        is_valid, error_msg = PromptLoader.validate_prompt_schema(request.prompt_data)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid prompt structure: {error_msg}"
            )

        path = PromptLoader.save_prompt(
            request.feature,
            request.prompt_data,
            request.set_as_current,
            request.subfolder
        )

        return {
            "success": True,
            "path": path,
            "is_current": request.set_as_current,
            "version": request.prompt_data.get("version", "unknown")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving prompt: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save prompt: {str(e)}"
        )


@router.get("/features")
async def list_features(session=Depends(verify_session)):
    """List all features with prompts.

    Returns:
        List of feature names
    """
    try:
        features = PromptLoader.list_features()
        return {
            "success": True,
            "features": features,
            "count": len(features)
        }
    except Exception as e:
        logger.error(f"Error listing features: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list features: {str(e)}"
        )


@router.post("/validate")
async def validate_prompt(
    request: ValidatePromptRequest,
    session=Depends(verify_session)
):
    """Validate prompt structure.

    Args:
        request: Validation request

    Returns:
        Validation result
    """
    try:
        is_valid, error_msg = PromptLoader.validate_prompt_schema(request.prompt_data)

        if is_valid:
            # Extract variables from prompt
            variables = PromptLoader.get_prompt_variables(request.prompt_data)

            return {
                "success": True,
                "valid": True,
                "variables": variables,
                "variable_count": len(variables)
            }
        else:
            return {
                "success": True,
                "valid": False,
                "error": error_msg
            }
    except Exception as e:
        logger.error(f"Error validating prompt: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate prompt: {str(e)}"
        )


@router.get("/variables/{feature}")
async def get_prompt_variables(
    feature: str,
    prompt_name: str = "current",
    subfolder: Optional[str] = None,
    session=Depends(verify_session)
):
    """Get variables used in a prompt.

    Args:
        feature: Feature name
        prompt_name: Prompt file name
        subfolder: Optional subfolder

    Returns:
        List of variable names
    """
    try:
        prompt = PromptLoader.load_prompt(feature, prompt_name, subfolder)
        variables = PromptLoader.get_prompt_variables(prompt)

        # Get variable documentation from prompt metadata
        variable_docs = prompt.get("variables", {})

        variable_info = [
            {
                "name": var,
                "description": variable_docs.get(var, "No description available")
            }
            for var in variables
        ]

        return {
            "success": True,
            "feature": feature,
            "prompt_name": prompt_name,
            "variables": variable_info,
            "count": len(variables)
        }
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error getting prompt variables: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get variables: {str(e)}"
        )
