"""
Auto-Ingest Service for automatically processing keyword alert articles.
Handles relevance scoring, quality control, and automatic ingestion.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import json
from pathlib import Path

from app.database import get_database_instance
from app.bulk_research import BulkResearch
from app.relevance import RelevanceCalculator
from app.ai_models import get_ai_model

logger = logging.getLogger(__name__)

@dataclass
class AutoIngestConfig:
    """Configuration for auto-ingest pipeline"""
    enabled: bool = True
    quality_control_enabled: bool = True
    min_relevance_threshold: float = 0.3
    llm_model: str = "gpt-4.1-mini"
    llm_temperature: float = 0.7
    batch_size: int = 5
    max_concurrent_batches: int = 2

class AutoIngestService:
    """Service for automatic article ingestion from keyword alerts"""

    def __init__(self, db=None):
        self.db = db or get_database_instance()
        self.bulk_research = BulkResearch(self.db)
        self.config = self._load_config()
        self._running = False
        self._topics_config = None  # Cache for topic configuration

    def _load_config(self) -> AutoIngestConfig:
        """Load auto-ingest configuration from database"""
        try:
            from sqlalchemy import select
            from app.database_models import app_config

            statement = select(app_config.c.config_value).where(
                app_config.c.config_key == 'auto_ingest_settings'
            )
            result = self.db.connection.execute(statement).scalar()

            if result:
                config_data = json.loads(result)
                return AutoIngestConfig(**config_data)
            else:
                # Return default config
                return AutoIngestConfig()
        except Exception as e:
            logger.error(f"Failed to load auto-ingest config: {e}")
            return AutoIngestConfig()

    def _load_topics_config(self) -> Dict:
        """Load topics configuration from config.json"""
        if self._topics_config is not None:
            return self._topics_config

        try:
            config_path = Path(__file__).parent.parent / 'config' / 'config.json'
            with open(config_path, 'r') as f:
                config_data = json.load(f)

            # Create a lookup dictionary by topic name
            topics_lookup = {}
            for topic in config_data.get('topics', []):
                topics_lookup[topic['name']] = topic

            self._topics_config = topics_lookup
            logger.info(f"Loaded configuration for {len(topics_lookup)} topics")
            return self._topics_config

        except Exception as e:
            logger.error(f"Failed to load topics config: {e}")
            return {}

    def _get_topic_description(self, topic_name: str) -> Optional[str]:
        """Get formatted topic description with categories for LLM context"""
        topics_config = self._load_topics_config()

        topic_config = topics_config.get(topic_name)
        if not topic_config:
            logger.warning(f"No configuration found for topic: {topic_name}")
            return None

        # Format topic description with categories for LLM
        description = topic_config.get('description', '')
        categories = topic_config.get('categories', [])

        if categories:
            categories_list = '\n'.join([f"  - {cat}" for cat in categories])
            full_description = f"{description}\n\nCategories:\n{categories_list}"
        else:
            full_description = description

        return full_description

    def save_config(self, config: AutoIngestConfig) -> bool:
        """Save auto-ingest configuration to database"""
        try:
            config_data = {
                'enabled': config.enabled,
                'quality_control_enabled': config.quality_control_enabled,
                'min_relevance_threshold': config.min_relevance_threshold,
                'llm_model': config.llm_model,
                'llm_temperature': config.llm_temperature,
                'batch_size': config.batch_size,
                'max_concurrent_batches': config.max_concurrent_batches
            }

            from sqlalchemy import insert
            from app.database_models import app_config

            statement = insert(app_config).values(
                config_key='auto_ingest_settings',
                config_value=json.dumps(config_data)
            ).prefix_with('OR REPLACE', dialect='sqlite').on_conflict_do_update(
                index_elements=['config_key'],
                set_={'config_value': json.dumps(config_data)}
            )

            self.db.connection.execute(statement)
            self.db.connection.commit()

            self.config = config
            logger.info("Auto-ingest configuration saved")
            return True

        except Exception as e:
            logger.error(f"Failed to save auto-ingest config: {e}")
            return False

    def get_config(self) -> Dict:
        """Get current configuration as dictionary"""
        return {
            'enabled': self.config.enabled,
            'quality_control_enabled': self.config.quality_control_enabled,
            'min_relevance_threshold': self.config.min_relevance_threshold,
            'llm_model': self.config.llm_model,
            'llm_temperature': self.config.llm_temperature,
            'batch_size': self.config.batch_size,
            'max_concurrent_batches': self.config.max_concurrent_batches
        }

    def update_config(self, updates: Dict) -> bool:
        """Update configuration with partial updates"""
        try:
            # Create new config with updates
            current_dict = self.get_config()
            current_dict.update(updates)
            new_config = AutoIngestConfig(**current_dict)

            return self.save_config(new_config)
        except Exception as e:
            logger.error(f"Failed to update auto-ingest config: {e}")
            return False

    async def get_pending_articles(self, limit: int = None) -> List[Dict]:
        """Get unprocessed keyword alert articles eligible for auto-ingest"""
        try:
            from sqlalchemy import select, or_, and_
            from app.database_models import keyword_article_matches, articles, keyword_groups

            # Build the query using SQLAlchemy Core
            statement = select(
                keyword_article_matches.c.id,
                keyword_article_matches.c.article_uri,
                articles.c.title,
                articles.c.summary,
                keyword_article_matches.c.keyword_ids,
                keyword_article_matches.c.detected_at,
                articles.c.news_source,
                articles.c.publication_date,
                keyword_groups.c.topic,
                keyword_groups.c.name.label('group_name')
            ).select_from(
                keyword_article_matches
                .outerjoin(articles, keyword_article_matches.c.article_uri == articles.c.uri)
                .outerjoin(keyword_groups, keyword_article_matches.c.group_id == keyword_groups.c.id)
            ).where(
                and_(
                    or_(
                        articles.c.uri.is_(None),
                        articles.c.auto_ingested == False
                    ),
                    keyword_article_matches.c.article_uri.isnot(None),
                    keyword_article_matches.c.article_uri != '',
                    keyword_article_matches.c.is_read == False
                )
            ).order_by(
                keyword_article_matches.c.detected_at.desc()
            )

            if limit:
                statement = statement.limit(limit)

            # Execute using database facade connection
            rows = self.db.connection.execute(statement).mappings().fetchall()

            articles = []
            for row in rows:
                articles.append({
                    'alert_id': row['id'],
                    'url': row['article_uri'],
                    'title': row['title'] or "No title available",
                    'summary': row['summary'] or "",
                    'keyword_ids': row['keyword_ids'],
                    'detected_at': row['detected_at'],
                    'source': row['news_source'] or "Unknown source",
                    'publication_date': row['publication_date'] or "",
                    'topic': row['topic'] or "general",
                    'group_name': row['group_name'] or "Unknown group"
                })

            return articles

        except Exception as e:
            logger.error(f"Failed to get pending articles: {e}")
            return []

    async def assess_relevance(self, articles: List[Dict]) -> List[Tuple[Dict, Dict]]:
        """Assess relevance scores for articles using full topic ontology

        Returns: List of tuples (article, relevance_data) where relevance_data contains:
            - topic_alignment_score: float
            - keyword_relevance_score: float (optional)
            - confidence_score: float (optional)
        """
        try:
            relevance_calculator = RelevanceCalculator(self.config.llm_model)
            scored_articles = []

            for article in articles:
                try:
                    # Get topic description with categories from config.json
                    topic_name = article['topic']
                    topic_description = self._get_topic_description(topic_name)

                    if not topic_description:
                        logger.warning(f"No topic description for '{topic_name}', using legacy method")
                        # Fallback to legacy method if topic config not found
                        article_content = f"Title: {article['title']}\n\n"
                        if article.get('summary'):
                            article_content += f"Summary: {article['summary']}\n\n"
                        article_content += f"Source: {article['source']}"

                        relevance_score = relevance_calculator.calculate_topic_alignment(
                            article_content,
                            topic_name
                        )
                        relevance_data = {'topic_alignment_score': relevance_score}
                    else:
                        # Use full analyze_relevance method with topic ontology
                        analysis_result = relevance_calculator.analyze_relevance(
                            title=article['title'],
                            source=article['source'],
                            content=article.get('summary', ''),
                            topic=topic_name,
                            keywords=article.get('keyword_ids', ''),
                            topic_description=topic_description
                        )

                        # Extract all relevance scores from the analysis result
                        relevance_data = {
                            'topic_alignment_score': analysis_result.get('topic_alignment_score', 0.0),
                            'keyword_relevance_score': analysis_result.get('keyword_relevance_score'),
                            'confidence_score': analysis_result.get('confidence_score'),
                        }

                        logger.debug(f"Article relevance with ontology: {article['title'][:50]}... = {relevance_data['topic_alignment_score']:.2f}")
                        logger.debug(f"  Topic: {topic_name}")
                        logger.debug(f"  Category: {analysis_result.get('category', 'Unknown')}")
                        logger.debug(f"  Keyword relevance: {relevance_data.get('keyword_relevance_score')}")
                        logger.debug(f"  Confidence: {relevance_data.get('confidence_score')}")

                    scored_articles.append((article, relevance_data))

                except Exception as e:
                    logger.error(f"Failed to assess relevance for {article['url']}: {e}")
                    # Default to low relevance if assessment fails
                    scored_articles.append((article, {'topic_alignment_score': 0.1}))

            return scored_articles

        except Exception as e:
            logger.error(f"Failed to assess article relevance: {e}")
            return [(article, {'topic_alignment_score': 0.1}) for article in articles]

    async def quality_control_check(self, article: Dict) -> Tuple[bool, str]:
        """Perform quality control check on article"""
        if not self.config.quality_control_enabled:
            return True, "Quality control disabled"

        try:
            ai_model = get_ai_model(self.config.llm_model)

            prompt = f"""
            Please assess this article for quality and suitability for inclusion in a professional research database.

            Title: {article['title']}
            Source: {article['source']}
            Summary: {article.get('summary', 'No summary available')}
            URL: {article['url']}

            Evaluate the article on these criteria:
            1. Factual accuracy and credibility
            2. Source reliability
            3. Content quality and depth
            4. Relevance to topic: {article['topic']}
            5. Professional/academic value

            Respond with ONLY:
            - "APPROVED" if the article meets quality standards
            - "REJECTED: [reason]" if it should be rejected

            Consider rejecting articles that are:
            - Clickbait or sensationalized
            - From unreliable sources
            - Duplicate or low-value content
            - Off-topic or irrelevant
            """

            response = await ai_model.generate_response(prompt, temperature=self.config.llm_temperature)

            if response.startswith("APPROVED"):
                return True, "Passed quality control"
            else:
                reason = response.replace("REJECTED:", "").strip()
                return False, reason

        except Exception as e:
            logger.error(f"Quality control check failed: {e}")
            # Default to approved if check fails
            return True, f"Quality control failed: {e}"

    async def process_articles_batch(self, articles: List[Dict]) -> Dict:
        """Process a batch of articles through the auto-ingest pipeline"""
        results = {
            'processed': 0,
            'ingested': 0,
            'rejected_relevance': 0,
            'rejected_quality': 0,
            'errors': 0,
            'details': []
        }

        try:
            # Step 1: Assess relevance
            logger.info(f"Assessing relevance for {len(articles)} articles")
            scored_articles = await self.assess_relevance(articles)

            # Step 2: Filter by relevance threshold
            relevant_articles = [
                (article, relevance_data) for article, relevance_data in scored_articles
                if relevance_data.get('topic_alignment_score', 0.0) >= self.config.min_relevance_threshold
            ]

            logger.info(f"Found {len(relevant_articles)} articles above relevance threshold ({self.config.min_relevance_threshold})")

            # Step 3: Quality control and ingestion
            for article, relevance_data in relevant_articles:
                try:
                    results['processed'] += 1

                    # Quality control check
                    passed_qc, qc_reason = await self.quality_control_check(article)

                    if not passed_qc:
                        results['rejected_quality'] += 1
                        results['details'].append({
                            'url': article['url'],
                            'title': article['title'],
                            'status': 'rejected_quality',
                            'reason': qc_reason,
                            'relevance_score': relevance_data.get('topic_alignment_score', 0.0)
                        })
                        continue

                    # Analyze and ingest article
                    analysis_results = await self.bulk_research.analyze_bulk_urls(
                        urls=[article['url']],
                        topic=article['topic'],
                        summary_type='curious_ai',
                        model_name=self.config.llm_model,
                        summary_length=50,
                        summary_voice='neutral'
                    )

                    if analysis_results and not analysis_results[0].get('error'):
                        # Mark the article as auto-ingested and add all relevance scores before saving
                        analysis_results[0]['auto_ingested'] = True
                        analysis_results[0]['ingest_status'] = 'auto'
                        analysis_results[0]['topic_alignment_score'] = relevance_data.get('topic_alignment_score')
                        analysis_results[0]['keyword_relevance_score'] = relevance_data.get('keyword_relevance_score')
                        analysis_results[0]['confidence_score'] = relevance_data.get('confidence_score')

                        # Save analyzed article
                        save_results = await self.bulk_research.save_bulk_articles(analysis_results)

                        if save_results['success']:
                            results['ingested'] += 1
                            results['details'].append({
                                'url': article['url'],
                                'title': article['title'],
                                'status': 'ingested',
                                'relevance_score': relevance_data.get('topic_alignment_score', 0.0)
                            })

                            # Mark alert as processed
                            await self._mark_alert_processed(article['alert_id'])

                        else:
                            results['errors'] += 1
                            results['details'].append({
                                'url': article['url'],
                                'title': article['title'],
                                'status': 'error',
                                'reason': 'Failed to save article',
                                'relevance_score': relevance_data.get('topic_alignment_score', 0.0)
                            })
                    else:
                        results['errors'] += 1
                        error_msg = analysis_results[0].get('error') if analysis_results else 'Analysis failed'
                        results['details'].append({
                            'url': article['url'],
                            'title': article['title'],
                            'status': 'error',
                            'reason': error_msg,
                            'relevance_score': relevance_data.get('topic_alignment_score', 0.0)
                        })

                except Exception as e:
                    results['errors'] += 1
                    results['details'].append({
                        'url': article['url'],
                        'title': article['title'],
                        'status': 'error',
                        'reason': str(e),
                        'relevance_score': relevance_data.get('topic_alignment_score', 0.0)
                    })

            # Count relevance rejections
            results['rejected_relevance'] = len(scored_articles) - len(relevant_articles)

            return results

        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            return results

    async def _mark_alert_processed(self, alert_id: int):
        """Mark a keyword alert as processed"""
        try:
            from sqlalchemy import update
            from app.database_models import keyword_article_matches

            statement = update(keyword_article_matches).where(
                keyword_article_matches.c.id == alert_id
            ).values(is_read=True)

            self.db.connection.execute(statement)
            self.db.connection.commit()
        except Exception as e:
            logger.error(f"Failed to mark alert {alert_id} as processed: {e}")

    async def run_auto_ingest(self) -> Dict:
        """Run the auto-ingest pipeline"""
        if not self.config.enabled:
            return {"success": False, "message": "Auto-ingest is disabled"}

        if self._running:
            return {"success": False, "message": "Auto-ingest is already running"}

        self._running = True
        start_time = datetime.now()

        try:
            logger.info("Starting auto-ingest pipeline")

            # Get pending articles
            pending_articles = await self.get_pending_articles(limit=50)

            if not pending_articles:
                logger.info("No pending articles for auto-ingest")
                return {
                    "success": True,
                    "message": "No pending articles",
                    "processed": 0,
                    "ingested": 0
                }

            logger.info(f"Found {len(pending_articles)} pending articles")

            # Process in batches
            total_results = {
                'processed': 0,
                'ingested': 0,
                'rejected_relevance': 0,
                'rejected_quality': 0,
                'errors': 0,
                'details': []
            }

            for i in range(0, len(pending_articles), self.config.batch_size):
                batch = pending_articles[i:i + self.config.batch_size]
                logger.info(f"Processing batch {i // self.config.batch_size + 1} ({len(batch)} articles)")

                batch_results = await self.process_articles_batch(batch)

                # Aggregate results
                for key in ['processed', 'ingested', 'rejected_relevance', 'rejected_quality', 'errors']:
                    total_results[key] += batch_results[key]
                total_results['details'].extend(batch_results['details'])

                # Brief pause between batches
                await asyncio.sleep(1)

            duration = (datetime.now() - start_time).total_seconds()

            logger.info(f"Auto-ingest completed in {duration:.1f}s: "
                       f"{total_results['ingested']} ingested, "
                       f"{total_results['rejected_relevance']} rejected (relevance), "
                       f"{total_results['rejected_quality']} rejected (quality), "
                       f"{total_results['errors']} errors")

            return {
                "success": True,
                "duration_seconds": duration,
                **total_results
            }

        except Exception as e:
            logger.error(f"Auto-ingest pipeline failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "duration_seconds": (datetime.now() - start_time).total_seconds()
            }
        finally:
            self._running = False

    def is_running(self) -> bool:
        """Check if auto-ingest is currently running"""
        return self._running

    def get_status(self) -> Dict:
        """Get current auto-ingest status"""
        return {
            "enabled": self.config.enabled,
            "running": self._running,
            "config": self.get_config()
        }

# Global service instance
_auto_ingest_service: Optional[AutoIngestService] = None

def get_auto_ingest_service() -> AutoIngestService:
    """Get or create the global auto-ingest service"""
    global _auto_ingest_service
    if _auto_ingest_service is None:
        _auto_ingest_service = AutoIngestService()
    return _auto_ingest_service