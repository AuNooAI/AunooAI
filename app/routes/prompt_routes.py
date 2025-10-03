from fastapi import APIRouter, HTTPException, Request, Path, status, Depends
from fastapi.responses import HTMLResponse
from app.security.session import verify_session
from pydantic import BaseModel
from typing import List, Dict, Optional
from app.analyzers.prompt_manager import PromptManager, PromptManagerError
from app.analyzers.prompt_templates import PromptTemplates
from app.core.shared import templates
import logging
import os

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,  # Ensure this is set to DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Create router with prefix
router = APIRouter(prefix="/api")

# Initialize prompt manager with absolute path
app_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
storage_dir = os.path.join(app_root, "data", "prompts")
prompt_manager = PromptManager(storage_dir=storage_dir)

# Initialize with default templates
try:
    prompt_manager.initialize_defaults(PromptTemplates.DEFAULT_TEMPLATES)
    logger.info("Initialized default templates in %s", storage_dir)
except Exception as e:
    logger.error("Failed to initialize default templates: %s", str(e))
    # Don't raise here - let the app continue but log the error

class PromptData(BaseModel):
    system_prompt: str
    user_prompt: str

class VersionResponse(BaseModel):
    hash: str
    version: str
    system_prompt: str
    user_prompt: str
    created_at: str

class VersionListResponse(BaseModel):
    versions: List[VersionResponse]

class TypeResponse(BaseModel):
    name: str
    display_name: str

class TypeListResponse(BaseModel):
    types: List[TypeResponse]

@router.get("/config", response_class=HTMLResponse, include_in_schema=False)
async def config_page(request: Request, session=Depends(verify_session)):
    return templates.TemplateResponse("config.html", {"request": request, "session": session})

@router.get("/prompts/types", response_model=TypeListResponse)
async def get_prompt_types(session=Depends(verify_session)):
    try:
        types = prompt_manager.get_prompt_types()
        return {"types": types}
    except PromptManagerError as e:
        logger.error(f"Failed to get prompt types: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/prompts/{prompt_type}/versions", response_model=VersionListResponse)
async def get_prompt_versions(
    prompt_type: str = Path(..., description="The type of prompt to get versions for"),
    session=Depends(verify_session)
):
    try:
        versions = prompt_manager.get_versions(prompt_type)
        return {"versions": versions}
    except PromptManagerError as e:
        logger.error(f"Failed to get versions for {prompt_type}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/prompts/{prompt_type}/{version_hash}", response_model=VersionResponse)
async def get_prompt_version(
    prompt_type: str = Path(..., description="The type of prompt"),
    version_hash: str = Path(..., description="The version hash or 'current'"),
    session=Depends(verify_session)
):
    try:
        version = prompt_manager.get_version(prompt_type, version_hash)
        return version
    except PromptManagerError as e:
        logger.error(f"Failed to get version {version_hash} for {prompt_type}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/prompts/{prompt_type}", response_model=VersionResponse)
async def save_prompt_version(
    prompt_type: str = Path(..., description="The type of prompt"),
    prompt_data: PromptData = None,
    session=Depends(verify_session)
):
    try:
        if not prompt_data:
            raise HTTPException(status_code=400, detail="Missing prompt data")

        version = prompt_manager.save_version(
            prompt_type,
            prompt_data.system_prompt,
            prompt_data.user_prompt
        )
        return version
    except PromptManagerError as e:
        logger.error(f"Failed to save version for {prompt_type}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/prompts/{prompt_type}/{version_hash}/restore", response_model=VersionResponse)
async def restore_prompt_version(
    prompt_type: str = Path(..., description="The type of prompt"),
    version_hash: str = Path(..., description="The version hash to restore"),
    session=Depends(verify_session)
):
    try:
        version = prompt_manager.restore_version(prompt_type, version_hash)
        return version
    except PromptManagerError as e:
        logger.error(f"Failed to restore version {version_hash} for {prompt_type}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/prompts/{prompt_type}/compare")
async def compare_prompt_versions(
    prompt_type: str = Path(..., description="The type of prompt"),
    version_a: str = None,
    version_b: str = "current",
    session=Depends(verify_session)
):
    try:
        if not version_a:
            raise HTTPException(status_code=400, detail="Missing version_a parameter")

        comparison = prompt_manager.compare_versions(prompt_type, version_a, version_b)
        return comparison
    except PromptManagerError as e:
        logger.error(f"Failed to compare versions for {prompt_type}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/prompts/{prompt_type}/{version_hash}")
async def delete_prompt_version(
    prompt_type: str = Path(..., description="The type of prompt"),
    version_hash: str = Path(..., description="The version hash to delete"),
    session=Depends(verify_session)
):
    try:
        if version_hash == "current":
            raise HTTPException(status_code=400, detail="Cannot delete current version")
        
        prompt_manager.delete_version(prompt_type, version_hash)
        return {"status": "success", "message": "Version deleted successfully"}
    except PromptManagerError as e:
        logger.error(f"Failed to delete version {version_hash} for {prompt_type}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



