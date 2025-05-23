from typing import List, Dict

from fastapi import APIRouter, status, Depends
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse
from fastapi import Request
from fastapi.templating import Jinja2Templates
from app.security.session import verify_session

from app.services import ontology_service as svc

router = APIRouter(prefix="/api", tags=["Scenarios"])


# -------------------------------------------------------------------
# Request models
# -------------------------------------------------------------------


class BuildingBlockBase(BaseModel):
    name: str = Field(..., min_length=1)
    kind: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=1)
    options: List[str] | None = None


class BuildingBlockCreate(BuildingBlockBase):
    pass


class BuildingBlockUpdate(BaseModel):
    name: str | None = Field(None, min_length=1)
    kind: str | None = Field(None, min_length=1)
    prompt: str | None = Field(None, min_length=1)
    options: List[str] | None = None


class ScenarioCreate(BaseModel):
    name: str = Field(..., min_length=1)
    topic: str = Field(..., min_length=1)
    block_ids: List[int]


class ScenarioUpdate(BaseModel):
    name: str | None = None
    topic: str | None = None
    block_ids: List[int] | None = None


# -------------------------------------------------------------------
# Building-block endpoints
# -------------------------------------------------------------------


@router.post("/building_blocks", status_code=status.HTTP_201_CREATED)
async def create_building_block(payload: BuildingBlockCreate, session=Depends(verify_session)) -> Dict:
    """Create a new ontological building-block."""

    return svc.create_building_block(
        name=payload.name,
        kind=payload.kind,
        prompt=payload.prompt,
        options=payload.options,
    )


@router.get("/building_blocks", response_model=List[Dict])
async def list_building_blocks(session=Depends(verify_session)) -> List[Dict]:
    """Return all building-blocks."""

    return svc.list_building_blocks()


@router.patch("/building_blocks/{block_id}")
async def update_building_block(
    block_id: int, payload: BuildingBlockUpdate, session=Depends(verify_session)
) -> Dict:
    """Update building block fields."""

    return svc.update_building_block(
        block_id=block_id,
        name=payload.name,
        kind=payload.kind,
        prompt=payload.prompt,
        options=payload.options,
    )


@router.delete("/building_blocks/{block_id}")
async def delete_building_block(block_id: int, session=Depends(verify_session)) -> Dict:
    """Delete a building block."""

    return svc.delete_building_block(block_id)


# -------------------------------------------------------------------
# Scenario endpoints
# -------------------------------------------------------------------


@router.post("/scenarios", status_code=status.HTTP_201_CREATED)
async def create_scenario(payload: ScenarioCreate, session=Depends(verify_session)) -> Dict:
    """Create a scenario and its dedicated article table."""

    return svc.create_scenario(
        name=payload.name,
        topic=payload.topic,
        block_ids=payload.block_ids,
    )


@router.get("/scenarios/{scenario_id}")
async def get_scenario(scenario_id: int, session=Depends(verify_session)) -> Dict:
    """Retrieve a scenario by id."""

    return svc.get_scenario(scenario_id)


@router.get("/scenarios", response_model=List[Dict])
async def list_scenarios(session=Depends(verify_session)) -> List[Dict]:
    """List saved scenarios."""

    return svc.list_scenarios()


@router.patch("/scenarios/{scenario_id}")
async def update_scenario(scenario_id: int, payload: ScenarioUpdate, session=Depends(verify_session)) -> Dict:
    """Update scenario details."""

    return svc.update_scenario(
        scenario_id,
        name=payload.name,
        topic=payload.topic,
        block_ids=payload.block_ids,
    )


# -------------------------------------------------------------------
# Delete scenario endpoint
# -------------------------------------------------------------------


@router.delete("/scenarios/{scenario_id}")
async def delete_scenario(scenario_id: int, session=Depends(verify_session)) -> Dict:
    """Delete a scenario and its associated article table."""

    return svc.delete_scenario(scenario_id)


# -------------------------------------------------------------------
# Compose prompt endpoint
# -------------------------------------------------------------------


@router.get("/scenarios/{scenario_id}/prompt")
async def compose_scenario_prompt(scenario_id: int, session=Depends(verify_session)) -> Dict[str, str]:
    """Return merged system & user prompt built from scenario blocks."""

    return svc.compose_prompt(scenario_id)


# -------------------------------------------------------------------
# Scenario Editor Page (HTML)
# -------------------------------------------------------------------


page_router = APIRouter(tags=["Scenario-Editor-Page"])


@page_router.get("/scenario-editor", response_class=HTMLResponse)
async def scenario_editor_page(request: Request):
    """Render the Scenario Builder UI (dynamic building-block selection)."""

    return Jinja2Templates(directory="templates").TemplateResponse(
        "scenario_editor.html",
        {
            "request": request,
            "session": request.session if hasattr(request, "session") else {},
        },
    )


# Alias with underscore for backward compatibility
@page_router.get("/scenario_editor", response_class=HTMLResponse)
async def scenario_editor_page_alias(request: Request):
    """Alias for clients using underscore URL."""

    return await scenario_editor_page(request) 