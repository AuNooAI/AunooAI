# This file makes the collectors directory a Python package
from .base_crawler import BaseCrawler
from .crawl4ai_crawler import Crawl4AICrawler
from .firecrawl_crawler import FirecrawlCrawler
from .crawler_factory import CrawlerFactory

__all__ = [
    'BaseCrawler',
    'Crawl4AICrawler',
    'FirecrawlCrawler',
    'CrawlerFactory',
]