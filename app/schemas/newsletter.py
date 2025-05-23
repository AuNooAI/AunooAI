from datetime import date
from typing import List, Optional, Dict
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


class NewsletterPromptTemplate(BaseModel):
    """Schema for newsletter content type prompt template."""
    content_type_id: str = Field(..., description="Identifier for the content type")
    prompt_template: str = Field(..., description="Prompt template text")
    description: str = Field(..., description="Detailed description of what this prompt does")


class NewsletterPromptUpdate(BaseModel):
    """Schema for updating a newsletter prompt template."""
    prompt_template: str = Field(..., description="Updated prompt template text")
    description: Optional[str] = Field(None, description="Updated description")


class ProgressUpdate(BaseModel):
    """Schema for newsletter compilation progress updates."""
    status: str = Field(..., description="Status of the compilation (in_progress, completed, error)")
    progress: float = Field(..., description="Percentage of completion (0-100)")
    current_step: str = Field(..., description="Current step being processed")
    message: Optional[str] = Field(None, description="Additional status message") 