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
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Only select articles that have all required ontological fields populated (benchmark data)
                query = """
                    SELECT uri, title, summary, news_source, topic, category,
                           sentiment, future_signal, time_to_impact, driver_type
                    FROM articles 
                    WHERE summary IS NOT NULL 
                    AND LENGTH(summary) > 100
                    AND analyzed = 1
                    AND sentiment IS NOT NULL AND sentiment != ''
                    AND future_signal IS NOT NULL AND future_signal != ''
                    AND time_to_impact IS NOT NULL AND time_to_impact != ''
                    AND driver_type IS NOT NULL AND driver_type != ''
                    AND category IS NOT NULL AND category != ''
                    AND (news_source IS NOT NULL AND news_source != '')
                """
                params = []
                
                if topic:
                    query += " AND topic = ?"
                    params.append(topic)
                    
                query += " ORDER BY RANDOM() LIMIT ?"
                params.append(count)
                
                cursor.execute(query, params)
                articles = []
                
                for row in cursor.fetchall():
                    articles.append({
                        "uri": row[0],
                        "title": row[1],
                        "summary": row[2],
                        "news_source": row[3],
                        "topic": row[4],
                        "category": row[5],
                        # Include benchmark values for reference
                        "benchmark_sentiment": row[6],
                        "benchmark_future_signal": row[7],
                        "benchmark_time_to_impact": row[8],
                        "benchmark_driver_type": row[9]
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
                                 topic: Optional[str] = None) -> int:
        """Create a new bias evaluation run."""
        try:
            # Sample articles
            articles = self.sample_articles(count=article_count, topic=topic)
            if not articles:
                raise ValueError("No articles found to sample")
            
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Create the run
                cursor.execute("""
                    INSERT INTO model_bias_arena_runs 
                    (name, description, benchmark_model, selected_models, article_count, status)
                    VALUES (?, ?, ?, ?, ?, 'running')
                """, (name, description, benchmark_model, json.dumps(selected_models), len(articles)))
                
                run_id = cursor.lastrowid
                
                # Add articles to the run
                for article in articles:
                    cursor.execute("""
                        INSERT INTO model_bias_arena_articles 
                        (run_id, article_uri, article_title, article_summary)
                        VALUES (?, ?, ?, ?)
                    """, (run_id, article["uri"], article["title"], article["summary"]))
                
                conn.commit()
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
            
            # Get articles for this run
            articles = self.get_run_articles(run_id)
            
            # Import ArticleAnalyzer from research.py approach
            from app.analyzers.article_analyzer import ArticleAnalyzer
            from app.ai_models import LiteLLMModel
            
            # Get topic ontology from first article to determine proper values
            first_article_topic = articles[0]["article_summary"] if articles else "AI and Machine Learning"  # fallback
            
            # Load proper ontology values from config like research.py does
            from app.config.config import load_config
            config = load_config()
            topic_configs = {topic['name']: topic for topic in config['topics']}
            
            # Find the appropriate topic config from sampled articles
            topic_config = None
            
            # Get topic from sampled articles by querying the database
            if articles:
                try:
                    with self.db.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT DISTINCT topic FROM articles WHERE uri = ?", (articles[0]["article_uri"],))
                        row = cursor.fetchone()
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
            
            results = {}
            
            # Evaluate each model (including benchmark)
            all_models = [benchmark_model] + [m for m in models if m != benchmark_model]
            
            for model_name in all_models:
                logger.info(f"Evaluating model: {model_name}")
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
                            
                            # Use ArticleAnalyzer like in research.py - analyze just the summary since that's what we have
                            parsed_analysis = article_analyzer.analyze_content(
                                article_text=article["article_summary"],
                                title=article["article_title"],
                                source=source,
                                uri=article["article_uri"],
                                summary_length=50,  # Not used since we already have summary
                                summary_voice="neutral",
                                summary_type="brief",
                                categories=categories,
                                future_signals=future_signals,
                                sentiment_options=sentiment_options,
                                time_to_impact_options=time_to_impact_options,
                                driver_types=driver_types
                            )
                            
                            response_time = int((time.time() - start_time) * 1000)
                            
                            # Extract ontological fields (remove confidence_score)
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
                                "category_explanation": parsed_analysis.get("category_explanation", "")
                            }
                            
                            # Store result with extracted fields
                            self._store_ontological_result(
                                run_id=run_id,
                                article_uri=article["article_uri"],
                                model_name=model_name,
                                response_text=str(parsed_analysis),  # Store full analysis response
                                extracted_fields=extracted_fields,
                                response_time_ms=response_time
                            )
                            
                            result_data = {
                                "article_uri": article["article_uri"],
                                "response_time_ms": response_time,
                                **extracted_fields
                            }
                            model_results.append(result_data)
                            
                        except Exception as e:
                            logger.error(f"Error evaluating article {article['article_uri']} with {model_name}: {e}")
                            # Store error result
                            self._store_evaluation_result(
                                run_id=run_id,
                                article_uri=article["article_uri"],
                                model_name=model_name,
                                error_message=str(e)
                            )
                    
                    results[model_name] = model_results
                    
                except Exception as e:
                    logger.error(f"Error initializing model {model_name}: {e}")
                    results[model_name] = {"error": str(e)}
            
            # Mark run as completed
            self._update_run_status(run_id, "completed")
            
            return results
            
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
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO model_bias_arena_results 
                    (run_id, article_uri, model_name, response_text, bias_score, 
                     confidence_score, response_time_ms, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (run_id, article_uri, model_name, response_text, bias_score,
                      confidence_score, response_time_ms, error_message))
                conn.commit()
        except Exception as e:
            logger.error(f"Error storing evaluation result: {e}")
    
    def _store_ontological_result(self,
                                run_id: int,
                                article_uri: str,
                                model_name: str,
                                response_text: str,
                                extracted_fields: Dict[str, Any],
                                response_time_ms: int):
        """Store ontological analysis result in database."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO model_bias_arena_results 
                    (run_id, article_uri, model_name, response_text, 
                     response_time_ms, sentiment, sentiment_explanation, future_signal, 
                     future_signal_explanation, time_to_impact, time_to_impact_explanation,
                     driver_type, driver_type_explanation, category, category_explanation)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
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
                    extracted_fields.get("category_explanation")
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Error storing ontological result: {e}")
    
    def _update_run_status(self, run_id: int, status: str):
        """Update run status."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE model_bias_arena_runs 
                    SET status = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, run_id))
                conn.commit()
        except Exception as e:
            logger.error(f"Error updating run status: {e}")
    
    def get_runs(self) -> List[Dict[str, Any]]:
        """Get all bias evaluation runs."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, name, description, benchmark_model, selected_models,
                           article_count, created_at, completed_at, status
                    FROM model_bias_arena_runs
                    ORDER BY created_at DESC
                """)
                
                runs = []
                for row in cursor.fetchall():
                    runs.append({
                        "id": row[0],
                        "name": row[1],
                        "description": row[2],
                        "benchmark_model": row[3],
                        "selected_models": json.loads(row[4]),
                        "article_count": row[5],
                        "created_at": row[6],
                        "completed_at": row[7],
                        "status": row[8]
                    })
                
                return runs
                
        except Exception as e:
            logger.error(f"Error getting runs: {e}")
            return []
    
    def get_run_details(self, run_id: int) -> Optional[Dict[str, Any]]:
        """Get details for a specific run."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, name, description, benchmark_model, selected_models,
                           article_count, created_at, completed_at, status
                    FROM model_bias_arena_runs
                    WHERE id = ?
                """, (run_id,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "name": row[1],
                        "description": row[2],
                        "benchmark_model": row[3],
                        "selected_models": row[4],  # Keep as JSON string for now
                        "article_count": row[5],
                        "created_at": row[6],
                        "completed_at": row[7],
                        "status": row[8]
                    }
                return None
                
        except Exception as e:
            logger.error(f"Error getting run details: {e}")
            return None
    
    def get_run_articles(self, run_id: int) -> List[Dict[str, Any]]:
        """Get articles for a specific run."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT article_uri, article_title, article_summary
                    FROM model_bias_arena_articles
                    WHERE run_id = ?
                    ORDER BY id
                """, (run_id,))
                
                articles = []
                for row in cursor.fetchall():
                    articles.append({
                        "article_uri": row[0],
                        "article_title": row[1],
                        "article_summary": row[2]
                    })
                
                return articles
                
        except Exception as e:
            logger.error(f"Error getting run articles: {e}")
            return []
    
    def get_run_results(self, run_id: int) -> Dict[str, Any]:
        """Get comprehensive results for a run including matrix view and benchmark comparison."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get run details
                run_details = self.get_run_details(run_id)
                if not run_details:
                    return {}
                
                # Get all ontological results with article info
                cursor.execute("""
                    SELECT r.model_name, r.article_uri, r.sentiment, r.sentiment_explanation,
                           r.future_signal, r.future_signal_explanation, r.time_to_impact, 
                           r.time_to_impact_explanation, r.driver_type, r.driver_type_explanation,
                           r.category, r.category_explanation, r.confidence_score, 
                           r.response_time_ms, r.error_message, r.response_text,
                           maa.article_title, maa.article_summary
                    FROM model_bias_arena_results r
                    JOIN model_bias_arena_articles maa ON r.article_uri = maa.article_uri 
                        AND r.run_id = maa.run_id
                    WHERE r.run_id = ?
                    ORDER BY r.article_uri, r.model_name
                """, (run_id,))
                
                results = cursor.fetchall()
                
                # Get benchmark data (original article data) for comparison
                cursor.execute("""
                    SELECT a.uri, a.title, a.sentiment, a.future_signal, a.time_to_impact,
                           a.driver_type, a.category, a.sentiment_explanation, 
                           a.future_signal_explanation, a.time_to_impact_explanation,
                           a.driver_type_explanation
                    FROM model_bias_arena_articles maa
                    JOIN articles a ON maa.article_uri = a.uri
                    WHERE maa.run_id = ?
                    ORDER BY a.uri
                """, (run_id,))
                
                benchmark_rows = cursor.fetchall()
                benchmark_data = {}
                for row in benchmark_rows:
                    benchmark_data[row[0]] = {
                        "title": row[1],
                        "sentiment": row[2],
                        "future_signal": row[3], 
                        "time_to_impact": row[4],
                        "driver_type": row[5],
                        "category": row[6],
                        "sentiment_explanation": row[7],
                        "future_signal_explanation": row[8],
                        "time_to_impact_explanation": row[9],
                        "driver_type_explanation": row[10]
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
        """Build matrix data structure for comparison view."""
        try:
            fields = ["sentiment", "future_signal", "time_to_impact", "driver_type", "category"]
            
            # Group results by article and model
            articles = {}
            models = set()
            
            for row in results:
                model_name = row[0]
                article_uri = row[1]
                article_title = row[16]
                
                models.add(model_name)
                
                if article_uri not in articles:
                    articles[article_uri] = {
                        "title": article_title,
                        "uri": article_uri,
                        "benchmark": benchmark_data.get(article_uri, {}),
                        "models": {}
                    }
                
                # Extract ontological fields for this model
                articles[article_uri]["models"][model_name] = {
                    "sentiment": row[2],
                    "sentiment_explanation": row[3],
                    "future_signal": row[4],
                    "future_signal_explanation": row[5],
                    "time_to_impact": row[6],
                    "time_to_impact_explanation": row[7],
                    "driver_type": row[8],
                    "driver_type_explanation": row[9],
                    "category": row[10],
                    "category_explanation": row[11],
                    "confidence_score": row[12],
                    "response_time_ms": row[13],
                    "error_message": row[14],
                    "response_text": row[15]
                }
            
            # Create field matrices
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
                    row_data = {
                        "article_uri": article_uri,
                        "article_title": article_data["title"],
                        "benchmark_value": article_data["benchmark"].get(field),
                        "model_values": {}
                    }
                    
                    # Get values from each model
                    for model_name in models:
                        if model_name in article_data["models"]:
                            model_result = article_data["models"][model_name]
                            row_data["model_values"][model_name] = {
                                "value": model_result.get(field),
                                "explanation": model_result.get(f"{field}_explanation"),
                                "has_error": bool(model_result.get("error_message"))
                            }
                        else:
                            row_data["model_values"][model_name] = {
                                "value": None,
                                "explanation": None,
                                "has_error": True
                            }
                    
                    field_matrices[field]["matrix"].append(row_data)
                    field_matrices[field]["benchmark_column"].append(article_data["benchmark"].get(field))
            
            return {
                "articles": articles,
                "models": list(models),
                "field_matrices": field_matrices
            }
            
        except Exception as e:
            logger.error(f"Error building matrix data: {e}")
            return {}
    
    def _calculate_model_statistics(self, results: List) -> Dict[str, Any]:
        """Calculate statistics for each model."""
        try:
            model_stats = {}
            
            for row in results:
                model_name = row[0]
                if model_name not in model_stats:
                    model_stats[model_name] = {
                        "response_times": [],
                        "error_count": 0,
                        "total_evaluations": 0,
                        "field_accuracy": {}  # Compared to benchmark
                    }
                
                stats = model_stats[model_name]
                stats["total_evaluations"] += 1
                
                if row[14]:  # error_message
                    stats["error_count"] += 1
                else:
                    if row[13] is not None:  # response_time_ms
                        stats["response_times"].append(row[13])
            
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
            if not matrix_data or "field_matrices" not in matrix_data:
                return {}
            
            outlier_analysis = {
                "outlier_models": {},
                "consensus_analysis": {},
                "benchmark_comparison": {}
            }
            
            fields = ["sentiment", "future_signal", "time_to_impact", "driver_type", "category"]
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
            return {}

    def delete_run(self, run_id: int) -> bool:
        """Delete a bias evaluation run and all its results."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM model_bias_arena_runs WHERE id = ?", (run_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting run: {e}")
            return False 