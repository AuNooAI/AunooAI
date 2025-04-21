from sqlalchemy import Column, String, DateTime, Boolean, Text, Integer
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from typing import Optional

Base = declarative_base()

class Article(Base):
    __tablename__ = "articles"

    uri = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    url = Column(String, nullable=True)
    publication_date = Column(DateTime, nullable=True)
    submission_date = Column(DateTime, default=datetime.utcnow)
    topic = Column(String, nullable=True)
    category = Column(String, nullable=True)
    sentiment = Column(String, nullable=True)
    future_signal = Column(String, nullable=True)
    news_source = Column(String, nullable=True)
    analyzed = Column(Boolean, default=False)
    ai_impact = Column(Integer, nullable=True)
    tags = Column(String, nullable=True)  # Stored as comma-separated string

    def __repr__(self):
        return f"<Article(uri='{self.uri}', title='{self.title}')>"

    def to_dict(self):
        """Convert the article to a dictionary."""
        return {
            "uri": self.uri,
            "title": self.title,
            "content": self.content,
            "summary": self.summary,
            "url": self.url,
            "publication_date": self.publication_date.isoformat() if self.publication_date else None,
            "submission_date": self.submission_date.isoformat() if self.submission_date else None,
            "topic": self.topic,
            "category": self.category,
            "sentiment": self.sentiment,
            "future_signal": self.future_signal,
            "news_source": self.news_source,
            "analyzed": self.analyzed,
            "ai_impact": self.ai_impact,
            "tags": self.tags.split(",") if self.tags else []
        } 