from app.crawlers import BaseCrawler
from app.crawlers import Crawl4AICrawler
from app.crawlers import FirecrawlCrawler
from typing import Dict
from dotenv import load_dotenv
import os


class CrawlerFactory:
    crawler_instance = None

    def __init__(self):
        pass

    @staticmethod
    def get_crawler(logger) -> BaseCrawler:
        try:
            if CrawlerFactory.crawler_instance is None:
                # First explicitly load environment variables to ensure keys are available
                load_dotenv(override=True)
                type = os.environ.get("CRAWLER", "firecrawl")
                logger.debug(f"Loading web crawler: {type}")

                crawler = None
                match type:
                    case "crawl4ai":
                        crawler = Crawl4AICrawler.instance(logger=logger, config={
                            "crawl4ai_url": os.environ.get("PROVIDER_CRAWL4AI_URL", ""),
                            "auth_token": os.environ.get("PROVIDER_CRAWL4AI_AUTH_TOKEN", ""),
                            "sleep_time": int(os.environ.get("CRAWLER_SLEEP_TIME", 2))
                        })
                    case "firecrawl":
                        crawler = FirecrawlCrawler.instance(logger=logger, config={
                            "api_key": os.environ.get("PROVIDER_FIRECRAWL_KEY", ""),

                        })
                    case _:
                        raise NotImplementedError

                logger.debug(f"Loaded web crawler: {type}")
                CrawlerFactory.crawler_instance = crawler
            return CrawlerFactory.crawler_instance
        except Exception as e:
            logger.error(f"Error initializing web crawler: {str(e)}", exc_info=True)

            import sys
            sys.exit(1)