from fastapi import APIRouter, status, Depends
from pydantic import BaseModel, Field

from app.services import auspex_service as auspex
from app.security.session import verify_session

router = APIRouter(prefix="/api/auspex", tags=["Auspex"])


class SuggestRequest(BaseModel):
    kind: str = Field(...)
    scenario_name: str = Field(...)
    scenario_description: str | None = None


@router.post("/block-options", status_code=status.HTTP_200_OK)
async def suggest_block_options(req: SuggestRequest, session=Depends(verify_session)):
    """Return list of option suggestions for a building-block."""

    return {
        "options": auspex.suggest_options(req.kind, req.scenario_name, req.scenario_description),
    } 