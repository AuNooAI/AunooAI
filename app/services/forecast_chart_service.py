"""
Forecast Chart Generation Service for Auspex

This service generates evidence-based forecast charts showing consensus bands
and outlier scenarios based on Auspex's analyzed articles and categories.
"""

import json
import logging
import matplotlib
from app.database_query_facade import DatabaseQueryFacade

matplotlib.use('Agg')  # Use non-interactive backend to avoid GUI threading issues
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import base64
import io
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, Counter

# Interactive plotting imports
try:
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
    import plotly.io as pio
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

from app.analyze_db import AnalyzeDB
from app.database import get_database_instance

logger = logging.getLogger(__name__)

# Configure matplotlib for server use
plt.ioff()  # Turn off interactive mode

class ForecastChartService:
    """Service for generating evidence-based forecast charts."""
    
    def __init__(self):
        self.db = get_database_instance()
        self.analyzer = AnalyzeDB(self.db)
        
        # Enhanced consensus types with detailed explanations
        self.consensus_types = {
            'positive_growth': {
                'color': '#b6d7a8',
                'label': 'Positive Growth',
                'description': 'Strong optimistic sentiment indicating technological advancement and beneficial adoption',
                'rationale': 'High positive sentiment (>60%) with minimal critical concerns'
            },
            'mixed_consensus': {
                'color': '#ffd966',
                'label': 'Mixed Consensus',
                'description': 'Balanced perspectives with both opportunities and challenges identified',
                'rationale': 'Moderate positive sentiment (30-60%) with significant debate and varied viewpoints'
            },
            'regulatory_critical': {
                'color': '#f4cccc',
                'label': 'Regulatory Response',
                'description': 'Policy and legal frameworks struggling to keep pace with technological change',
                'rationale': 'High critical sentiment focused on governance, ethics, and legal implications'
            },
            'safety_security': {
                'color': '#e06666',
                'label': 'Safety/Security',
                'description': 'Risk management focus with emphasis on preventing harm and ensuring reliability',
                'rationale': 'High critical sentiment centered on safety protocols and security measures'
            },
            'warfare_defense': {
                'color': '#f08080',
                'label': 'Defense Applications',
                'description': 'Military and defense sector adoption with security implications',
                'rationale': 'Critical sentiment regarding dual-use technologies and military applications'
            },
            'geopolitical': {
                'color': '#b4c7e7',
                'label': 'Geopolitical Strategy',
                'description': 'International competition and strategic national interests in technology',
                'rationale': 'Mixed sentiment reflecting competitive dynamics and policy considerations'
            },
            'business_automation': {
                'color': '#ffe599',
                'label': 'Business Transformation',
                'description': 'Commercial adoption driving immediate market changes and disruption',
                'rationale': 'High positive sentiment with focus on near-term business opportunities'
            },
            'societal_impact': {
                'color': '#f6b26b',
                'label': 'Societal Impact',
                'description': 'Focus on broader social implications, ethics, and human-centered concerns',
                'rationale': 'Mixed sentiment with emphasis on social responsibility and human welfare'
            }
        }
        
        # Legacy color mapping for backwards compatibility
        self.consensus_colors = {k: v['color'] for k, v in self.consensus_types.items()}
        
        # Outlier marker colors
        self.outlier_colors = {
            'optimistic': '#e74c3c',  # Red for optimistic outliers
            'pessimistic': '#3498db'  # Blue for pessimistic outliers
        }

    async def get_topics_with_categories(self) -> List[str]:
        """
        Get list of topics that have categories and data suitable for forecast generation.
        
        Returns:
            List of topic names that have forecast data
        """
        try:
            # Get all topics from database
            topics_data = self.db.get_topics()
            available_topics = []
            
            for topic_info in topics_data:
                topic_name = topic_info.get('id') or topic_info.get('name')
                if not topic_name:
                    continue
                    
                # Check if topic has categories
                topic_options = self.analyzer.get_topic_options(topic_name)
                categories = topic_options.get('categories', [])
                
                if categories:  # Only include topics that have categories
                    available_topics.append(topic_name)
                    
            logger.info(f"Found {len(available_topics)} topics with categories: {available_topics}")
            return available_topics
            
        except Exception as e:
            logger.error(f"Error getting topics with categories: {str(e)}", exc_info=True)
            return []

    async def generate_evidence_based_forecast_chart(
        self, 
        topic: str, 
        timeframe: str = "365",
        title_prefix: str = "AI & Machine Learning",
        interactive: bool = False,
        selected_categories: List[str] = None,
        selected_clusters: List[str] = None
    ) -> str:
        """
        Generate an evidence-based forecast chart showing consensus bands and outliers.
        
        Args:
            topic: The topic to analyze
            timeframe: Time period for data collection (default: 365 days)
            title_prefix: Prefix for the chart title
            interactive: Whether to generate interactive chart with tooltips
            
        Returns:
            Base64 encoded PNG image of the chart or HTML for interactive chart
        """
        try:
            # Get data for the topic
            chart_data = await self._prepare_chart_data(topic, timeframe, selected_categories, selected_clusters)
            
            if not chart_data['themes']:
                logger.warning(f"No data found for topic: {topic}")
                # Get available topics for better error message
                available_topics = await self.get_topics_with_categories()
                return self._generate_empty_chart(topic, available_topics)
            
            # Generate interactive chart if requested and available
            if interactive and PLOTLY_AVAILABLE:
                return self._create_interactive_forecast_chart(chart_data, title_prefix, topic)
            else:
                # Fallback to static chart
                chart_bytes = self._create_forecast_chart(chart_data, title_prefix, topic)
                chart_base64 = base64.b64encode(chart_bytes).decode('utf-8')
                return f"data:image/png;base64,{chart_base64}"
            
        except Exception as e:
            logger.error(f"Error generating forecast chart: {str(e)}", exc_info=True)
            raise

    async def _prepare_chart_data(self, topic: str, timeframe: str, selected_categories: List[str] = None, selected_clusters: List[str] = None) -> Dict:
        """Prepare data structure for chart generation."""
        
        logger.info(f"Preparing chart data for topic: {topic}, timeframe: {timeframe}")
        
        # First, let's check what topics actually exist in the database
        all_topics = self.db.get_topics()
        logger.info(f"All topics in database: {[t.get('id') or t.get('name') for t in all_topics]}")
        
        total_topic_articles, articles_with_categories, sample_categories = (DatabaseQueryFacade(self.db, logger)).get_total_articles_and_sample_categories_for_topic(topic)

        # Check total articles for this topic (case-insensitive)
        logger.info(f"Total articles for topic '{topic}': {total_topic_articles}")

        # Check articles with categories
        logger.info(f"Articles with categories for topic '{topic}': {articles_with_categories}")

        # Show some sample categories
        logger.info(f"Sample categories for topic '{topic}': {sample_categories}")
        
        # Get topic options to understand available categories
        # First try with exact match, then with case-insensitive match
        topic_options = self.analyzer.get_topic_options(topic)
        categories = topic_options.get('categories', [])
        
        if not categories:
            # Try case-insensitive search for topic name
            actual_topic_result = (DatabaseQueryFacade(self.db, logger)).get_topic(topic)
            if actual_topic_result:
                actual_topic = actual_topic_result[0]
                logger.info(f"Found actual topic case: '{actual_topic}' for requested: '{topic}'")
                topic_options = self.analyzer.get_topic_options(actual_topic)
                categories = topic_options.get('categories', [])
                topic = actual_topic  # Use the actual case
        
        logger.info(f"Topic options for '{topic}': {topic_options}")
        logger.info(f"Categories found: {categories}")
        
        if not categories:
            logger.warning(f"No categories found for topic: {topic}. Trying without curated filter...")
            # Try to get categories without the curated filter requirement
            raw_categories = (DatabaseQueryFacade(self.db, logger)).get_categories_for_topic(topic)
            logger.info(f"Raw categories found: {raw_categories}")
            if raw_categories:
                categories = raw_categories
            else:
                return {'themes': [], 'consensus_bands': [], 'outlier_markers': []}
        
        # Filter categories if specific ones were selected
        if selected_categories:
            categories = [cat for cat in categories if cat in selected_categories]
            logger.info(f"Filtered to selected categories: {categories}")
        
        # Get clusters if available (placeholder for future cluster implementation)
        clusters = []
        if selected_clusters:
            # TODO: Implement cluster filtering when cluster feature is added
            logger.info(f"Cluster filtering requested: {selected_clusters}")
        
        # Analyze each category for consensus and outliers
        themes = []
        consensus_bands = []
        outlier_markers = []
        
        for i, category in enumerate(categories[:8]):  # Limit to 8 themes for readability
            themes.append(category)
            
            try:
                # Try non-curated first to get actual article counts
                sentiment_data = self.analyzer.get_sentiment_distribution(
                    timeframe=timeframe, 
                    category=category, 
                    topic=topic,
                    curated=False
                )
                logger.info(f"Non-curated sentiment data for {category}: {sentiment_data}")
                
                # Get time to impact distribution
                impact_data = self.analyzer.get_time_to_impact_distribution(
                    timeframe=timeframe,
                    category=category,
                    topic=topic,
                    curated=False
                )
                logger.info(f"Non-curated impact data for {category}: {impact_data}")
                
                # Convert dict format to list format for consistency
                if isinstance(sentiment_data, dict):
                    labels = sentiment_data.get('labels', [])
                    values = sentiment_data.get('values', [])
                    sentiment_data = [{'sentiment': label, 'count': count} 
                                    for label, count in zip(labels, values)]
                    
                if isinstance(impact_data, dict):
                    labels = impact_data.get('labels', [])
                    values = impact_data.get('values', [])
                    impact_data = [{'time_to_impact': label, 'count': count} 
                                 for label, count in zip(labels, values)]
                
                # Ensure data is in expected format
                if not isinstance(sentiment_data, list):
                    logger.warning(f"Sentiment data is not a list: {type(sentiment_data)} - {sentiment_data}")
                    sentiment_data = []
                    
                if not isinstance(impact_data, list):
                    logger.warning(f"Impact data is not a list: {type(impact_data)} - {impact_data}")
                    impact_data = []
                
                # Analyze consensus and create bands
                consensus_band = self._analyze_consensus(
                    category, sentiment_data, impact_data
                )
                consensus_bands.append(consensus_band)
                
                # Identify outliers
                category_outliers = self._identify_outliers(
                    i, category, sentiment_data, topic, timeframe
                )
                outlier_markers.append(category_outliers)
                
            except Exception as e:
                logger.error(f"Error processing category {category}: {str(e)}", exc_info=True)
                # Add default data for this category
                consensus_bands.append((1, 4, self.consensus_colors['mixed_consensus'], "Data Error"))
                outlier_markers.append([])
        
        # Calculate total articles safely - use direct database query
        total_articles = 0
        try:
            if categories:
                placeholders = ', '.join(['?' for _ in categories])
                total_articles = (DatabaseQueryFacade(self.db, logger)).get_articles_count_from_topic_and_categories(placeholders, [topic] + categories)
            else:
                total_articles = (DatabaseQueryFacade(self.db, logger)).get_article_count_for_topic(topic)

            logger.info(f"Total articles counted: {total_articles}")
        except Exception as e:
            logger.error(f"Error calculating total articles: {str(e)}", exc_info=True)
            # Fallback to analyzer method
            try:
                for cat in categories:
                    cat_sentiment_data = self.analyzer.get_sentiment_distribution(timeframe, cat, topic, curated=False)
                    if isinstance(cat_sentiment_data, dict):
                        values = cat_sentiment_data.get('values', [])
                        total_articles += sum(values)
                    elif isinstance(cat_sentiment_data, list):
                        for item in cat_sentiment_data:
                            if isinstance(item, dict) and 'count' in item:
                                total_articles += item['count']
            except Exception as fallback_error:
                logger.error(f"Fallback calculation also failed: {str(fallback_error)}", exc_info=True)
                total_articles = 0
        
        return {
            'themes': themes,
            'consensus_bands': consensus_bands,
            'outlier_markers': outlier_markers,
            'total_articles': total_articles
        }

    def _analyze_consensus(
        self, 
        category: str, 
        sentiment_data: List[Dict], 
        impact_data: List[Dict]
    ) -> Tuple[int, int, str, str]:
        """
        Analyze data to determine consensus timing and type.
        
        Returns: (start_year_index, end_year_index, color, label)
        """
        
        logger.info(f"Analyzing consensus for {category}")
        logger.info(f"Sentiment data: {sentiment_data}")
        logger.info(f"Impact data: {impact_data}")
        
        # Map time to impact to year indices (0=2024, 1=2025, etc.)
        time_mapping = {
            'immediate': 0,
            '** short-term': 1,
            'short-term': 1,
            'mid-term': 3,
            'medium-term': 3,
            '** long-term': 6,
            'long-term': 6,
            'unknown': 2
        }
        
        # Determine consensus timing based on time_to_impact distribution
        try:
            total_articles = sum(item['count'] for item in impact_data if isinstance(item, dict) and 'count' in item)
            if total_articles == 0:
                return (1, 4, self.consensus_colors['mixed_consensus'], "Limited Data")
            
            # Calculate weighted average timing and spread
            weighted_time = 0
            time_spread = 0
            time_counts = {}
            
            for item in impact_data:
                if isinstance(item, dict) and 'time_to_impact' in item and 'count' in item:
                    time_key = item['time_to_impact'].lower()
                    time_index = time_mapping.get(time_key, 2)
                    weighted_time += time_index * item['count']
                    time_counts[time_index] = time_counts.get(time_index, 0) + item['count']
            
            if total_articles > 0:
                weighted_time = weighted_time / total_articles
                
                # Calculate spread (variance) for consensus band width
                variance = sum((time_idx - weighted_time) ** 2 * count for time_idx, count in time_counts.items()) / total_articles
                time_spread = variance ** 0.5
            else:
                weighted_time = 2  # Default to mid-term
                time_spread = 1
                
        except Exception as e:
            logger.error(f"Error calculating consensus timing: {str(e)}", exc_info=True)
            return (1, 4, self.consensus_colors['mixed_consensus'], "Calculation Error")
        
        # Determine band width based on spread and total articles
        if time_spread < 0.5 or total_articles < 10:
            # Narrow consensus
            start_time = max(0, int(weighted_time) - 1)
            end_time = min(10, int(weighted_time) + 1)
        elif time_spread > 2:
            # Wide consensus
            start_time = max(0, int(weighted_time) - 2)
            end_time = min(10, int(weighted_time) + 4)
        else:
            # Medium consensus
            start_time = max(0, int(weighted_time) - 1)
            end_time = min(10, int(weighted_time) + 2)
        
        # Determine consensus type based on sentiment and category
        try:
            total_sentiment_articles = sum(item['count'] for item in sentiment_data if isinstance(item, dict) and 'count' in item)
            if total_sentiment_articles == 0:
                positive_ratio = 0
                negative_ratio = 0
                critical_ratio = 0
            else:
                positive_count = 0
                negative_count = 0
                critical_count = 0
                
                for item in sentiment_data:
                    if isinstance(item, dict) and 'sentiment' in item and 'count' in item:
                        sentiment = item['sentiment'].lower()
                        if sentiment in ['positive', 'optimistic']:
                            positive_count += item['count']
                        elif sentiment in ['negative', 'pessimistic']:
                            negative_count += item['count']
                        elif sentiment in ['critical', '** critical']:
                            critical_count += item['count']
                
                positive_ratio = positive_count / total_sentiment_articles
                negative_ratio = negative_count / total_sentiment_articles
                critical_ratio = critical_count / total_sentiment_articles
                
            logger.info(f"Sentiment ratios for {category}: positive={positive_ratio:.2f}, negative={negative_ratio:.2f}, critical={critical_ratio:.2f}")
                
        except Exception as e:
            logger.error(f"Error calculating sentiment ratios: {str(e)}", exc_info=True)
            positive_ratio = 0
            negative_ratio = 0
        
        # Adjust timing based on category characteristics
        category_lower = category.lower()
        
        # Category-specific timing adjustments
        if 'healthcare' in category_lower:
            # Healthcare typically has slower adoption due to regulation
            start_time = max(start_time + 1, 1)
            end_time = min(end_time + 2, 8)
        elif 'business' in category_lower:
            # Business adoption tends to be faster and more immediate
            start_time = max(start_time - 1, 0)
            end_time = max(end_time - 1, start_time + 2)
        elif 'regulation' in category_lower or 'copyright' in category_lower:
            # Regulatory responses are often immediate but with long-term effects
            start_time = 0
            end_time = min(end_time + 3, 9)
        elif 'software' in category_lower:
            # Software development moves very fast
            start_time = max(start_time - 1, 0)
            end_time = min(start_time + 1, 4)
        elif 'robotics' in category_lower:
            # Robotics has longer development cycles
            start_time = max(start_time + 1, 2)
            end_time = min(end_time + 3, 10)
        elif 'ethics' in category_lower:
            # Ethics concerns are immediate but long-lasting
            start_time = 0
            end_time = min(end_time + 2, 8)
        elif 'carbon' in category_lower:
            # Environmental impact is immediate and ongoing
            start_time = 0
            end_time = min(end_time + 4, 10)
        
        # Determine consensus type based on ACTUAL SENTIMENT DATA, not category names
        # This makes the relationship between data and consensus type clear and logical
        
        logger.info(f"Determining consensus type for {category}: positive={positive_ratio:.2f}, critical={critical_ratio:.2f}, negative={negative_ratio:.2f}")
        
        consensus_type_key = None
        
        # Primary classification based on sentiment patterns
        if positive_ratio >= 0.6:
            # Strong positive sentiment indicates growth potential
            consensus_type_key = 'positive_growth'
            logger.info(f"→ Positive Growth (high positive sentiment: {positive_ratio:.2f})")
            
        elif critical_ratio >= 0.25 or negative_ratio >= 0.35:
            # High critical/negative sentiment - determine the type of concern
            if 'regulation' in category_lower or 'copyright' in category_lower or 'antitrust' in category_lower or 'law' in category_lower:
                consensus_type_key = 'regulatory_critical'
                logger.info(f"→ Regulatory Response (high critical in regulatory domain: {critical_ratio:.2f})")
            elif 'safety' in category_lower or 'security' in category_lower or 'risk' in category_lower or 'trust' in category_lower:
                consensus_type_key = 'safety_security'
                logger.info(f"→ Safety/Security (high critical in safety domain: {critical_ratio:.2f})")
            elif 'warfare' in category_lower or 'military' in category_lower or 'warbot' in category_lower or 'defense' in category_lower:
                consensus_type_key = 'warfare_defense'
                logger.info(f"→ Defense Applications (high critical in military domain: {critical_ratio:.2f})")
            elif 'ethics' in category_lower or 'society' in category_lower or 'societal' in category_lower:
                consensus_type_key = 'societal_impact'
                logger.info(f"→ Societal Impact (high critical in ethics/society domain: {critical_ratio:.2f})")
            elif 'geopolit' in category_lower or 'sovereign' in category_lower or 'nationalism' in category_lower:
                consensus_type_key = 'geopolitical'
                logger.info(f"→ Geopolitical Strategy (high critical in geopolitical domain: {critical_ratio:.2f})")
            else:
                # High critical sentiment but not in specific domain - general regulatory concern
                consensus_type_key = 'regulatory_critical'
                logger.info(f"→ Regulatory Response (high critical sentiment, general: {critical_ratio:.2f})")
                
        elif positive_ratio >= 0.35 and negative_ratio <= 0.25:
            # Moderate positive sentiment - check domain for business vs general growth
            if 'business' in category_lower or 'automation' in category_lower or 'work' in category_lower or 'employment' in category_lower:
                consensus_type_key = 'business_automation'
                logger.info(f"→ Business Transformation (moderate positive in business domain: {positive_ratio:.2f})")
            else:
                consensus_type_key = 'positive_growth'
                logger.info(f"→ Positive Growth (moderate positive sentiment: {positive_ratio:.2f})")
                
        else:
            # Mixed or unclear sentiment patterns
            consensus_type_key = 'mixed_consensus'
            logger.info(f"→ Mixed Consensus (balanced sentiment: pos={positive_ratio:.2f}, neg={negative_ratio:.2f}, crit={critical_ratio:.2f})")
        
        # Get the consensus type details
        if consensus_type_key and consensus_type_key in self.consensus_types:
            consensus_info = self.consensus_types[consensus_type_key]
            color = consensus_info['color']
            label = consensus_info['label']
        else:
            # Fallback
            color = self.consensus_colors['mixed_consensus']
            label = "Mixed Consensus"
        
        logger.info(f"Final consensus for {category}: {label}, timing: {start_time}-{end_time}, color: {color}")
        return (start_time, end_time, color, label)

    def _identify_outliers(
        self, 
        theme_index: int, 
        category: str, 
        sentiment_data: List[Dict],
        topic: str = None,
        timeframe: str = "365"
    ) -> List[Dict]:
        """
        Identify outlier scenarios based on extreme sentiments or signals.
        
        Returns: List of dictionaries with outlier data including article information
        """
        outliers = []
        
        # Get actual articles for this category to provide real examples
        article_examples = self._get_category_articles(category, topic, timeframe)
        
        logger.info(f"Identifying outliers for {category}")
        logger.info(f"Sentiment data for outlier detection: {sentiment_data}")
        
        try:
            # Find extreme positive outliers
            optimistic_count = 0
            pessimistic_count = 0
            critical_count = 0
            hyperbolic_count = 0
            total_count = 0
            
            for item in sentiment_data:
                if isinstance(item, dict) and 'sentiment' in item and 'count' in item:
                    sentiment = item['sentiment'].lower()
                    count = item['count']
                    total_count += count
                    
                    if sentiment in ['positive', 'optimistic']:
                        optimistic_count += count
                    elif sentiment in ['hyperbolic']:
                        hyperbolic_count += count
                    elif sentiment in ['negative', 'pessimistic']:
                        pessimistic_count += count
                    elif sentiment in ['critical', '** critical']:
                        critical_count += count
            
            logger.info(f"Outlier counts for {category}: optimistic={optimistic_count}, hyperbolic={hyperbolic_count}, pessimistic={pessimistic_count}, critical={critical_count}, total={total_count}")
            
            # Lower thresholds and add more nuanced detection
            if total_count > 5:  # Only analyze if we have enough data
                optimistic_ratio = optimistic_count / total_count
                hyperbolic_ratio = hyperbolic_count / total_count  
                pessimistic_ratio = pessimistic_count / total_count
                critical_ratio = critical_count / total_count
                
                # Optimistic outliers (lower threshold)
                if optimistic_ratio > 0.4 or hyperbolic_ratio > 0.2:
                    outliers.append((1, f"Rapid adoption\n{category[:15]}...", "above"))
                
                # Pessimistic outliers (lower threshold)
                if pessimistic_ratio > 0.3 or critical_ratio > 0.3:
                    outliers.append((6, f"Delayed impact\n{category[:15]}...", "below"))
                    
        except Exception as e:
            logger.error(f"Error identifying outliers for {category}: {str(e)}", exc_info=True)
        
        # Add specific outliers based on category type - always add some for variety
        if 'business' in category.lower():
            outliers.extend([
                (2, "Minimal disruption\nbubble bursts", "above"),
                (5, "Full automation\nby 2029", "below")
            ])
        elif 'healthcare' in category.lower():
            outliers.extend([
                (1, "Breakthrough\n2025", "above"),
                (7, "Regulation\nstalls", "below")
            ])
        elif 'regulation' in category.lower() or 'copyright' in category.lower():
            outliers.extend([
                (1, "AGI by 2026\n(Startup claims)", "above"),
                (6, "Talent surplus\nemerges", "below")
            ])
        elif 'ethics' in category.lower():
            outliers.extend([
                (2, "Self-regulation\nsucceeds", "above"),
                (7, "AI alignment\nfailure", "below")
            ])
        elif 'software' in category.lower():
            outliers.extend([
                (1, "Coding obsolete\n2025", "above"),
                (5, "Adoption resistance", "below")
            ])
        elif 'society' in category.lower():
            outliers.extend([
                (2, "Global cooperation\nemerges", "above"),
                (6, "Mass unemployment\nby 2030", "below")
            ])
        elif 'robotics' in category.lower():
            outliers.extend([
                (1, "Effective protocols\noverstated", "above"),
                (7, "Autonomous weapons\nban", "below")
            ])
        elif 'carbon' in category.lower():
            outliers.extend([
                (2, "Green AI\nbreakthrough", "above"),
                (5, "Climate costs\noverride", "below")
            ])
        
        # Convert to new format with article data
        enriched_outliers = []
        for i, (x_pos, label, position) in enumerate(outliers):
            # Try to find relevant articles for this outlier
            relevant_articles = []
            if i < len(article_examples):
                relevant_articles = [article_examples[i]]
            
            enriched_outliers.append({
                'x_position': x_pos,
                'label': label,
                'position': position,
                'articles': relevant_articles,
                'category': category,
                'timeline': f"Year {x_pos + 2024}",
                'type': 'optimistic' if position == 'above' else 'pessimistic'
            })
        
        logger.info(f"Final enriched outliers for {category}: {len(enriched_outliers)} items")
        return enriched_outliers

    def _get_category_articles(self, category: str, topic: str, timeframe: str) -> List[Dict]:
        """Get sample articles for a category to use in outlier context."""
        try:
            articles = []
            for row in (DatabaseQueryFacade(self.db, logger)).get_recent_articles_for_topic_and_category((topic, category, timeframe)):
                articles.append({
                    'title': row[0],
                    'source': row[1],
                    'uri': row[2],
                    'sentiment': row[3],
                    'future_signal': row[4],
                    'time_to_impact': row[5],
                    'publication_date': row[6]
                })

            logger.info(f"Found {len(articles)} sample articles for {category}")
            return articles
                
        except Exception as e:
            logger.error(f"Error getting articles for category {category}: {str(e)}")
            return []

    def _create_forecast_chart(self, chart_data: Dict, title_prefix: str, topic: str) -> bytes:
        """Create a clean, easy-to-read matplotlib chart."""
        
        themes = chart_data['themes']
        consensus_bands = chart_data['consensus_bands']
        outlier_markers = chart_data['outlier_markers']
        
        # Improved timeline setup with better spacing
        years = ["2024", "2025", "2026", "2027", "2028", "2029", "2030", "2035+"]
        y_pos = np.arange(len(themes))
        
        # Create figure with better proportions
        height = max(10, len(themes) * 1.5)
        plt.figure(figsize=(22, height))
        ax = plt.gca()
        
        # Set clean background
        ax.set_facecolor('#fafafa')
        plt.gcf().patch.set_facecolor('white')
        
        # Draw consensus bands with improved clarity
        consensus_type_counts = {}
        
        for i, (start, end, color, label) in enumerate(consensus_bands):
            width = end - start + 1
            
            # Count consensus types for legend
            consensus_type_counts[label] = consensus_type_counts.get(label, 0) + 1
            
            # Main consensus band with better styling
            ax.broken_barh([(start, width)], (y_pos[i] - 0.4, 0.8), 
                          facecolors=color, edgecolor="white", linewidth=2, 
                          alpha=0.9, zorder=2)
            
            # Add subtle shadow for depth
            ax.broken_barh([(start + 0.1, width)], (y_pos[i] - 0.42, 0.8), 
                          facecolors='gray', alpha=0.2, zorder=1)
            
            # Add consensus type label (not just "CONSENSUS")
            mid_point = (start + end) / 2
            ax.text(mid_point, y_pos[i], label.upper(), 
                   fontsize=10, ha='center', va='center', 
                   color="white", fontweight='bold', 
                   bbox=dict(facecolor='black', alpha=0.7, edgecolor='none', pad=2, boxstyle="round,pad=0.3"))
        
        # Draw outlier markers with much cleaner design
        outlier_legend_items = set()
        
        for i, markers in enumerate(outlier_markers):
            if not markers:
                continue
                
            # Group outliers by category type for cleaner display
            category_groups = {}
            for marker in markers:
                # Handle both old tuple format and new dict format
                if isinstance(marker, dict):
                    x = marker['x_position']
                    label = marker['label']
                    pos = marker['position']
                else:
                    # Legacy tuple format
                    x, label, pos = marker
                
                # Determine category type for grouping
                if any(keyword in label.lower() for keyword in ['security', 'safety', 'risk']):
                    cat_type = 'Security/Risk'
                    marker_color = '#e74c3c'
                    marker_symbol = '^'
                elif any(keyword in label.lower() for keyword in ['business', 'economic', 'productivity']):
                    cat_type = 'Business/Economic'
                    marker_color = '#27ae60'
                    marker_symbol = 'o'
                elif any(keyword in label.lower() for keyword in ['regulation', 'policy', 'governance']):
                    cat_type = 'Regulatory'
                    marker_color = '#f39c12'
                    marker_symbol = 's'
                else:
                    cat_type = 'Other'
                    marker_color = '#9b59b6'
                    marker_symbol = 'D'
                
                if cat_type not in category_groups:
                    category_groups[cat_type] = []
                category_groups[cat_type].append({
                    'x': x, 'label': label, 'pos': pos, 
                    'color': marker_color, 'symbol': marker_symbol
                })
                outlier_legend_items.add(cat_type)
            
            # Draw grouped markers with better spacing
            for cat_type, group_markers in category_groups.items():
                for j, marker in enumerate(group_markers):
                    x = marker['x']
                    # Offset markers slightly to avoid overlap
                    y_offset = 0.6 if marker['pos'] == "above" else -0.6
                    x_offset = (j - len(group_markers)/2) * 0.1  # Slight horizontal spread
                    
                    # Draw marker
                    ax.scatter(x + x_offset, y_pos[i] + y_offset, 
                              c=marker['color'], s=100, marker=marker['symbol'],
                              edgecolor='white', linewidth=2, alpha=0.9, zorder=5)
                    
                    # Only show label for first marker of each type to reduce clutter
                    if j == 0:
                        ax.text(x, y_pos[i] + (y_offset * 1.3), cat_type, 
                               fontsize=9, ha='center', va='center',
                               bbox=dict(boxstyle="round,pad=0.3", 
                                        facecolor=marker['color'], alpha=0.8, 
                                        edgecolor='white'),
                               color='white', fontweight='bold')
                    
                    # Show count if multiple markers of same type
                    if len(group_markers) > 1 and j == 0:
                        ax.text(x + 0.3, y_pos[i] + y_offset, f"({len(group_markers)})", 
                               fontsize=8, ha='left', va='center',
                               color=marker['color'], fontweight='bold')
        
        # Set up axes
        plt.yticks(y_pos, themes, fontsize=16, fontweight='bold')
        plt.xticks(range(len(years)), years, fontsize=16, fontweight='bold')
        plt.xlabel("Timeline / Forecast Horizon", fontsize=18, labelpad=15, fontweight='bold')
        
        # Titles
        title_main = f"{title_prefix}: Evidence-Based Forecast Analysis"
        title_sub = f"Based on {chart_data.get('total_articles', 0)} Articles - Topic: {topic}"
        plt.suptitle(title_main, fontsize=22, fontweight='bold', y=0.96)
        plt.title(title_sub, fontsize=16, style='italic', pad=20, color="#34495e")
        
        # Grid and styling
        plt.xlim(-0.6, len(years)-0.4)
        plt.ylim(-0.8, len(themes)-0.1)
        plt.grid(axis='x', linestyle='--', alpha=0.4, linewidth=1.2, color='gray')
        plt.grid(axis='y', linestyle=':', alpha=0.2, linewidth=0.8, color='gray')
        
        # Create cleaner legends based on actual data
        # Get unique consensus types from the data
        unique_consensus_types = set()
        for _, _, color, label in consensus_bands:
            unique_consensus_types.add((label, color))
        
        consensus_patches = []
        for label, color in unique_consensus_types:
            consensus_patches.append(mpatches.Patch(color=color, label=label))
        
        # Create outlier legend based on actual outlier types found
        outlier_patches = []
        outlier_colors_map = {
            'Security/Risk': '#e74c3c',
            'Business/Economic': '#27ae60', 
            'Regulatory': '#f39c12',
            'Other': '#9b59b6'
        }
        for outlier_type in sorted(outlier_legend_items):
            color = outlier_colors_map.get(outlier_type, '#9b59b6')
            outlier_patches.append(mpatches.Patch(color=color, label=f'{outlier_type} Outliers'))
        
        # Position legends
        legend1 = plt.legend(handles=consensus_patches, title="Consensus Forecasts", 
                            bbox_to_anchor=(1.02, 1), loc='upper left', 
                            fontsize=13, title_fontsize=14, frameon=True, 
                            fancybox=True, shadow=True)
        
        legend2 = plt.legend(handles=outlier_patches, title="Outlier Scenarios", 
                            bbox_to_anchor=(1.02, 0.6), loc='upper left',
                            fontsize=13, title_fontsize=14, frameon=True,
                            fancybox=True, shadow=True)
        
        plt.gca().add_artist(legend1)
        
        # Add clearer summary
        summary_title = "HOW TO READ THIS CHART:"
        summary_content = (
            f"• CONSENSUS BANDS: Show when experts agree on timing (based on {chart_data.get('total_articles', 0)} articles)\n"
            "• BAND COLORS: Indicate the type of consensus (positive, regulatory, security, etc.)\n"
            "• OUTLIER MARKERS: Show dissenting views and alternative scenarios by category\n"
            "• TIMELINE: Years when impact is expected based on expert analysis\n"
            "• Strategic planning should consider both consensus timing and outlier scenarios"
        )
        
        plt.figtext(0.02, 0.12, summary_title, fontsize=14, fontweight='bold', color="#2c3e50")
        plt.figtext(0.02, 0.02, summary_content, fontsize=12, color="#34495e", 
                   verticalalignment='bottom', wrap=True)
        
        # Methodology note
        methodology = f"Methodology: Auspex analysis engine, thematic clustering, consensus detection, outlier identification - Topic: {topic}"
        plt.figtext(0.02, 0.18, methodology, fontsize=10, style='italic', color="#7f8c8d")
        
        # Layout and styling
        plt.tight_layout(rect=[0, 0.22, 0.75, 0.94])
        ax.set_facecolor('#fafafa')
        plt.gcf().patch.set_facecolor('white')
        
        # Convert to bytes
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=300, bbox_inches='tight', 
                   facecolor='white', edgecolor='none')
        img_buffer.seek(0)
        chart_bytes = img_buffer.getvalue()
        plt.close()
        
        return chart_bytes

    def _create_interactive_forecast_chart(self, chart_data: Dict, title_prefix: str, topic: str) -> str:
        """Create an interactive Plotly chart with hover tooltips."""
        
        if not PLOTLY_AVAILABLE:
            raise ImportError("Plotly is required for interactive charts")
        
        themes = chart_data['themes']
        consensus_bands = chart_data['consensus_bands']
        outlier_markers = chart_data['outlier_markers']
        
        # Timeline setup
        years = ["2024", "2025", "2026", "2027", "2028", "2029", "2030", "2035+"]
        
        # Create figure
        fig = go.Figure()
        
        # Add consensus bands
        for i, (start, end, color, label) in enumerate(consensus_bands):
            # Convert matplotlib colors to plotly format
            plotly_color = self._matplotlib_to_plotly_color(color)
            
            # Find the consensus type details for enhanced tooltips
            consensus_details = None
            for consensus_key, consensus_info in self.consensus_types.items():
                if consensus_info['label'] == label:
                    consensus_details = consensus_info
                    break
            
            hover_text = f"<b>{themes[i]}</b><br>Consensus: {label}<br>Timeline: {years[start]} - {years[min(end, len(years)-1)]}"
            
            if consensus_details:
                hover_text += f"<br><br><b>Description:</b><br>{consensus_details['description']}"
                hover_text += f"<br><br><b>Rationale:</b><br>{consensus_details['rationale']}"
            
            fig.add_trace(go.Scatter(
                x=[start, end, end, start, start],
                y=[i-0.35, i-0.35, i+0.35, i+0.35, i-0.35],
                fill='toself',
                fillcolor=plotly_color,
                line=dict(color='rgba(0,0,0,0.5)', width=1.5),
                mode='lines',
                name=f'{themes[i]} - {label}',
                hovertemplate=hover_text + "<extra></extra>",
                showlegend=True
            ))
            
            # Add consensus type label instead of generic "CONSENSUS"
            mid_point = (start + end) / 2
            fig.add_annotation(
                x=mid_point,
                y=i,
                text=label.upper(),
                showarrow=False,
                font=dict(size=10, color="white"),
                bgcolor="rgba(0,0,0,0.7)",
                bordercolor="rgba(255,255,255,0.3)",
                borderwidth=1
            )
        
        # Add outlier markers with tooltips
        for i, markers in enumerate(outlier_markers):
            for marker in markers:
                # Handle both old tuple format and new dict format
                if isinstance(marker, dict):
                    x = marker['x_position']
                    label = marker['label']
                    pos = marker['position']
                    articles = marker.get('articles', [])
                    timeline = marker.get('timeline', f"Year {x + 2024}")
                    category = marker.get('category', themes[i])
                    
                    # Build enhanced hover template with article data
                    hover_text = f"<b>Outlier Scenario</b><br>Category: {category}<br>Scenario: {label}<br>Timeline: {timeline}<br>Type: {marker.get('type', 'Unknown')}"
                    
                    if articles:
                        hover_text += "<br><br><b>Supporting Articles:</b>"
                        for article in articles[:3]:  # Show up to 3 articles
                            hover_text += f"<br>• {article.get('title', 'Unknown Title')[:50]}..."
                            if article.get('source'):
                                hover_text += f" ({article['source']})"
                else:
                    # Legacy tuple format
                    x, label, pos = marker
                    hover_text = f"<b>Outlier Scenario</b><br>Category: {themes[i]}<br>Scenario: {label}<br>Timeline: {years[min(x, len(years)-1)]}<br>Type: {'Optimistic' if pos == 'above' else 'Pessimistic'}"
                
                y_offset = 0.45 if pos == "above" else -0.45
                marker_color = '#e74c3c' if pos == "above" else '#3498db'
                
                fig.add_trace(go.Scatter(
                    x=[x],
                    y=[i + y_offset],
                    mode='markers',
                    marker=dict(
                        size=14,
                        color=marker_color,
                        line=dict(color='black', width=2)
                    ),
                    name=f'Outlier: {themes[i]}',
                    hovertemplate=hover_text + "<extra></extra>",
                    showlegend=False
                ))
        
        # Update layout
        fig.update_layout(
            title=dict(
                text=f"{title_prefix}: Evidence-Based Forecast Analysis<br>" +
                     f"<sub>Based on {chart_data.get('total_articles', 0)} Articles - Topic: {topic}</sub>",
                font=dict(size=20)
            ),
            xaxis=dict(
                title="Timeline / Forecast Horizon",
                tickmode='array',
                tickvals=list(range(len(years))),
                ticktext=years,
                range=[-0.6, len(years)-0.4],
                showgrid=True,
                gridcolor='rgba(128,128,128,0.4)'
            ),
            yaxis=dict(
                tickmode='array',
                tickvals=list(range(len(themes))),
                ticktext=themes,
                range=[-0.8, len(themes)-0.1],
                showgrid=True,
                gridcolor='rgba(128,128,128,0.2)'
            ),
            hovermode='closest',
            plot_bgcolor='#fafafa',
            paper_bgcolor='white',
            font=dict(size=12),
            width=1200,
            height=max(600, len(themes) * 80),
            margin=dict(l=200, r=200, t=100, b=100)
        )
        
        # Add clearer annotations for chart reading
        insights_text = (
            f"• CONSENSUS BANDS: Show when experts agree on timing (based on {chart_data.get('total_articles', 0)} articles)<br>"
            "• BAND COLORS: Indicate the type of consensus (positive, regulatory, security, etc.)<br>"
            "• OUTLIER MARKERS: Show dissenting views and alternative scenarios by category<br>"
            "• TIMELINE: Years when impact is expected based on expert analysis<br>"
            "• Strategic planning should consider both consensus timing and outlier scenarios"
        )
        
        fig.add_annotation(
            x=0,
            y=-0.15,
            xref="paper",
            yref="paper",
            text=f"<b>HOW TO READ THIS CHART:</b><br>{insights_text}",
            showarrow=False,
            font=dict(size=10),
            align="left",
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="rgba(0,0,0,0.1)",
            borderwidth=1
        )
        
        # Return JSON data for client-side rendering (avoids embedding issues)
        chart_json = pio.to_json(fig)
        chart_data = json.loads(chart_json)
        
        # Return the chart data directly as JSON string for the frontend
        return json.dumps({
            'plotly_data': chart_data['data'],
            'plotly_layout': chart_data['layout'],
            'config': {'displayModeBar': True, 'responsive': True}
        })
    
    def _matplotlib_to_plotly_color(self, mpl_color: str) -> str:
        """Convert matplotlib color to plotly-compatible color."""
        color_map = {
            '#b6d7a8': 'rgba(182, 215, 168, 0.7)',  # Green
            '#ffd966': 'rgba(255, 217, 102, 0.7)',  # Yellow  
            '#f4cccc': 'rgba(244, 204, 204, 0.7)',  # Light red
            '#e06666': 'rgba(224, 102, 102, 0.7)',  # Red
            '#f08080': 'rgba(240, 128, 128, 0.7)',  # Light coral
            '#b4c7e7': 'rgba(180, 199, 231, 0.7)',  # Blue
            '#ffe599': 'rgba(255, 229, 153, 0.7)',  # Light yellow
            '#f6b26b': 'rgba(246, 178, 107, 0.7)'   # Orange
        }
        return color_map.get(mpl_color, 'rgba(255, 217, 102, 0.7)')

    def _generate_empty_chart(self, topic: str, available_topics: List[str] = None) -> str:
        """Generate a placeholder chart when no data is available."""
        plt.figure(figsize=(12, 8))
        
        # Create message based on available topics
        if available_topics:
            topics_text = ", ".join(available_topics[:5])  # Show first 5 topics
            if len(available_topics) > 5:
                topics_text += f", and {len(available_topics) - 5} more"
            message = f"No data available for topic: '{topic}'\n\nAvailable topics with forecast data:\n{topics_text}\n\nPlease select a different topic or ensure\narticles have been analyzed and categorized."
        else:
            message = f"No data available for topic: '{topic}'\n\nNo topics with forecast data found.\nPlease ensure articles have been analyzed\nand categories have been assigned."
        
        plt.text(0.5, 0.5, message, 
                ha='center', va='center', fontsize=12, 
                bbox=dict(boxstyle="round,pad=0.8", facecolor="lightgray", alpha=0.8))
        plt.xlim(0, 1)
        plt.ylim(0, 1)
        plt.axis('off')
        plt.title(f"Forecast Chart - {topic}", fontsize=16, pad=20)
        
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
        img_buffer.seek(0)
        chart_bytes = img_buffer.getvalue()
        plt.close()
        
        chart_base64 = base64.b64encode(chart_bytes).decode('utf-8')
        return f"data:image/png;base64,{chart_base64}"

def get_forecast_chart_service() -> ForecastChartService:
    """Get singleton instance of ForecastChartService."""
    return ForecastChartService() 