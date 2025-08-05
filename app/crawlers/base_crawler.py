from abc import ABC, abstractmethod
from typing import Dict

class BaseCrawler:
    """And abstract base class for web page crawlers."""
    _instance = None
    _logger = None
    _config = {}

    def __init__(self):
        raise RuntimeError('Call instance() instead')

    @classmethod
    def instance(cls, logger, config : Dict):
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            cls._logger = logger
            cls._config = config
            cls.initialize(cls._instance)
        return cls._instance

    @abstractmethod
    def initialize(self):
        pass

    @abstractmethod
    def batch_scrape_urls(self, urls, params={}):
        pass

    @abstractmethod
    def scrape_url(self, url):
        pass