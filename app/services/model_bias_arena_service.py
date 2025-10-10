#!/usr/bin/env python3
"""Model Bias Arena Service - Monitor and compare model bias across different AI models."""

import json
import logging
import time
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from statistics import mean, stdev
import sqlite3

from app.database import Database, get_database_instance
from app.database_query_facade import DatabaseQueryFacade
from app.ai_models import LiteLLMModel, get_available_models
from app.analyzers.prompt_manager import PromptManager

logger = logging.getLogger(__name__)


class ModelBiasArenaService:
    """Service for running model bias evaluation arenas."""
    
    def __init__(self, db: Database = None):
        self.db = db or get_database_instance()
        self.prompt_manager = PromptManager()
        
        # Initialize migration if needed
        self._ensure_tables_exist()
    
    def _ensure_tables_exist(self):
        """Ensure bias arena tables exist in the database."""
        try:
            migration_path = "app/database/migrations/create_model_bias_arena_table.sql"
            with open(migration_path, 'r') as f:
                migration_sql = f.read()
            
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.executescript(migration_sql)
                conn.commit()
                
        except Exception as e:
            logger.warning(f"Could not run bias arena migration: {e}")
    
    def get_available_models(self) -> List[Dict[str, Any]]:
        """Get list of available configured models."""
        try:
            models = get_available_models()
            return [
                {
                    "name": model["name"],
                    "provider": model.get("provider", "unknown"),
                    "display_name": f"{model['name']} ({model.get('provider', 'unknown')})"
                }
                for model in models
            ]
        except Exception as e:
            logger.error(f"Error getting available models: {e}")
            return []
    
    def sample_articles(self, count: int = 25, topic: Optional[str] = None) -> List[Dict[str, Any]]:
        """Sample articles that have complete benchmark ontological data."""
        try:
            articles = []

            for row in (DatabaseQueryFacade(self.db, logger)).sample_articles(count, topic):
                articles.append({
                    "uri": row['uri'],
                    "title": row['title'],
                    "summary": row['summary'],
                    "news_source": row['news_source'],
                    "topic": row['topic'],
                    "category": row['category'],
                    # Include benchmark values for reference
                    "benchmark_sentiment": row['sentiment'],
                    "benchmark_future_signal": row['future_signal'],
                    "benchmark_time_to_impact": row['time_to_impact'],
                    "benchmark_driver_type": row['driver_type'],
                    # Store source bias data for post-analysis validation (NOT used in analysis prompts)
                    "source_bias": row['bias'],
                    "source_factual_reporting": row['factual_reporting'],
                    "source_credibility": row['mbfc_credibility_rating'],
                    "source_country": row['bias_country']
                })

            logger.info(f"Sampled {len(articles)} articles with complete benchmark ontological data")
            if len(articles) == 0:
                logger.warning("No articles found with complete benchmark data. Make sure you have analyzed articles with ontological fields.")

            return articles
                
        except Exception as e:
            logger.error(f"Error sampling articles: {e}")
            return []
    
    def create_bias_evaluation_run(self, 
                                 name: str,
                                 description: str,
                                 benchmark_model: str,
                                 selected_models: List[str],
                                 article_count: int = 25,
                                 rounds: int = 1,
                                 topic: Optional[str] = None) -> int:
        """Create a new bias evaluation run."""
        try:
            # Sample articles
            articles = self.sample_articles(count=article_count, topic=topic)
            if not articles:
                raise ValueError("No articles found to sample")

            run_id = (DatabaseQueryFacade(self.db, logger)).create_model_bias_arena_runs((name, description, benchmark_model, json.dumps(selected_models), len(articles), rounds, 1))

            # Add articles to the run
            for article in articles:
                (DatabaseQueryFacade(self.db, logger)).add_articles_to_run((run_id, article["uri"], article["title"], article["summary"]))

            return run_id
                
        except Exception as e:
            logger.error(f"Error creating bias evaluation run: {e}")
            raise
    
    async def evaluate_model_ontology(self, run_id: int) -> Dict[str, Any]:
        """Run ontological field evaluation for all models in a run using ArticleAnalyzer."""
        try:
            # Get run details
            run_details = self.get_run_details(run_id)
            if not run_details:
                raise ValueError(f"Run {run_id} not found")
            
            models = json.loads(run_details["selected_models"])
            benchmark_model = run_details["benchmark_model"]
            
            # Get rounds info - need to update query to include new fields
            round_info = (DatabaseQueryFacade(self.db, logger)).get_run_info(run_id)
            if not round_info:
                raise ValueError(f"Run {run_id} not found")
            total_rounds, current_round = round_info
            
            # Get articles for this run
            articles = self.get_run_articles(run_id)
            
            # Import ArticleAnalyzer from research.py approach
            from app.analyzers.article_analyzer import ArticleAnalyzer
            from app.ai_models import LiteLLMModel
            
            # Load ontology configuration
            from app.config.config import load_config
            config = load_config()
            topic_configs = {topic['name']: topic for topic in config['topics']}
            
            # Find the appropriate topic config from sampled articles
            topic_config = None
            if articles:
                try:
                    row = (DatabaseQueryFacade(self.db, logger)).get_topics_from_article(articles[0]["article_uri"],)
                    if row and row[0] and row[0] in topic_configs:
                        topic_config = topic_configs[row[0]]
                        logger.info(f"Using topic config for: {row[0]}")
                except Exception as e:
                    logger.warning(f"Could not determine topic from articles: {e}")
            
            # Fallback to first available topic if none found
            if not topic_config and topic_configs:
                topic_config = next(iter(topic_configs.values()))
                logger.info(f"Using fallback topic config: {topic_config.get('name', 'Unknown')}")
            
            # Extract ontology values or use defaults
            if topic_config:
                categories = topic_config.get('categories', ["Technology", "Business", "Politics", "Science", "Health", "Other"])
                future_signals = topic_config.get('future_signals', ["Strong", "Moderate", "Weak", "None"])
                sentiment_options = topic_config.get('sentiment', ["Positive", "Negative", "Neutral", "Mixed"])
                time_to_impact_options = topic_config.get('time_to_impact', ["Immediate", "Short-term", "Medium-term", "Long-term", "Uncertain"])
                driver_types = topic_config.get('driver_types', ["Technological", "Economic", "Social", "Political", "Environmental", "Regulatory"])
            else:
                # Final fallback defaults
                categories = ["Technology", "Business", "Politics", "Science", "Health", "Other"]
                future_signals = ["Strong", "Moderate", "Weak", "None"]
                sentiment_options = ["Positive", "Negative", "Neutral", "Mixed"]
                time_to_impact_options = ["Immediate", "Short-term", "Medium-term", "Long-term", "Uncertain"]
                driver_types = ["Technological", "Economic", "Social", "Political", "Environmental", "Regulatory"]
            
            logger.info(f"Using ontology: categories={categories}, future_signals={future_signals}, driver_types={driver_types}")
            
            all_results = {}
            all_models = [benchmark_model] + [m for m in models if m != benchmark_model]
            
            # Run evaluation for each round
            for round_num in range(current_round, total_rounds + 1):
                logger.info(f"Starting Round {round_num} of {total_rounds}")
                
                # Update current round in database
                (DatabaseQueryFacade(self.db, logger)).update_run((round_num, run_id))
                round_results = {}
                
                # Evaluate each model for this round
                for model_name in all_models:
                    logger.info(f"Round {round_num}: Evaluating model {model_name}")
                    model_results = []
                    
                    try:
                        # Create AI model instance and ArticleAnalyzer 
                        ai_model = LiteLLMModel.get_instance(model_name)
                        article_analyzer = ArticleAnalyzer(ai_model, use_cache=False)  # No cache for comparison
                        
                        for article in articles:
                            start_time = time.time()
                            
                            try:
                                # Extract source from URI if news_source is empty
                                source = article.get("news_source", "").strip()
                                if not source:
                                    from urllib.parse import urlparse
                                    parsed_uri = urlparse(article["article_uri"])
                                    source = parsed_uri.netloc or "Unknown Source"
                                
                                # Use ArticleAnalyzer like in research.py
                                parsed_analysis = article_analyzer.analyze_content(
                                    article_text=article["article_summary"],
                                    title=article["article_title"],
                                    source=source,
                                    uri=article["article_uri"],
                                    summary_length=50,
                                    summary_voice="neutral",
                                    summary_type="brief",
                                    categories=categories,
                                    future_signals=future_signals,
                                    sentiment_options=sentiment_options,
                                    time_to_impact_options=time_to_impact_options,
                                    driver_types=driver_types
                                )
                                
                                response_time = int((time.time() - start_time) * 1000)
                                
                                # Extract ontological fields
                                extracted_fields = {
                                    "sentiment": parsed_analysis.get("sentiment", ""),
                                    "sentiment_explanation": parsed_analysis.get("sentiment_explanation", ""),
                                    "future_signal": parsed_analysis.get("future_signal", ""),
                                    "future_signal_explanation": parsed_analysis.get("future_signal_explanation", ""),
                                    "time_to_impact": parsed_analysis.get("time_to_impact", ""),
                                    "time_to_impact_explanation": parsed_analysis.get("time_to_impact_explanation", ""),
                                    "driver_type": parsed_analysis.get("driver_type", ""),
                                    "driver_type_explanation": parsed_analysis.get("driver_type_explanation", ""),
                                    "category": parsed_analysis.get("category", ""),
                                    "category_explanation": parsed_analysis.get("category_explanation", ""),
                                    "political_bias": parsed_analysis.get("political_bias", ""),
                                    "political_bias_explanation": parsed_analysis.get("political_bias_explanation", ""),
                                    "factuality": parsed_analysis.get("factuality", ""),
                                    "factuality_explanation": parsed_analysis.get("factuality_explanation", "")
                                }
                                
                                # Store result with round number
                                self._store_ontological_result(
                                    run_id=run_id,
                                    article_uri=article["article_uri"],
                                    model_name=model_name,
                                    response_text=str(parsed_analysis),
                                    extracted_fields=extracted_fields,
                                    response_time_ms=response_time,
                                    round_number=round_num
                                )
                                
                                result_data = {
                                    "article_uri": article["article_uri"],
                                    "response_time_ms": response_time,
                                    "round": round_num,
                                    **extracted_fields
                                }
                                model_results.append(result_data)
                                
                            except Exception as e:
                                logger.error(f"Round {round_num}: Error evaluating article {article['article_uri']} with {model_name}: {e}")
                                # Store error result
                                self._store_evaluation_result(
                                    run_id=run_id,
                                    article_uri=article["article_uri"],
                                    model_name=model_name,
                                    error_message=str(e)
                                )
                        
                        round_results[model_name] = model_results
                        
                    except Exception as e:
                        logger.error(f"Round {round_num}: Error initializing model {model_name}: {e}")
                        round_results[model_name] = {"error": str(e)}
                
                all_results[f"round_{round_num}"] = round_results
                logger.info(f"Completed Round {round_num} of {total_rounds}")
            
            # Mark run as completed
            self._update_run_status(run_id, "completed")
            
            logger.info(f"All {total_rounds} rounds completed for run {run_id}")
            return all_results
            
        except Exception as e:
            logger.error(f"Error running ontological evaluation: {e}")
            self._update_run_status(run_id, "failed")
            raise
    
    def _store_evaluation_result(self, 
                               run_id: int,
                               article_uri: str,
                               model_name: str,
                               response_text: str = None,
                               bias_score: float = None,
                               confidence_score: float = None,
                               response_time_ms: int = None,
                               error_message: str = None):
        """Store evaluation result in database."""
        try:
            (DatabaseQueryFacade(self.db, logger)).store_evaluation_results((run_id, article_uri, model_name, response_text, bias_score, confidence_score, response_time_ms, error_message))
        except Exception as e:
            logger.error(f"Error storing evaluation result: {e}")
    
    def _store_ontological_result(self,
                                run_id: int,
                                article_uri: str,
                                model_name: str,
                                response_text: str,
                                extracted_fields: Dict[str, Any],
                                response_time_ms: int,
                                round_number: int = 1):
        """Store ontological analysis result in database."""
        try:
            (DatabaseQueryFacade(self.db, logger)).store_ontological_results((
                    run_id, article_uri, model_name, response_text,
                    response_time_ms,
                    extracted_fields.get("sentiment"),
                    extracted_fields.get("sentiment_explanation"),
                    extracted_fields.get("future_signal"),
                    extracted_fields.get("future_signal_explanation"),
                    extracted_fields.get("time_to_impact"),
                    extracted_fields.get("time_to_impact_explanation"),
                    extracted_fields.get("driver_type"),
                    extracted_fields.get("driver_type_explanation"),
                    extracted_fields.get("category"),
                    extracted_fields.get("category_explanation"),
                    extracted_fields.get("political_bias"),
                    extracted_fields.get("political_bias_explanation"),
                    extracted_fields.get("factuality"),
                    extracted_fields.get("factuality_explanation"),
                    round_number
                ))
        except Exception as e:
            logger.error(f"Error storing ontological result: {e}")
    
    def _update_run_status(self, run_id: int, status: str):
        """Update run status."""
        try:
            (DatabaseQueryFacade(self.db, logger)).update_run_status((status, run_id))
        except Exception as e:
            logger.error(f"Error updating run status: {e}")
    
    def get_runs(self) -> List[Dict[str, Any]]:
        """Get all bias evaluation runs."""
        try:
            runs = []
            for row in (DatabaseQueryFacade(self.db, logger)).get_all_bias_evaluation_runs():
                # Convert datetime objects to strings for API compatibility
                created_at = row['created_at']
                if created_at and hasattr(created_at, 'isoformat'):
                    created_at = created_at.isoformat()
                elif created_at:
                    created_at = str(created_at)

                completed_at = row['completed_at']
                if completed_at and hasattr(completed_at, 'isoformat'):
                    completed_at = completed_at.isoformat()
                elif completed_at:
                    completed_at = str(completed_at)

                runs.append({
                    "id": row['id'],
                    "name": row['name'],
                    "description": row['description'],
                    "benchmark_model": row['benchmark_model'],
                    "selected_models": json.loads(row['selected_models']),
                    "article_count": row['article_count'],
                    "rounds": row['rounds'],
                    "current_round": row['current_round'],
                    "created_at": created_at,
                    "completed_at": completed_at,
                    "status": row['status']
                })

            return runs

        except Exception as e:
            logger.error(f"Error getting runs: {e}")
            return []
    
    def get_run_details(self, run_id: int) -> Optional[Dict[str, Any]]:
        """Get details for a specific run."""
        try:
            row = (DatabaseQueryFacade(self.db, logger)).get_run_details(run_id)
            if row:
                # Convert datetime objects to strings for API compatibility
                created_at = row['created_at']
                if created_at and hasattr(created_at, 'isoformat'):
                    created_at = created_at.isoformat()
                elif created_at:
                    created_at = str(created_at)

                completed_at = row['completed_at']
                if completed_at and hasattr(completed_at, 'isoformat'):
                    completed_at = completed_at.isoformat()
                elif completed_at:
                    completed_at = str(completed_at)

                return {
                    "id": row['id'],
                    "name": row['name'],
                    "description": row['description'],
                    "benchmark_model": row['benchmark_model'],
                    "selected_models": row['selected_models'],  # Keep as JSON string for now
                    "article_count": row['article_count'],
                    "rounds": row['rounds'],
                    "current_round": row['current_round'],
                    "created_at": created_at,
                    "completed_at": completed_at,
                    "status": row['status']
                }
            return None

        except Exception as e:
            logger.error(f"Error getting run details: {e}")
            return None
    
    def get_run_articles(self, run_id: int) -> List[Dict[str, Any]]:
        """Get articles for a specific run."""
        try:
            articles = []
            for row in (DatabaseQueryFacade(self.db, logger)).get_run_articles(run_id):
                articles.append({
                    "article_uri": row['article_uri'],
                    "article_title": row['article_title'],
                    "article_summary": row['article_summary']
                })

            return articles
        except Exception as e:
            logger.error(f"Error getting run articles: {e}")
            return []
    
    def get_run_results(self, run_id: int) -> Dict[str, Any]:
        """Get comprehensive results for a run including matrix view and benchmark comparison."""
        try:
            # Get run details
            run_details = self.get_run_details(run_id)
            if not run_details:
                return {}

            # Get all ontological results with article info
            results = (DatabaseQueryFacade(self.db, logger)).get_ontological_results_with_article_info(run_id)

            # Get benchmark data (original article data) for comparison including media bias info
            benchmark_rows = (DatabaseQueryFacade(self.db, logger)).get_benchmark_data_including_media_bias_info(run_id)
            benchmark_data = {}
            for row in benchmark_rows:
                benchmark_data[row['uri']] = {
                    "title": row['title'],
                    "sentiment": row['sentiment'],
                    "future_signal": row['future_signal'],
                    "time_to_impact": row['time_to_impact'],
                    "driver_type": row['driver_type'],
                    "category": row['category'],
                    "sentiment_explanation": row['sentiment_explanation'],
                    "future_signal_explanation": row['future_signal_explanation'],
                    "time_to_impact_explanation": row['time_to_impact_explanation'],
                    "driver_type_explanation": row['driver_type_explanation'],
                    "bias": row['bias'],
                    "factual_reporting": row['factual_reporting'],
                    "mbfc_credibility_rating": row['mbfc_credibility_rating'],
                    "bias_country": row['bias_country'],
                    "press_freedom": row['press_freedom'],
                    "media_type": row['media_type'],
                    "popularity": row['popularity'],
                    "source": row['news_source'],
                    "publication": row['news_source']  # Using news_source for both
                }

            # Build matrix data structure
            matrix_data = self._build_matrix_data(results, benchmark_data)

            # Calculate model statistics
            statistics = self._calculate_model_statistics(results)

            # Perform outlier analysis
            outlier_analysis = self._analyze_model_outliers(matrix_data, run_details["benchmark_model"])

            return {
                "run_details": run_details,
                "matrix_data": matrix_data,
                "benchmark_data": benchmark_data,
                "statistics": statistics,
                "outlier_analysis": outlier_analysis
            }
        except Exception as e:
            logger.error(f"Error getting run results: {e}")
            return {}
    
    def _build_matrix_data(self, results: List, benchmark_data: Dict) -> Dict[str, Any]:
        """Build matrix data structure for comparison view, aggregating across multiple rounds."""
        try:
            fields = ["sentiment", "future_signal", "time_to_impact", "driver_type", "category", "political_bias", "factuality"]
            
            # Group results by article, model, and round
            articles = {}
            models = set()
            rounds_info = {}
            
            for row in results:
                model_name = row['model_name']
                article_uri = row['article_uri']
                article_title = row['article_title']
                round_number = row['round_number']

                models.add(model_name)

                if article_uri not in articles:
                    articles[article_uri] = {
                        "title": article_title,
                        "uri": article_uri,
                        "benchmark": benchmark_data.get(article_uri, {}),
                        "models": {}
                    }

                if model_name not in articles[article_uri]["models"]:
                    articles[article_uri]["models"][model_name] = {
                        "rounds": {},
                        "aggregated": {},
                        "consistency": {}
                    }

                # Store round-specific data
                articles[article_uri]["models"][model_name]["rounds"][round_number] = {
                    "sentiment": row['sentiment'],
                    "sentiment_explanation": row['sentiment_explanation'],
                    "future_signal": row['future_signal'],
                    "future_signal_explanation": row['future_signal_explanation'],
                    "time_to_impact": row['time_to_impact'],
                    "time_to_impact_explanation": row['time_to_impact_explanation'],
                    "driver_type": row['driver_type'],
                    "driver_type_explanation": row['driver_type_explanation'],
                    "category": row['category'],
                    "category_explanation": row['category_explanation'],
                    "political_bias": row['political_bias'],
                    "political_bias_explanation": row['political_bias_explanation'],
                    "factuality": row['factuality'],
                    "factuality_explanation": row['factuality_explanation'],
                    "confidence_score": row['confidence_score'],
                    "response_time_ms": row['response_time_ms'],
                    "error_message": row['error_message'],
                    "response_text": row['response_text']
                }
                
                # Track rounds for this run
                if article_uri not in rounds_info:
                    rounds_info[article_uri] = set()
                rounds_info[article_uri].add(round_number)
            
            # Aggregate results across rounds for each model/article combination
            for article_uri, article_data in articles.items():
                for model_name, model_data in article_data["models"].items():
                    rounds_data = model_data["rounds"]
                    
                    # Calculate aggregated values and consistency for each field
                    for field in fields:
                        field_values = []
                        explanations = []
                        
                        for round_num, round_data in rounds_data.items():
                            if round_data.get(field) is not None:
                                field_values.append(round_data[field])
                            if round_data.get(f"{field}_explanation"):
                                explanations.append(f"R{round_num}: {round_data[f'{field}_explanation']}")
                        
                        # Calculate most common value (mode) for aggregation
                        if field_values:
                            from collections import Counter
                            value_counts = Counter(field_values)
                            most_common_value = value_counts.most_common(1)[0][0]
                            consistency_rate = value_counts[most_common_value] / len(field_values)
                            
                            model_data["aggregated"][field] = most_common_value
                            model_data["aggregated"][f"{field}_explanation"] = " | ".join(explanations) if explanations else None
                            model_data["consistency"][field] = {
                                "rate": consistency_rate,
                                "values": field_values,
                                "counts": dict(value_counts)
                            }
                        else:
                            model_data["aggregated"][field] = None
                            model_data["aggregated"][f"{field}_explanation"] = None
                            model_data["consistency"][field] = {
                                "rate": 0.0,
                                "values": [],
                                "counts": {}
                            }
                    
                    # Calculate average response time and error rate
                    response_times = []
                    error_count = 0
                    total_rounds = len(rounds_data)
                    
                    for round_data in rounds_data.values():
                        if round_data.get("error_message"):
                            error_count += 1
                        elif round_data.get("response_time_ms"):
                            response_times.append(round_data["response_time_ms"])
                    
                    model_data["aggregated"]["response_time_ms"] = sum(response_times) / len(response_times) if response_times else None
                    model_data["aggregated"]["error_message"] = f"{error_count}/{total_rounds} errors" if error_count > 0 else None
                    model_data["aggregated"]["error_rate"] = error_count / total_rounds if total_rounds > 0 else 0
            
            # Create field matrices using aggregated data
            field_matrices = {}
            for field in fields:
                field_matrices[field] = {
                    "field_name": field,
                    "articles": [],
                    "models": list(models),
                    "matrix": [],
                    "benchmark_column": []
                }
                
                # Build matrix rows
                for article_uri, article_data in articles.items():
                    # Get media bias data from benchmark if available
                    benchmark_article = article_data["benchmark"]
                    
                    row_data = {
                        "article_uri": article_uri,
                        "article_title": article_data["title"],
                        "benchmark_value": benchmark_article.get(field),
                        "model_values": {},
                        # Add media bias fields for display
                        "bias": benchmark_article.get("bias"),
                        "factual_reporting": benchmark_article.get("factual_reporting"),
                        "mbfc_credibility_rating": benchmark_article.get("mbfc_credibility_rating"),
                        "bias_country": benchmark_article.get("bias_country"),
                        "press_freedom": benchmark_article.get("press_freedom"),
                        "media_type": benchmark_article.get("media_type"),
                        "popularity": benchmark_article.get("popularity"),
                        "source": benchmark_article.get("source"),
                        "publication": benchmark_article.get("publication")
                    }
                    
                    # Get aggregated values from each model
                    for model_name in models:
                        if model_name in article_data["models"]:
                            model_data = article_data["models"][model_name]
                            aggregated = model_data["aggregated"]
                            consistency = model_data["consistency"].get(field, {})
                            
                            # Build explanation with consistency info
                            explanation = aggregated.get(f"{field}_explanation") or ""
                            if len(model_data["rounds"]) > 1:
                                consistency_rate = consistency.get("rate", 0) * 100
                                if explanation:
                                    explanation += f" | Consistency: {consistency_rate:.1f}% ({consistency.get('counts', {})})"
                                else:
                                    explanation = f"Consistency: {consistency_rate:.1f}% ({consistency.get('counts', {})})"
                            
                            row_data["model_values"][model_name] = {
                                "value": aggregated.get(field),
                                "explanation": explanation,
                                "has_error": bool(aggregated.get("error_message")),
                                "consistency_rate": consistency.get("rate", 0),
                                "rounds_data": model_data["rounds"],
                                "total_rounds": len(model_data["rounds"])
                            }
                        else:
                            row_data["model_values"][model_name] = {
                                "value": None,
                                "explanation": None,
                                "has_error": True,
                                "consistency_rate": 0,
                                "rounds_data": {},
                                "total_rounds": 0
                            }
                    
                    field_matrices[field]["matrix"].append(row_data)
                    field_matrices[field]["benchmark_column"].append(article_data["benchmark"].get(field))
            
            return {
                "articles": articles,
                "models": list(models),
                "field_matrices": field_matrices,
                "rounds_info": {uri: list(rounds) for uri, rounds in rounds_info.items()},  # Convert sets to lists
                "total_rounds": max(len(rounds) for rounds in rounds_info.values()) if rounds_info else 1
            }
            
        except Exception as e:
            logger.error(f"Error building matrix data: {e}")
            return {}
    
    def _calculate_model_statistics(self, results: List) -> Dict[str, Any]:
        """Calculate statistics for each model."""
        try:
            model_stats = {}
            
            for row in results:
                model_name = row['model_name']
                if model_name not in model_stats:
                    model_stats[model_name] = {
                        "response_times": [],
                        "error_count": 0,
                        "total_evaluations": 0,
                        "field_accuracy": {}  # Compared to benchmark
                    }

                stats = model_stats[model_name]
                stats["total_evaluations"] += 1

                if row['error_message']:
                    stats["error_count"] += 1
                else:
                    if row['response_time_ms'] is not None:
                        stats["response_times"].append(row['response_time_ms'])
            
            # Calculate summary statistics
            for model_name, data in model_stats.items():
                response_times = data["response_times"]
                successful_evaluations = data["total_evaluations"] - data["error_count"]
                
                model_stats[model_name].update({
                    "mean_response_time": mean(response_times) if response_times else 0,
                    "std_response_time": stdev(response_times) if len(response_times) > 1 else 0,
                    "successful_evaluations": successful_evaluations,
                    "success_rate": successful_evaluations / data["total_evaluations"] if data["total_evaluations"] > 0 else 0
                })
            
            return model_stats
            
        except Exception as e:
            logger.error(f"Error calculating model statistics: {e}")
            return {}
    
    def _analyze_model_outliers(self, matrix_data: Dict, benchmark_model: str) -> Dict[str, Any]:
        """Analyze which models are outliers and why."""
        try:
            # Default structure to ensure consistency
            default_structure = {
                "outlier_models": {},
                "consensus_analysis": {},
                "benchmark_comparison": {},
                "model_outlier_scores": {}
            }
            
            if not matrix_data or "field_matrices" not in matrix_data:
                return default_structure
            
            outlier_analysis = {
                "outlier_models": {},
                "consensus_analysis": {},
                "benchmark_comparison": {}
            }
            
            fields = ["sentiment", "future_signal", "time_to_impact", "driver_type", "category", "political_bias", "factuality"]
            models = matrix_data.get("models", [])
            
            for field in fields:
                field_matrix = matrix_data["field_matrices"].get(field, {})
                matrix = field_matrix.get("matrix", [])
                
                field_outliers = {}
                consensus_data = {}
                
                # Analyze each article's responses
                for row in matrix:
                    article_uri = row["article_uri"]
                    model_values = row["model_values"]
                    benchmark_value = row["benchmark_value"]
                    
                    # Count value frequencies (excluding errors/nulls)
                    value_counts = {}
                    valid_models = []
                    
                    for model_name, model_data in model_values.items():
                        if not model_data.get("has_error") and model_data.get("value"):
                            value = model_data["value"]
                            value_counts[value] = value_counts.get(value, 0) + 1
                            valid_models.append(model_name)
                    
                    if len(value_counts) > 1:  # There's disagreement
                        # Find consensus (most common value)
                        consensus_value = max(value_counts.items(), key=lambda x: x[1])[0] if value_counts else None
                        consensus_count = value_counts.get(consensus_value, 0)
                        
                        # Find outlier models (those not agreeing with consensus)
                        for model_name in valid_models:
                            model_value = model_values[model_name]["value"]
                            if model_value != consensus_value:
                                if model_name not in field_outliers:
                                    field_outliers[model_name] = []
                                field_outliers[model_name].append({
                                    "article_uri": article_uri,
                                    "article_title": row["article_title"],
                                    "model_value": model_value,
                                    "consensus_value": consensus_value,
                                    "benchmark_value": benchmark_value,
                                    "explanation": model_values[model_name].get("explanation")
                                })
                        
                        consensus_data[article_uri] = {
                            "consensus_value": consensus_value,
                            "consensus_count": consensus_count,
                            "total_valid_models": len(valid_models),
                            "agreement_rate": consensus_count / len(valid_models) if valid_models else 0,
                            "benchmark_matches_consensus": consensus_value == benchmark_value
                        }
                
                outlier_analysis["outlier_models"][field] = field_outliers
                outlier_analysis["consensus_analysis"][field] = consensus_data
            
            # Overall model outlier scoring
            model_outlier_scores = {}
            for model in models:
                total_outlier_count = 0
                total_articles = 0
                
                for field in fields:
                    field_outliers = outlier_analysis["outlier_models"].get(field, {})
                    if model in field_outliers:
                        total_outlier_count += len(field_outliers[model])
                    
                    # Count total articles this model processed for this field
                    field_matrix = matrix_data["field_matrices"].get(field, {})
                    for row in field_matrix.get("matrix", []):
                        if model in row.get("model_values", {}) and not row["model_values"][model].get("has_error"):
                            total_articles += 1
                
                outlier_score = total_outlier_count / total_articles if total_articles > 0 else 0
                model_outlier_scores[model] = {
                    "outlier_count": total_outlier_count,
                    "total_articles": total_articles // len(fields),  # Divide by fields to avoid double counting
                    "outlier_rate": outlier_score,
                    "is_outlier": outlier_score > 0.3  # More than 30% disagreement
                }
            
            outlier_analysis["model_outlier_scores"] = model_outlier_scores
            
            return outlier_analysis
            
        except Exception as e:
            logger.error(f"Error analyzing model outliers: {e}")
            # Return default structure even on error
            return {
                "outlier_models": {},
                "consensus_analysis": {},
                "benchmark_comparison": {},
                "model_outlier_scores": {}
            }

    def delete_run(self, run_id: int) -> bool:
        """Delete a bias evaluation run and all its results."""
        try:
            return (DatabaseQueryFacade(self.db, logger)).delete_run(run_id) > 0
        except Exception as e:
            logger.error(f"Error deleting run: {e}")
            return False
    
    def export_run_to_csv(self, run_id: int) -> Optional[str]:
        """Export basic run information to CSV format."""
        try:
            run_details = self.get_run_details(run_id)
            if not run_details:
                return None
            
            # Get run results for summary stats
            results_data = self.get_run_results(run_id)
            statistics = results_data.get("statistics", {})
            
            import io
            import csv
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write run header info
            writer.writerow(["Model Bias Arena - Run Summary"])
            writer.writerow(["Run ID", run_id])
            writer.writerow(["Run Name", run_details["name"]])
            writer.writerow(["Description", run_details.get("description", "")])
            writer.writerow(["Benchmark Model", run_details["benchmark_model"]])
            writer.writerow(["Article Count", run_details["article_count"]])
            writer.writerow(["Created At", run_details["created_at"]])
            writer.writerow(["Status", run_details["status"]])
            writer.writerow([])
            
            # Write model statistics
            writer.writerow(["Model Statistics"])
            writer.writerow(["Model", "Response Time (ms)", "Success Rate (%)", "Successful Evaluations", "Total Evaluations", "Error Count"])
            
            for model_name, stats in statistics.items():
                writer.writerow([
                    model_name,
                    round(stats.get("mean_response_time", 0)),
                    round(stats.get("success_rate", 0) * 100, 1),
                    stats.get("successful_evaluations", 0),
                    stats.get("total_evaluations", 0),
                    stats.get("error_count", 0)
                ])
            
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"Error exporting run to CSV: {e}")
            return None
    
    def export_run_results_to_csv(self, run_id: int) -> Optional[str]:
        """Export detailed run results to CSV format with complete matrix data."""
        try:
            results_data = self.get_run_results(run_id)
            run_details = results_data.get("run_details", {})
            matrix_data = results_data.get("matrix_data", {})
            statistics = results_data.get("statistics", {})
            outlier_analysis = results_data.get("outlier_analysis", {})
            
            if not matrix_data or "field_matrices" not in matrix_data:
                return None
                
            import io
            import csv
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header with run information
            writer.writerow(["Model Bias Arena - Complete Export"])
            writer.writerow(["Run Name", run_details.get("name", "")])
            writer.writerow(["Run ID", run_id])
            writer.writerow(["Benchmark Model", run_details.get("benchmark_model", "")])
            writer.writerow(["Created", run_details.get("created_at", "")])
            writer.writerow(["Status", run_details.get("status", "")])
            writer.writerow([])
            
            # Model Statistics Summary
            writer.writerow(["MODEL PERFORMANCE STATISTICS"])
            writer.writerow(["Model", "Response Time (ms)", "Success Rate (%)", "Outlier Rate (%)", "Evaluations", "Error Count"])
            
            for model_name, stats in statistics.items():
                outlier_score = outlier_analysis.get("model_outlier_scores", {}).get(model_name, {})
                writer.writerow([
                    model_name,
                    round(stats.get("mean_response_time", 0)),
                    round(stats.get("success_rate", 0) * 100, 1),
                    round(outlier_score.get("outlier_rate", 0) * 100, 1),
                    f"{stats.get('successful_evaluations', 0)}/{stats.get('total_evaluations', 0)}",
                    stats.get("error_count", 0)
                ])
            writer.writerow([])
            
            # Detailed Field Analysis
            fields = ["sentiment", "future_signal", "time_to_impact", "driver_type", "category", "political_bias", "factuality"]
            models = matrix_data.get("models", [])
            
            writer.writerow(["DETAILED FIELD ANALYSIS"])
            writer.writerow([])
            
            for field in fields:
                field_matrix = matrix_data["field_matrices"].get(field, {})
                matrix = field_matrix.get("matrix", [])
                
                if not matrix:
                    continue
                    
                writer.writerow([f"FIELD: {field.upper()}"])
                
                # Write comprehensive headers
                headers = ["Article_ID", "Article_Title", "Article_URL", "Benchmark_Value"]
                for model in models:
                    headers.extend([f"{model}_Value", f"{model}_Explanation", f"{model}_Agreement"])
                writer.writerow(headers)
                
                # Write detailed data rows
                for idx, row in enumerate(matrix):
                    data_row = [
                        f"Article_{idx + 1}",
                        row.get("article_title", "")[:100],  # Truncate long titles
                        row.get("article_uri", ""),
                        row.get("benchmark_value", "")
                    ]
                    
                    # Add comprehensive model data
                    for model in models:
                        model_data = row.get("model_values", {}).get(model, {})
                        if model_data.get("has_error"):
                            data_row.extend(["ERROR", "Error occurred", "No"])
                        else:
                            value = model_data.get("value", "No response")
                            explanation = model_data.get("explanation", "")
                            agrees_with_benchmark = "Yes" if value == row.get("benchmark_value") else "No"
                            data_row.extend([value, explanation, agrees_with_benchmark])
                    
                    writer.writerow(data_row)
                
                # Add field summary
                writer.writerow([])
                writer.writerow(["Field Summary:"])
                
                # Calculate agreement rates per model for this field
                for model in models:
                    agreements = 0
                    total = 0
                    for row in matrix:
                        model_data = row.get("model_values", {}).get(model, {})
                        if not model_data.get("has_error") and model_data.get("value"):
                            total += 1
                            if model_data.get("value") == row.get("benchmark_value"):
                                agreements += 1
                    
                    agreement_rate = (agreements / total * 100) if total > 0 else 0
                    writer.writerow([f"{model} Agreement Rate", f"{agreement_rate:.1f}%", f"({agreements}/{total})"])
                
                writer.writerow([])
                writer.writerow([])
            
            # Outlier Analysis Summary
            writer.writerow(["OUTLIER ANALYSIS"])
            writer.writerow([])
            
            model_outlier_scores = outlier_analysis.get("model_outlier_scores", {})
            writer.writerow(["Model", "Outlier_Count", "Total_Articles", "Outlier_Rate", "Is_Outlier"])
            
            for model, scores in model_outlier_scores.items():
                writer.writerow([
                    model,
                    scores.get("outlier_count", 0),
                    scores.get("total_articles", 0),
                    f"{scores.get('outlier_rate', 0) * 100:.1f}%",
                    "Yes" if scores.get("is_outlier", False) else "No"
                ])
            
            writer.writerow([])
            
            # Field-specific outliers
            writer.writerow(["FIELD-SPECIFIC OUTLIERS"])
            outlier_models = outlier_analysis.get("outlier_models", {})
            
            for field, field_outliers in outlier_models.items():
                if field_outliers:
                    writer.writerow([f"Field: {field.upper()}"])
                    writer.writerow(["Model", "Disagreement_Count", "Sample_Disagreement"])
                    
                    for model, outliers in field_outliers.items():
                        sample_disagreement = ""
                        if outliers:
                            sample = outliers[0]
                            sample_disagreement = f"Expected: {sample.get('consensus_value', 'N/A')}, Got: {sample.get('model_value', 'N/A')}"
                        
                        writer.writerow([model, len(outliers), sample_disagreement])
                    writer.writerow([])
            
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"Error exporting run results to CSV: {e}")
            return None
    
    def export_run_to_pdf(self, run_id: int) -> Optional[bytes]:
        """Export comprehensive run report to PDF format."""
        try:
            results_data = self.get_run_results(run_id)
            run_details = results_data.get("run_details", {})
            statistics = results_data.get("statistics", {})
            outlier_analysis = results_data.get("outlier_analysis", {})
            matrix_data = results_data.get("matrix_data", {})
            
            if not run_details:
                return None
            
            # Create comprehensive HTML report that can be converted to PDF
            html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Model Bias Arena Report - {run_details.get('name', 'Unknown')}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .header {{ border-bottom: 2px solid #333; padding-bottom: 20px; margin-bottom: 30px; }}
        .section {{ margin-bottom: 30px; }}
        .stats-table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        .stats-table th, .stats-table td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        .stats-table th {{ background-color: #f2f2f2; }}
        .outlier-high {{ color: #d32f2f; font-weight: bold; }}
        .outlier-medium {{ color: #f57c00; }}
        .outlier-low {{ color: #388e3c; }}
        .agreement {{ color: #388e3c; }}
        .disagreement {{ color: #d32f2f; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Model Bias Arena Report</h1>
        <p><strong>Run:</strong> {run_details.get('name', 'Unknown')}</p>
        <p><strong>Date:</strong> {run_details.get('created_at', 'Unknown')}</p>
        <p><strong>Status:</strong> {run_details.get('status', 'Unknown')}</p>
        <p><strong>Benchmark Model:</strong> {run_details.get('benchmark_model', 'Unknown')}</p>
        <p><strong>Article Count:</strong> {run_details.get('article_count', 0)}</p>
    </div>

    <div class="section">
        <h2>Executive Summary</h2>
        <p>This report analyzes bias and consistency across {len(statistics)} AI models on {run_details.get('article_count', 0)} articles, 
        comparing their ontological field extraction against a benchmark model.</p>
    </div>

    <div class="section">
        <h2>Model Performance Statistics</h2>
        <table class="stats-table">
            <thead>
                <tr>
                    <th>Model</th>
                    <th>Response Time (ms)</th>
                    <th>Success Rate (%)</th>
                    <th>Outlier Rate (%)</th>
                    <th>Evaluations</th>
                    <th>Performance Rating</th>
                </tr>
            </thead>
            <tbody>
"""
            
            # Add model statistics
            for model_name, stats in statistics.items():
                outlier_score = outlier_analysis.get("model_outlier_scores", {}).get(model_name, {})
                outlier_rate = outlier_score.get("outlier_rate", 0) * 100
                
                # Determine performance rating
                rating = "Excellent"
                if outlier_rate > 30:
                    rating = "Needs Improvement"
                elif outlier_rate > 15:
                    rating = "Good"
                elif outlier_rate > 5:
                    rating = "Very Good"
                
                outlier_class = "outlier-high" if outlier_rate > 30 else ("outlier-medium" if outlier_rate > 15 else "outlier-low")
                
                html_content += f"""
                <tr>
                    <td><strong>{model_name}</strong></td>
                    <td>{round(stats.get('mean_response_time', 0))}</td>
                    <td>{round(stats.get('success_rate', 0) * 100, 1)}%</td>
                    <td class="{outlier_class}">{outlier_rate:.1f}%</td>
                    <td>{stats.get('successful_evaluations', 0)}/{stats.get('total_evaluations', 0)}</td>
                    <td>{rating}</td>
                </tr>
"""
            
            html_content += """
            </tbody>
        </table>
    </div>

    <div class="section">
        <h2>Field Analysis Summary</h2>
        <p>Agreement rates with benchmark model across different ontological fields:</p>
"""
            
            # Add field analysis
            if matrix_data and "field_matrices" in matrix_data:
                fields = ["sentiment", "future_signal", "time_to_impact", "driver_type", "category"]
                models = matrix_data.get("models", [])
                
                for field in fields:
                    field_matrix = matrix_data["field_matrices"].get(field, {})
                    matrix = field_matrix.get("matrix", [])
                    
                    if matrix:
                        html_content += f"<h3>{field.replace('_', ' ').title()}</h3><ul>"
                        
                        for model in models:
                            agreements = 0
                            total = 0
                            for row in matrix:
                                model_data = row.get("model_values", {}).get(model, {})
                                if not model_data.get("has_error") and model_data.get("value"):
                                    total += 1
                                    if model_data.get("value") == row.get("benchmark_value"):
                                        agreements += 1
                            
                            agreement_rate = (agreements / total * 100) if total > 0 else 0
                            agreement_class = "agreement" if agreement_rate >= 70 else "disagreement"
                            html_content += f'<li class="{agreement_class}"><strong>{model}:</strong> {agreement_rate:.1f}% agreement ({agreements}/{total})</li>'
                        
                        html_content += "</ul>"
            
            html_content += """
    </div>

    <div class="section">
        <h2>Key Insights</h2>
        <ul>
"""
            
            # Add insights based on data
            model_outlier_scores = outlier_analysis.get("model_outlier_scores", {})
            if model_outlier_scores:
                best_model = min(model_outlier_scores.items(), key=lambda x: x[1].get("outlier_rate", 1))
                worst_model = max(model_outlier_scores.items(), key=lambda x: x[1].get("outlier_rate", 0))
                
                html_content += f"""
            <li><strong>Most Consistent Model:</strong> {best_model[0]} with {best_model[1].get('outlier_rate', 0) * 100:.1f}% outlier rate</li>
            <li><strong>Least Consistent Model:</strong> {worst_model[0]} with {worst_model[1].get('outlier_rate', 0) * 100:.1f}% outlier rate</li>
"""
            
            if statistics:
                fastest_model = min(statistics.items(), key=lambda x: x[1].get("mean_response_time", float('inf')))
                html_content += f"<li><strong>Fastest Model:</strong> {fastest_model[0]} at {round(fastest_model[1].get('mean_response_time', 0))}ms average</li>"
            
            html_content += """
        </ul>
    </div>

    <div class="section">
        <h2>Recommendations</h2>
        <ul>
            <li>Models with high outlier rates (>30%) should be reviewed for consistency issues</li>
            <li>Consider using the most consistent model for production workloads</li>
            <li>Monitor response times for performance optimization opportunities</li>
            <li>Regular bias evaluations help maintain model quality over time</li>
        </ul>
    </div>
</body>
</html>
"""
            
            # Return HTML content as bytes (can be converted to PDF with tools like wkhtmltopdf)
            return html_content.encode('utf-8')
            
        except Exception as e:
            logger.error(f"Error exporting run to PDF: {e}")
            return None
    
    def export_run_to_png(self, run_id: int) -> Optional[bytes]:
        """Export run visualization to PNG format as ASCII art dashboard."""
        try:
            results_data = self.get_run_results(run_id)
            run_details = results_data.get("run_details", {})
            statistics = results_data.get("statistics", {})
            outlier_analysis = results_data.get("outlier_analysis", {})
            
            if not results_data:
                return None
            
            # Create ASCII art visualization
            visualization = f"""
{'='*80}
                    MODEL BIAS ARENA DASHBOARD
{'='*80}

Run: {run_details.get('name', 'Unknown')}
Date: {run_details.get('created_at', 'Unknown')}
Benchmark: {run_details.get('benchmark_model', 'Unknown')}

{'='*80}
                    PERFORMANCE OVERVIEW
{'='*80}

Model                    Response Time    Success Rate    Outlier Rate
{'-'*70}
"""
            
            # Add model performance bars
            for model_name, stats in statistics.items():
                outlier_score = outlier_analysis.get("model_outlier_scores", {}).get(model_name, {})
                response_time = round(stats.get('mean_response_time', 0))
                success_rate = round(stats.get('success_rate', 0) * 100, 1)
                outlier_rate = round(outlier_score.get('outlier_rate', 0) * 100, 1)
                
                # Create visual bars
                success_bar = '█' * int(success_rate / 5) + '░' * (20 - int(success_rate / 5))
                outlier_bar = '█' * int(outlier_rate / 5) + '░' * (20 - int(outlier_rate / 5))
                
                visualization += f"""
{model_name[:20]:20} {response_time:6d}ms      {success_rate:5.1f}%       {outlier_rate:5.1f}%
Success: [{success_bar}] {success_rate}%
Outlier: [{outlier_bar}] {outlier_rate}%
{'-'*70}
"""
            
            # Add agreement matrix visualization
            matrix_data = results_data.get("matrix_data", {})
            if matrix_data and "field_matrices" in matrix_data:
                visualization += f"""

{'='*80}
                    FIELD AGREEMENT MATRIX
{'='*80}

Field Analysis (█ = High Agreement, ▓ = Medium, ░ = Low, ▒ = Poor):

"""
                fields = ["sentiment", "future_signal", "time_to_impact", "driver_type", "category"]
                models = matrix_data.get("models", [])
                
                # Header
                visualization += f"{'Field':15}"
                for model in models:
                    visualization += f"{model[:10]:12}"
                visualization += "\n" + "-" * (15 + len(models) * 12) + "\n"
                
                # Field rows
                for field in fields:
                    field_matrix = matrix_data["field_matrices"].get(field, {})
                    matrix = field_matrix.get("matrix", [])
                    
                    visualization += f"{field[:15]:15}"
                    
                    for model in models:
                        agreements = 0
                        total = 0
                        for row in matrix:
                            model_data = row.get("model_values", {}).get(model, {})
                            if not model_data.get("has_error") and model_data.get("value"):
                                total += 1
                                if model_data.get("value") == row.get("benchmark_value"):
                                    agreements += 1
                        
                        agreement_rate = (agreements / total * 100) if total > 0 else 0
                        
                        # Visual representation
                        if agreement_rate >= 80:
                            symbol = "█"  # High agreement
                        elif agreement_rate >= 60:
                            symbol = "▓"  # Medium agreement
                        elif agreement_rate >= 40:
                            symbol = "░"  # Low agreement
                        else:
                            symbol = "▒"  # Poor agreement
                        
                        visualization += f"{symbol * 3} {agreement_rate:5.1f}%  "
                    
                    visualization += "\n"
            
            # Add insights section
            model_outlier_scores = outlier_analysis.get("model_outlier_scores", {})
            if model_outlier_scores:
                best_model = min(model_outlier_scores.items(), key=lambda x: x[1].get("outlier_rate", 1))
                worst_model = max(model_outlier_scores.items(), key=lambda x: x[1].get("outlier_rate", 0))
                
                visualization += f"""

{'='*80}
                        KEY INSIGHTS
{'='*80}

🏆 Most Consistent: {best_model[0]} ({best_model[1].get('outlier_rate', 0) * 100:.1f}% outlier rate)
⚠️  Least Consistent: {worst_model[0]} ({worst_model[1].get('outlier_rate', 0) * 100:.1f}% outlier rate)
"""
            
            if statistics:
                fastest_model = min(statistics.items(), key=lambda x: x[1].get("mean_response_time", float('inf')))
                visualization += f"⚡ Fastest Response: {fastest_model[0]} ({round(fastest_model[1].get('mean_response_time', 0))}ms)\n"
            
            visualization += f"""

{'='*80}
                        LEGEND
{'='*80}

Agreement Levels: █ High (80%+)  ▓ Medium (60-79%)  ░ Low (40-59%)  ▒ Poor (<40%)
Performance Bars: Each █ represents 5% (20 blocks = 100%)

{'='*80}
"""
            
            # Return as bytes - this creates a text-based visualization
            # In production, you could use matplotlib to create actual PNG images
            return visualization.encode('utf-8')
            
        except Exception as e:
            logger.error(f"Error exporting run to PNG: {e}")
            return None
    
    def get_source_bias_validation_data(self, run_id: int) -> Dict[str, Dict[str, Any]]:
        """Get source bias data for validation purposes (separate from analysis to avoid contamination)."""
        try:
            articles = self.get_run_articles(run_id)
            validation_data = {}

            for article in articles:
                row = (DatabaseQueryFacade(self.db, logger)).get_source_bias_validation_data(article["article_uri"])
                if row:
                    validation_data[article["article_uri"]] = {
                        "known_political_bias": row[0],
                        "known_factual_reporting": row[1],
                        "known_credibility_rating": row[2],
                        "source_country": row[3],
                        "press_freedom_score": row[4],
                        "media_type": row[5],
                        "popularity_score": row[6]
                    }

            return validation_data
            
        except Exception as e:
            logger.error(f"Error getting source bias validation data: {e}")
            return {}

    def compare_results_with_source_bias(self, run_id: int) -> Dict[str, Any]:
        """Compare model results with known source bias for validation insights."""
        try:
            # Get model results
            results = self.get_run_results(run_id)
            
            # Get source bias validation data  
            validation_data = self.get_source_bias_validation_data(run_id)
            
            comparison_results = {
                "political_bias_accuracy": {},
                "factuality_accuracy": {},
                "model_performance_vs_known_bias": {}
            }
            
            matrix_data = results.get("matrix_data", {})
            field_matrices = matrix_data.get("field_matrices", {})
            
            # Compare political bias results
            if "political_bias" in field_matrices:
                political_matrix = field_matrices["political_bias"]
                comparison_results["political_bias_accuracy"] = self._calculate_bias_accuracy(
                    political_matrix, validation_data, "known_political_bias"
                )
            
            # Compare factuality results  
            if "factuality" in field_matrices:
                factuality_matrix = field_matrices["factuality"]
                comparison_results["factuality_accuracy"] = self._calculate_bias_accuracy(
                    factuality_matrix, validation_data, "known_factual_reporting"
                )
            
            return comparison_results
            
        except Exception as e:
            logger.error(f"Error comparing results with source bias: {e}")
            return {}

    def _calculate_bias_accuracy(self, matrix_data: Dict, validation_data: Dict, bias_field: str) -> Dict[str, Any]:
        """Calculate how well model results match known source bias."""
        accuracy_results = {}
        
        try:
            models = matrix_data.get("models", [])
            articles = matrix_data.get("articles", [])
            results_matrix = matrix_data.get("matrix", [])
            
            for model_idx, model_name in enumerate(models):
                correct_predictions = 0
                total_predictions = 0
                
                for article_idx, article in enumerate(articles):
                    article_uri = article.get("uri")
                    if article_uri in validation_data:
                        known_bias = validation_data[article_uri].get(bias_field)
                        model_prediction = results_matrix[article_idx][model_idx].get("value")
                        
                        if known_bias and model_prediction:
                            total_predictions += 1
                            # Normalize for comparison (case-insensitive, handle variations)
                            if self._normalize_bias_value(known_bias) == self._normalize_bias_value(model_prediction):
                                correct_predictions += 1
                
                accuracy_results[model_name] = {
                    "accuracy": correct_predictions / total_predictions if total_predictions > 0 else 0,
                    "correct_predictions": correct_predictions,
                    "total_predictions": total_predictions
                }
            
            return accuracy_results
            
        except Exception as e:
            logger.error(f"Error calculating bias accuracy: {e}")
            return {}

    def _normalize_bias_value(self, value: str) -> str:
        """Normalize bias values for comparison."""
        if not value:
            return ""
        
        value = value.lower().strip()
        
        # Normalize political bias values
        if "left" in value and "center" not in value:
            return "left-leaning"
        elif "left-center" in value or "center-left" in value:
            return "center-left"
        elif "right" in value and "center" not in value:
            return "right-leaning"  
        elif "right-center" in value or "center-right" in value:
            return "center-right"
        elif "center" in value or "least biased" in value:
            return "center"
        elif "mixed" in value:
            return "mixed"
        elif "neutral" in value:
            return "neutral"
        
        # Normalize factuality values
        elif "very high" in value:
            return "very high"
        elif "high" in value and "very" not in value:
            return "high"
        elif "mixed" in value:
            return "mixed"
        elif "low" in value and "very" not in value:
            return "low"
        elif "very low" in value:
            return "very low"
        
        return value 