from app.crawlers import BaseCrawler
from typing import Dict
from firecrawl import FirecrawlApp


class FirecrawlCrawler(BaseCrawler):
    firecrawl_instance = None

    def batch_scrape_urls(self, urls, params={}):
        batch_scrape_results = self.firecrawl_instance.batch_scrape_urls(
            urls,
            formats=['markdown'],
            **params
        )

        return {result.metadata['sourceURL']: result.markdown for _, result in enumerate(batch_scrape_results.data)}


    def scrape_url(self, url):
        result = self.firecrawl_instance.scrape_url(url, formats=['markdown'])
        return {"markdown": result.markdown}

    def initialize(self):
        self.firecrawl_instance = FirecrawlApp(api_key=self._config['api_key'])
        self._logger.info("Testing firecrawl with a basic request...")
        try:
            test_data = self.scrape_url(url='https://www.example.com')

            if 'markdown' in test_data:
                self._logger.info("firecrawl test successful")
            else:
                self._logger.warning(f"firecrawl test request failed: unknown reason.")
        except Exception as test_error:
            self._logger.warning(f"firecrawl test request failed: {str(test_error)}")
