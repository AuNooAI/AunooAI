"""Fakes shared by the collector data-quality ingest tests. No database,
no network, no model: the service object is built without __init__ and
every collaborator that would touch the outside is replaced."""
import logging
from typing import Any, Dict, List, Optional

from app.services.automated_ingest_service import AutomatedIngestService


class FakeFacade:
    def __init__(self):
        self.below_threshold: List[str] = []
        self.keywords_by_topic: Dict[str, List[str]] = {}

    def mark_article_as_below_threshold(self, uri):
        self.below_threshold.append(uri)

    def get_monitored_keywords_for_topic(self, params):
        return self.keywords_by_topic.get(params[0], [])


class FakeDb:
    def __init__(self):
        self.facade = FakeFacade()

    def _temp_get_connection(self):  # the ledger is always faked; never reached
        raise AssertionError("tests must not open a database connection")


class FakeAsyncDb:
    def __init__(self):
        self.saved_below: List[Dict[str, Any]] = []
        self.updated: List[Dict[str, Any]] = []
        self.raw_saved: List[str] = []
        self.group_relevance: List[tuple] = []

    async def save_below_threshold_article(self, article):
        self.saved_below.append(dict(article))
        return True

    async def record_group_relevance(self, uri, topic, score, status):
        self.group_relevance.append((uri, topic, score, status))
        return True

    async def update_article_with_enrichment(self, article):
        self.updated.append(dict(article))
        return True

    async def save_raw_article_async(self, uri, content, topic):
        self.raw_saved.append(uri)

    async def get_raw_article_async(self, uri):
        return None


class FakeResearch:
    def __init__(self, topic_configs, firecrawl_app=None):
        self.topic_configs = topic_configs
        self.firecrawl_app = firecrawl_app
        self.reloads = 0

    def load_config(self):
        self.reloads += 1


class FakeLedger:
    """Stands in for RejectedCandidateLedger. ``hits`` is what lookup returns."""
    instances: List["FakeLedger"] = []

    def __init__(self, db, hits=None):
        self.db = db
        self.hits = hits or {}
        self.lookups: List[tuple] = []
        self.records: List[tuple] = []
        self.forgotten: List[str] = []
        FakeLedger.instances.append(self)

    def lookup(self, urls, group_id, version):
        self.lookups.append((list(urls), group_id, version))
        return dict(self.hits)

    def record(self, url, group_id, version, *, score, threshold):
        self.records.append((url, group_id, version, score, threshold))

    def forget(self, url, group_id=None):
        self.forgotten.append(url)
        return 1


def make_service(topic_configs: Optional[Dict[str, Dict[str, Any]]] = None, *,
                 score: float = 0.1, threshold: float = 0.5, firecrawl_app=None) -> AutomatedIngestService:
    svc = AutomatedIngestService.__new__(AutomatedIngestService)
    svc.db = FakeDb()
    svc.async_db = FakeAsyncDb()
    svc.config = {}
    svc.logger = logging.getLogger("test.ingest")
    svc._research_cache = {}
    svc._last_extraction_outcomes = {}
    svc.article_analyzer = None
    svc.hybrid_relevance_service = None
    svc.enrichment_service = None
    svc.hybrid_enrichment_service = None
    svc.relevance_calculator = None
    svc.use_adaptive_enrichment = False
    svc._blocking_executor = None
    svc.media_bias = None

    research = FakeResearch(topic_configs if topic_configs is not None else {}, firecrawl_app=firecrawl_app)
    svc._research = research
    svc._get_research = lambda model_name=None: research
    svc.get_llm_client = lambda model_override=None: "fake-model"
    svc.get_relevance_threshold = lambda topic=None: threshold

    svc.score_calls: List[str] = []
    svc.analyze_calls: List[str] = []

    async def _score(article, topic, keywords):
        svc.score_calls.append(article.get("uri"))
        return {"relevance_score": score, "topic_alignment_score": score,
                "keyword_relevance_score": score, "confidence_score": score,
                "overall_match_explanation": "fake"}

    async def _bias(article):
        return article

    async def _analyze(article, topic):
        svc.analyze_calls.append(article.get("uri"))
        article.update({"analyzed": True, "category": "C", "sentiment": "Neutral",
                        "future_signal": "F", "summary": article.get("summary") or "s"})
        return article

    async def _vector(article, raw_content=None):
        return None

    async def _scrape_batch(uris, topic=None):
        return {}

    svc._score_article_relevance_async = _score
    svc._enrich_article_with_bias_async = _bias
    svc._analyze_article_content_async = _analyze
    svc._upsert_to_vector_db_async = _vector
    svc.scrape_articles_batch = _scrape_batch
    return svc


def full_topic(name="T"):
    return {"name": name, "categories": ["A"], "future_signals": ["S"], "sentiment": ["Neutral"],
            "time_to_impact": ["Short"], "driver_types": ["Tech"]}


def article(uri, topic="T", summary="Some body text long enough."):
    return {"uri": uri, "title": "Title " + uri, "news_source": "src", "publication_date": "2026-09-30",
            "summary": summary, "topic": topic, "analyzed": False}
