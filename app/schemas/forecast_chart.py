"""
Pydantic schemas for forecast chart data structures.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

class ForecastChartRequest(BaseModel):
    """Request model for generating forecast charts."""
    topic: str = Field(..., description="Topic to analyze for forecast")
    timeframe: str = Field(default="365", description="Time period in days for data collection")
    title_prefix: str = Field(default="AI & Machine Learning", description="Prefix for chart title")

class ConsensusBand(BaseModel):
    """Model for consensus band data."""
    start_year_index: int = Field(..., description="Starting year index (0=2024)")
    end_year_index: int = Field(..., description="Ending year index")
    color: str = Field(..., description="Hex color code for the band")
    label: str = Field(..., description="Label describing the consensus type")
    category: str = Field(..., description="Category this consensus applies to")

class OutlierMarker(BaseModel):
    """Model for outlier marker data."""
    x_position: int = Field(..., description="X-axis position (year index)")
    label: str = Field(..., description="Text label for the outlier")
    position_type: str = Field(..., description="Position type: 'above' or 'below'")
    category: str = Field(..., description="Category this outlier applies to")

class ForecastChartData(BaseModel):
    """Model for complete forecast chart data."""
    themes: List[str] = Field(..., description="List of category themes")
    consensus_bands: List[ConsensusBand] = Field(..., description="Consensus band data")
    outlier_markers: List[List[OutlierMarker]] = Field(..., description="Outlier markers by theme")
    total_articles: int = Field(..., description="Total number of articles analyzed")
    topic: str = Field(..., description="Topic analyzed")
    timeframe: str = Field(..., description="Timeframe used for analysis")

class ForecastChartResponse(BaseModel):
    """Response model for forecast chart generation."""
    success: bool = Field(..., description="Whether the chart generation was successful")
    chart_data: str = Field(..., description="Base64 encoded chart image data URL")
    topic: str = Field(..., description="Topic that was analyzed")
    timeframe: str = Field(..., description="Timeframe used for analysis")
    message: str = Field(..., description="Status message")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")

class AvailableTopicsResponse(BaseModel):
    """Response model for available topics."""
    success: bool = Field(..., description="Whether the request was successful")
    topics: List[str] = Field(..., description="List of available topics")
    message: str = Field(..., description="Status message")

class CategoryAnalysis(BaseModel):
    """Model for category-specific analysis data."""
    category: str = Field(..., description="Category name")
    article_count: int = Field(..., description="Number of articles in this category")
    sentiment_distribution: Dict[str, int] = Field(..., description="Sentiment counts")
    time_to_impact_distribution: Dict[str, int] = Field(..., description="Time to impact counts")
    future_signal_distribution: Dict[str, int] = Field(..., description="Future signal counts")
    dominant_sentiment: str = Field(..., description="Most common sentiment")
    predicted_timeline: str = Field(..., description="Predicted timeline for impact")

class ForecastInsights(BaseModel):
    """Model for forecast insights and analysis."""
    topic: str = Field(..., description="Topic analyzed")
    analysis_date: datetime = Field(..., description="When the analysis was performed")
    total_articles: int = Field(..., description="Total articles analyzed")
    category_analyses: List[CategoryAnalysis] = Field(..., description="Per-category analysis")
    key_insights: List[str] = Field(..., description="Key insights from the analysis")
    consensus_summary: str = Field(..., description="Summary of consensus findings")
    outlier_summary: str = Field(..., description="Summary of outlier scenarios")
    confidence_level: str = Field(..., description="Overall confidence in predictions")
    
class ErrorResponse(BaseModel):
    """Model for error responses."""
    success: bool = Field(default=False, description="Success status (always False for errors)")
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(default=None, description="Detailed error information")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp") 