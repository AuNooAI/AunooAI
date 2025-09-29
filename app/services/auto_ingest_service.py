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

from app.database import get_database_instance
from app.bulk_research import BulkResearch
from app.relevance import RelevanceCalculator
from app.ai_models import get_ai_model

logger = logging.getLogger(__name__)

@dataclass
class AutoIngestConfig:
    """Configuration for auto-ingest pipeline"""
    enabled: bool = False
    quality_control_enabled: bool = True
    min_relevance_threshold: float = 0.3
    llm_model: str = "gpt-4"
    llm_temperature: float = 0.1
    batch_size: int = 5
    max_concurrent_batches: int = 2

class AutoIngestService:
    """Service for automatic article ingestion from keyword alerts"""

    def __init__(self, db=None):
        self.db = db or get_database_instance()
        self.bulk_research = BulkResearch(self.db)
        self.config = self._load_config()
        self._running = False

    def _load_config(self) -> AutoIngestConfig:
        """Load auto-ingest configuration from database"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT config_value FROM app_config
                    WHERE config_key = 'auto_ingest_settings'
                """)
                result = cursor.fetchone()

                if result:
                    config_data = json.loads(result[0])
                    return AutoIngestConfig(**config_data)
                else:
                    # Return default config
                    return AutoIngestConfig()
        except Exception as e:
            logger.error(f"Failed to load auto-ingest config: {e}")
            return AutoIngestConfig()

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

            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO app_config (config_key, config_value)
                    VALUES ('auto_ingest_settings', ?)
                """, (json.dumps(config_data),))
                conn.commit()

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
            query = """
                SELECT kam.id, kam.article_uri, a.title, a.summary,
                       kam.keyword_ids, kam.detected_at, a.news_source, a.publication_date,
                       kg.topic, kg.name as group_name
                FROM keyword_article_matches kam
                LEFT JOIN articles a ON kam.article_uri = a.uri
                LEFT JOIN keyword_groups kg ON kam.group_id = kg.id
                WHERE (a.uri IS NULL OR a.auto_ingested = 0)  -- Not yet ingested or marked for auto-ingest
                  AND kam.article_uri IS NOT NULL
                  AND kam.article_uri != ''
                  AND kam.is_read = 0  -- Only unread alerts
                ORDER BY kam.detected_at DESC
            """

            if limit:
                query += f" LIMIT {limit}"

            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                rows = cursor.fetchall()

                articles = []
                for row in rows:
                    articles.append({
                        'alert_id': row[0],
                        'url': row[1],
                        'title': row[2] or "No title available",
                        'summary': row[3] or "",
                        'keyword_ids': row[4],
                        'detected_at': row[5],
                        'source': row[6] or "Unknown source",
                        'publication_date': row[7] or "",
                        'topic': row[8] or "general",
                        'group_name': row[9] or "Unknown group"
                    })

                return articles

        except Exception as e:
            logger.error(f"Failed to get pending articles: {e}")
            return []

    async def assess_relevance(self, articles: List[Dict]) -> List[Tuple[Dict, float]]:
        """Assess relevance scores for articles"""
        try:
            relevance_calculator = RelevanceCalculator(self.config.llm_model)
            scored_articles = []

            for article in articles:
                try:
                    # Create article content for relevance assessment
                    article_content = f"Title: {article['title']}\n\n"
                    if article.get('summary'):
                        article_content += f"Summary: {article['summary']}\n\n"
                    article_content += f"Source: {article['source']}"

                    # Get relevance score using the calculator
                    relevance_score = relevance_calculator.calculate_topic_alignment(
                        article_content,
                        article['topic']
                    )

                    scored_articles.append((article, relevance_score))
                    logger.debug(f"Article relevance: {article['title'][:50]}... = {relevance_score:.2f}")

                except Exception as e:
                    logger.error(f"Failed to assess relevance for {article['url']}: {e}")
                    # Default to low relevance if assessment fails
                    scored_articles.append((article, 0.1))

            return scored_articles

        except Exception as e:
            logger.error(f"Failed to assess article relevance: {e}")
            return [(article, 0.1) for article in articles]

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
                (article, score) for article, score in scored_articles
                if score >= self.config.min_relevance_threshold
            ]

            logger.info(f"Found {len(relevant_articles)} articles above relevance threshold ({self.config.min_relevance_threshold})")

            # Step 3: Quality control and ingestion
            for article, relevance_score in relevant_articles:
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
                            'relevance_score': relevance_score
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
                        # Mark the article as auto-ingested before saving
                        analysis_results[0]['auto_ingested'] = True
                        analysis_results[0]['ingest_status'] = 'auto'

                        # Save analyzed article
                        save_results = await self.bulk_research.save_bulk_articles(analysis_results)

                        if save_results['success']:
                            results['ingested'] += 1
                            results['details'].append({
                                'url': article['url'],
                                'title': article['title'],
                                'status': 'ingested',
                                'relevance_score': relevance_score
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
                                'relevance_score': relevance_score
                            })
                    else:
                        results['errors'] += 1
                        error_msg = analysis_results[0].get('error') if analysis_results else 'Analysis failed'
                        results['details'].append({
                            'url': article['url'],
                            'title': article['title'],
                            'status': 'error',
                            'reason': error_msg,
                            'relevance_score': relevance_score
                        })

                except Exception as e:
                    results['errors'] += 1
                    results['details'].append({
                        'url': article['url'],
                        'title': article['title'],
                        'status': 'error',
                        'reason': str(e),
                        'relevance_score': relevance_score
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
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                # Mark the keyword_article_matches as read
                cursor.execute("""
                    UPDATE keyword_article_matches
                    SET is_read = 1
                    WHERE id = ?
                """, (alert_id,))
                conn.commit()
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