from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field


class NewsletterRequest(BaseModel):
    """Request schema for newsletter compilation."""
    frequency: str = Field(..., description="Newsletter frequency (daily, weekly, monthly)")
    topics: List[str] = Field(..., description="List of topics to include")
    content_types: List[str] = Field(..., description="Types of content to include")
    start_date: Optional[date] = Field(None, description="Optional start date")
    end_date: Optional[date] = Field(None, description="Optional end date")


class NewsletterResponse(BaseModel):
    """Response schema for newsletter compilation."""
    message: str = Field(..., description="Status message")
    compiled_markdown: Optional[str] = Field(None, description="Compiled markdown content")
    request_payload: NewsletterRequest = Field(..., description="Original request payload") 