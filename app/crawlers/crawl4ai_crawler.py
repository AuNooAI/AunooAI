from app.crawlers import BaseCrawler
import requests
import time


class Crawl4AICrawler(BaseCrawler):
    # TODO: Add browser configuration?
    def initialize(self):
        self._logger.info("Testing crawl4ai with a basic request...")
        try:
            test_data = self.scrape_url(url='https://www.example.com')['data']

            if 'markdown' in test_data:
                self._logger.info("crawl4ai test successful")
            else:
                self._logger.warning(f"crawl4ai test request failed: unknown reason.")
        except Exception as test_error:
            self._logger.warning(f"crawl4ai test request failed: {str(test_error)}")

    def get_page_code(self, url):
        headers = {"Authorization": f"Bearer {self._config['auth_token']}"}

        # Basic crawl with authentication
        response = requests.post(
            f"{self._config['crawl4ai_url']}/crawl",
            headers=headers,
            json={
                "urls": url,
                "crawler_params": {
                    # Browser Configuration
                    "text_mode": True,
                    # "extra_args": ["--enable-reader-mode=true"],
                    # "headless": True,  # Run in headless mode
                    "browser_type": "chromium",  # chromium/firefox/webkit
                    # "user_agent": "custom-agent",        # Custom user agent
                    # Performance & Behavior
                    # "page_timeout": 30000,  # Page load timeout (ms)
                    # "verbose": True,  # Enable detailed logging
                    # Anti-Detection Features
                    # "simulate_user": True,  # Simulate human behavior
                    # "magic": True,  # Advanced anti-detection
                    # "override_navigator": True,  # Override navigator properties
                    # Session Management
                    # "user_data_dir": "./browser-data",  # Browser profile location
                    # "use_managed_browser": True,  # Use persistent browser
                },
                "priority": 10
            }
        )

        # Returned data format, for a single page (if multiple, then the same format is stored in 'results' instead
        # of 'result':
        # {
        #   "url": "string",                    // Final URL crawled (after redirects)
        #   "html": "string",                   // Raw, unmodified HTML
        #   "success": "boolean",               // Whether crawl completed successfully
        #   "cleaned_html": "string|null",     // Sanitized HTML with scripts/styles removed
        #   "media": {                          // Extracted media content
        #     "images": [...],
        #     "audio": [...],
        #     "video": [...],
        #     "tables": [...]
        #   },
        #   "links": {                          // Extracted links
        #     "internal": [...],
        #     "external": [...]
        #   },
        #   "downloaded_files": ["string[]|null"], // Downloaded file paths
        #   "screenshot": "string|null",        // Base64-encoded PNG screenshot
        #   "pdf": "bytes|null",               // PDF version of page
        #   "mhtml": "string|null",            // MHTML snapshot with all resources
        #   "markdown": {                      // Markdown generation result
        #     "raw_markdown": "string",
        #     "markdown_with_citations": "string",
        #     "references_markdown": "string",
        #     "fit_markdown": "string|null",
        #     "fit_html": "string|null"
        #   },
        #   "extracted_content": "string|null", // Structured extraction results (JSON string)
        #   "metadata": "object|null",          // Additional crawl metadata
        #   "error_message": "string|null",    // Error description if success=false
        #   "session_id": "string|null",       // Session ID for multi-page crawling
        #   "response_headers": "object|null", // HTTP response headers
        #   "status_code": "number|null",      // HTTP status code
        #   "ssl_certificate": "object|null"   // SSL certificate details
        # }

        task_id = response.json()['task_id']

        # Wait until scraping is complete.
        while True:
            time.sleep(self._config['sleep_time'])
            response = requests.get(
                f"{self._config['crawl4ai_url']}/task/{task_id}",
                headers=headers,
            )

            # TODO: Error handling.
            if response.json()['status'] == 'completed':
                return response.json()

    def scrape_url(self, url):
        # TODO: Validation?
        markdown = self.get_page_code(url)['result']['markdown']

        return {"data": {"markdown": markdown}}

    def batch_scrape_urls(self, urls, params={}):
        # TODO: Validation?
        results = self.get_page_code(urls)['results']

        return {result["url"]: result["markdown"] for result in results}
