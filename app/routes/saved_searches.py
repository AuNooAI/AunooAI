import json
import os
from typing import List, Optional
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from app.security.session import verify_session


# Define the router
router = APIRouter(tags=["saved_searches"])


# Path to saved searches config file
SAVED_SEARCHES_PATH = os.path.join("app", "config", "saved_searches.json")


# Models
class SavedSearch(BaseModel):
    id: str = Field(
        default_factory=lambda: f"search_{uuid.uuid4().hex[:10]}"
    )
    name: str
    description: Optional[str] = None
    tags: Optional[str] = None
    query: str
    created_at: Optional[str] = Field(
        default_factory=lambda: datetime.now().isoformat()
    )


# Helper functions
def load_saved_searches() -> List[SavedSearch]:
    """Load saved searches from the config file."""
    if not os.path.exists(SAVED_SEARCHES_PATH):
        # Create the file if it doesn't exist
        with open(SAVED_SEARCHES_PATH, "w") as f:
            json.dump([], f)
        return []
    
    try:
        with open(SAVED_SEARCHES_PATH, "r") as f:
            data = json.load(f)
        return [SavedSearch(**item) for item in data]
    except Exception as e:
        print(f"Error loading saved searches: {e}")
        return []


def save_searches(searches: List[SavedSearch]) -> bool:
    """Save searches to the config file."""
    try:
        with open(SAVED_SEARCHES_PATH, "w") as f:
            json.dump([s.dict() for s in searches], f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving searches: {e}")
        return False


# Routes
@router.get("/api/saved-searches", response_model=List[SavedSearch])
async def get_saved_searches(session=Depends(verify_session)):
    """Get all saved searches."""
    return load_saved_searches()


@router.post("/api/saved-searches", response_model=SavedSearch)
async def create_saved_search(search: SavedSearch, session=Depends(verify_session)):
    """Create or update a saved search."""
    searches = load_saved_searches()
    
    # Check if this is an update (ID exists)
    for i, existing in enumerate(searches):
        if existing.id == search.id:
            searches[i] = search
            if save_searches(searches):
                return search
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to save search"
                )
    
    # New search
    searches.append(search)
    if save_searches(searches):
        return search
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save search"
        )


@router.delete("/api/saved-searches/{search_id}")
async def delete_saved_search(search_id: str, session=Depends(verify_session)):
    """Delete a saved search."""
    searches = load_saved_searches()
    original_count = len(searches)
    searches = [s for s in searches if s.id != search_id]
    
    if len(searches) == original_count:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Search with ID {search_id} not found"
        )
    
    if save_searches(searches):
        return {"detail": "Search deleted successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete search"
        ) 