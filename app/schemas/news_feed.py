from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class BiasRating(str, Enum):
    LEFT = "left"
    LEFT_CENTER = "left-center"
    CENTER = "center"
    RIGHT_CENTER = "right-center"
    RIGHT = "right"
    MIXED = "mixed"


class FactualityRating(str, Enum):
    VERY_HIGH = "very-high"
    HIGH = "high"
    MOSTLY_FACTUAL = "mostly-factual"
    MIXED = "mixed"
    LOW = "low"
    VERY_LOW = "very-low"


class ArticleSource(BaseModel):
    name: str
    bias: Optional[BiasRating] = None
    factuality: Optional[FactualityRating] = None
    credibility_rating: Optional[str] = None
    country: Optional[str] = None


class NewsArticle(BaseModel):
    uri: str
    title: str
    summary: str
    url: Optional[str] = None
    publication_date: Optional[datetime] = None
    source: ArticleSource
    sentiment: Optional[str] = None
    category: Optional[str] = None
    time_to_impact: Optional[str] = None
    tags: List[str] = []


class RelatedArticle(BaseModel):
    title: str
    source: str
    url: Optional[str] = None
    bias: Optional[BiasRating] = None
    summary: str
    similarity_score: Optional[float] = None  # For vector similarity ranking


class TopStory(BaseModel):
    headline: str
    summary: str
    primary_article: NewsArticle
    related_articles: List[RelatedArticle] = []
    topic_description: str
    bias_analysis: Dict[str, Any] = Field(default_factory=dict)
    factuality_assessment: str
    perspective_breakdown: Dict[str, List[str]] = Field(default_factory=dict)  # left, center, right perspectives


class DailyOverview(BaseModel):
    date: datetime
    title: str = "Daily News Overview"
    top_stories: List[TopStory] = []
    generated_at: datetime = Field(default_factory=datetime.now)
    total_articles_analyzed: int = 0
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class SixArticlesReport(BaseModel):
    date: datetime
    title: str = "Six Most Interesting Articles"
    articles: List[TopStory] = []  # Reuse TopStory structure for detailed analysis
    generated_at: datetime = Field(default_factory=datetime.now)
    executive_summary: str = ""
    key_themes: List[str] = []
    bias_distribution: Dict[str, int] = Field(default_factory=dict)
    factuality_overview: Dict[str, int] = Field(default_factory=dict)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class NewsFeedRequest(BaseModel):
    date: Optional[datetime] = None
    date_range: Optional[str] = None  # Date range: "24h", "7d", "30d", "3m", "1y", "all", or "start_date,end_date"
    topic: Optional[str] = None
    max_articles: int = Field(default=50, ge=10, le=200)
    include_bias_analysis: bool = True
    model: str = "gpt-4o"
    profile_id: Optional[int] = None  # Organizational profile for contextualized analysis
    
    
class NewsFeedResponse(BaseModel):
    overview: DailyOverview
    six_articles: SixArticlesReport
    generated_at: datetime = Field(default_factory=datetime.now)
    processing_time_seconds: float = 0.0
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
