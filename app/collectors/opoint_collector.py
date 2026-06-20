import os
import logging
import aiohttp
from typing import Dict, List, Optional
from datetime import datetime, timezone
from .base_collector import ArticleCollector
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class OpointCollector(ArticleCollector):
    """Collector for the Opoint media intelligence API.

    Opoint differs from our other HTTP collectors: it is a POST/JSON API with
    token auth and cursor (``context``) pagination. Its value for AunooAI is the
    per-document entity/topic enrichment (``topics_and_entities`` + ``topics``),
    which carries organizations/people/locations tagged with Wikidata, Crunchbase,
    PermID, LEI and FIGI identifiers — i.e. structured brand & competitor signal.

    That enrichment is license-gated, so we request it and degrade gracefully:
    whatever the token is entitled to is preserved verbatim under the standardized
    ``opoint_entities`` top-level key (the ingest pipeline drops ``raw_data``).

    Docs: https://api-docs.opoint.com/references/search-response
    """

    def __init__(self):
        self.api_key = os.getenv('PROVIDER_OPOINT_API_KEY') or os.getenv('OPOINT_API_KEY')
        if not self.api_key:
            logger.error("Opoint API key not found in environment")
            raise ValueError("Opoint API key not configured")

        # Base URL - configurable for different deployments
        self.base_url = os.getenv('OPOINT_BASE_URL', 'https://api.opoint.com').rstrip('/')
        self.requests_today = 0
        logger.info(f"OpointCollector initialized with base URL: {self.base_url}")

    async def search_articles(
        self,
        query: str,
        topic: str,
        max_results: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        language: str = "en",
        locale: Optional[str] = None,
        domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        sort_by: Optional[str] = None,
        source_ids: Optional[List[str]] = None,
        exclude_source_ids: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        exclude_categories: Optional[List[str]] = None,
        search_fields: Optional[List[str]] = None,
        page: int = 1,
    ) -> List[Dict]:
        """Search articles using the Opoint ``POST /search/`` endpoint.

        Args:
            query: Search term. Opoint supports boolean operators and wildcards;
                it auto-corrects minor syntax errors, so the query is passed through
                largely as-is.
            topic: Topic for categorization (stored on each article).
            max_results: Maximum number of results to return.
            start_date: Optional start date (mapped to the ``oldest`` unix param).
            end_date: Optional end date (mapped to the ``newest`` unix param).
            language: ISO 639-1 language code filter (default "en").
            locale, domains, exclude_domains, sort_by, source_ids,
            exclude_source_ids, categories, exclude_categories, search_fields, page:
                Kept for interface compatibility with other collectors; not used by
                the Opoint /search endpoint.
        """
        try:
            headers = {
                "Authorization": f"Token {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            collected: List[Dict] = []
            context: Optional[str] = None
            # Opoint caps articles per request; loop on the cursor until we have enough.
            per_request_cap = 100

            async with aiohttp.ClientSession() as session:
                while len(collected) < max_results:
                    remaining = max_results - len(collected)
                    params: Dict = {
                        "requestedarticles": min(remaining, per_request_cap),
                        # Ask Opoint to include the enrichment payloads. These are
                        # license-gated; absent fields are simply omitted from the
                        # response, so requesting them is safe.
                        #   textrazor=15 -> topics_and_entities + wikinames (TextRazor
                        #                   entity extraction; requires that add-on)
                        #   allsubject=0 -> topics subject taxonomy (broadly available)
                        "textrazor": 15,
                        "allsubject": "0",
                        "groupidentical": 1,  # surfaces equalgroup (dedup cluster id) per doc; does not collapse results
                        "main": {
                            "header": 1,
                            "summary": 1,
                            "text": 1,
                        },
                        "matchedwords": 0,
                    }

                    if language:
                        params["lang"] = language

                    if start_date is not None:
                        params["oldest"] = self._to_unix(start_date)
                    if end_date is not None:
                        params["newest"] = self._to_unix(end_date)

                    if context:
                        params["context"] = context

                    body = {"searchterm": query, "params": params}

                    async with session.post(
                        f"{self.base_url}/search/",
                        json=body,
                        headers=headers,
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            logger.error(
                                f"Opoint HTTP ERROR: status={response.status} "
                                f"body={error_text[:500]}"
                            )
                            break

                        self.requests_today += 1

                        try:
                            data = await response.json()
                        except Exception as json_error:
                            logger.error(f"Opoint JSON parse error: {json_error}")
                            break

                    search_result = data.get("searchresult", {}) or {}
                    errors = search_result.get("errors")
                    if errors:
                        logger.error(f"Opoint search error: {errors}")
                        break

                    documents = search_result.get("document", []) or []
                    if not documents:
                        break

                    for doc in documents:
                        collected.append(self._format_article(doc, topic))
                        if len(collected) >= max_results:
                            break

                    # Cursor pagination: empty/absent context means no more results.
                    context = search_result.get("context")
                    if not context:
                        break

            logger.info(
                f"Opoint returned {len(collected)} articles for query '{query[:80]}'"
            )
            return collected

        except aiohttp.ClientError as e:
            logger.error(f"Opoint network error: {type(e).__name__}: {e}")
            return []
        except Exception as e:
            logger.error(f"Opoint unexpected error: {type(e).__name__}: {e}")
            return []

    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """Fetch a single article from Opoint by searching for its URL."""
        try:
            headers = {
                "Authorization": f"Token {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            body = {
                "searchterm": url,
                "params": {
                    "requestedarticles": 1,
                    "textrazor": 15,
                    "allsubject": "0",
                    "main": {"header": 1, "summary": 1, "text": 1},
                },
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/search/",
                    json=body,
                    headers=headers,
                ) as response:
                    if response.status != 200:
                        logger.error(f"Opoint fetch_article_content error: {response.status}")
                        return None

                    data = await response.json()

            documents = (data.get("searchresult", {}) or {}).get("document", []) or []
            if not documents:
                logger.warning(f"Opoint returned no articles for URL: {url}")
                return None

            return self._format_article(documents[0], topic="")

        except aiohttp.ClientError as e:
            logger.error(f"Opoint fetch_article_content network error: {e}")
            return None
        except Exception as e:
            logger.error(f"Opoint fetch_article_content error: {e}")
            return None

    @staticmethod
    def _to_unix(value) -> int:
        """Convert a datetime (or ISO string) to unix epoch seconds."""
        if isinstance(value, datetime):
            return int(value.timestamp())
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                return int(dt.timestamp())
            except ValueError:
                return 0
        if isinstance(value, (int, float)):
            return int(value)
        return 0

    @staticmethod
    def _text(field) -> str:
        """Opoint text fields are objects like {"text": "...", "matches": ...}.

        Some are returned as plain strings depending on the endpoint/license, so
        handle both shapes.
        """
        if isinstance(field, dict):
            return (field.get("text") or "").strip()
        if isinstance(field, str):
            return field.strip()
        return ""

    def _format_article(self, doc: Dict, topic: str) -> Dict:
        """Map an Opoint document to AunooAI's standardized article dict."""
        title = self._text(doc.get("header"))
        summary = self._text(doc.get("summary"))
        content = self._text(doc.get("body"))

        url = (doc.get("orig_url") or doc.get("url") or "").strip()

        # Prefer the publisher site name; fall back to the domain.
        first_source = doc.get("first_source") or {}
        source_name = ""
        if isinstance(first_source, dict):
            source_name = (first_source.get("sitename") or first_source.get("name") or "").strip()
        if not source_name:
            source_name = (doc.get("url_common") or "").strip()
        if not source_name and url:
            source_name = urlparse(url).netloc.replace("www.", "")

        # Published date: prefer unix_timestamp -> clean UTC ISO 8601 (Opoint's
        # local_time.text is a non-standard compact format like "20260618T19:57:41+0200"
        # that the downstream TEXT->timestamp casts can't parse reliably).
        published_date = ""
        local_time = doc.get("local_time")
        if doc.get("unix_timestamp"):
            try:
                published_date = datetime.fromtimestamp(
                    int(doc["unix_timestamp"]), tz=timezone.utc
                ).isoformat()
            except (ValueError, TypeError, OSError):
                published_date = ""
        if not published_date and isinstance(local_time, dict) and local_time.get("text"):
            published_date = local_time["text"]

        author = doc.get("author")
        authors = [author] if author and isinstance(author, str) else []

        language = doc.get("language")
        language_text = language.get("text") if isinstance(language, dict) else language

        identical = doc.get("identical_documents") or {}
        identical_count = identical.get("cnt") if isinstance(identical, dict) else None

        # The brand/competitor payload. License-gated fields are simply absent when
        # the token is not entitled — we store whatever is present.
        #   topics_and_entities/wikinames -> require the TextRazor add-on
        #   topics                         -> Opoint subject taxonomy (allsubject)
        #   similarweb/site_rank           -> reach/readership (useful brand signal)
        opoint_entities = {
            "entities": doc.get("topics_and_entities"),
            "topics": doc.get("topics"),
            "wikinames": doc.get("wikinames"),
            "wikidescriptions": doc.get("wikidescriptions"),
            "similarweb": doc.get("similarweb"),
            "site_rank": doc.get("site_rank"),
            "countryname": doc.get("countryname"),
            "countrycode": doc.get("countrycode"),
            "language": language_text,
            "id_article": doc.get("id_article"),
            "id_site": doc.get("id_site"),
            "identical_count": identical_count,
            # equalgroup = Opoint dedup-cluster id; articles sharing it are
            # republications of the same story (identical_documents is null in this
            # license tier, so equalgroup is the available pickup/dedup signal).
            "equalgroup": doc.get("equalgroup"),
            # mediatype.text = WEB / PRINT / TV / RADIO (channel, not journal-vs-news).
            "media_type": (doc.get("mediatype") or {}).get("text") if isinstance(doc.get("mediatype"), dict) else None,
        }

        return {
            "title": title,
            "summary": summary,
            "content": content,  # Opoint provides body text - avoids re-scraping
            "authors": authors,
            "published_date": published_date,
            "url": url,
            "source": source_name,
            "topic": topic,
            # Top-level (not raw_data) because the ingest pipeline persists this
            # via the new articles.opoint_entities column.
            "opoint_entities": opoint_entities,
            "raw_data": {
                "first_source": first_source,
                "sources": doc.get("sources"),
                "language": language,
                "countryname": doc.get("countryname"),
                "countrycode": doc.get("countrycode"),
                "word_count": doc.get("word_count"),
                "articleimages": doc.get("articleimages"),
                "mediatype": doc.get("mediatype"),
                "topics": doc.get("topics"),
                "topics_and_entities": doc.get("topics_and_entities"),
            },
        }
