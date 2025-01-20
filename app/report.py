import markdown
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from collections import defaultdict
import logging
import json

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
class Report:
    def __init__(self, db):
        self.db = db
        # Load the categories template
        try:
            with open('app/config/templates.json', 'r') as f:
                templates = json.load(f)
                self.categories_template = templates['report_sections']['categories']
        except Exception as e:
            logger.error(f"Error loading categories template: {e}")
            # Fallback template if loading fails
            self.categories_template = "## {category}\n\n### {title}\n\n**Source:** {news_source} | [Link]({url})\n\n{summary}\n\n"

    def generate_report(self, article_ids: List[str], custom_sections: Optional[Dict] = None) -> str:
        try:
            logger.debug(f"Starting report generation with custom sections: {custom_sections}")
            articles = self.get_articles_by_ids(article_ids)
            logger.debug(f"Retrieved {len(articles)} articles")
            
            # Ensure custom_sections is a dictionary
            custom_sections = custom_sections or {}
            logger.debug(f"Using custom sections: {custom_sections}")
            
            # Generate section data
            section_data = self._generate_section_data(articles, custom_sections)
            logger.debug(f"Generated section data with keys: {section_data.keys()}")
            
            # Build the report content based on selected sections
            content = []
            
            # Add title
            content.append(f"# {section_data['title']}\n")
            logger.debug("Added title to content")
            
            # Add overview if requested
            if custom_sections.get('include_overview'):
                logger.debug("Adding overview section")
                content.append("\n## Overview\n")
                content.append(section_data.get('overview', ''))
                content.append("\n")
            
            # Add categories (always included)
            logger.debug("Adding categories section")
            content.append("\n## Categories\n")
            content.append(section_data.get('categories', ''))
            content.append("\n")
            
            # Add analysis if requested
            if custom_sections.get('include_analysis'):
                logger.debug("Adding analysis section")
                content.append("\n## Analysis\n")
                content.append(section_data.get('analysis', ''))
                content.append("\n")
            
            # Add sources if requested
            if custom_sections.get('include_sources'):
                logger.debug("Adding sources section")
                content.append("\n## Sources\n")
                content.append(section_data.get('sources', ''))
                content.append("\n")
            
            final_content = "\n".join(content)
            logger.debug(f"Final report length: {len(final_content)}")
            return final_content
            
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            raise

    def _generate_categories_section(self, articles_by_category: Dict[str, List[Dict]]) -> str:
        try:
            with open('app/config/templates.json', 'r') as f:
                templates = json.load(f)
                article_template = templates['report_sections']['categories']
            
            content = []
            # Process one category at a time
            for category, articles in articles_by_category.items():
                # Add category header once
                content.append(f"# {category}\n")
                
                # Add all articles under this category
                for article in articles:
                    article_data = {
                        'title': article.get('title', 'Untitled'),
                        'news_source': article.get('news_source', 'Unknown'),
                        'url': article.get('url', ''),
                        'summary': article.get('summary', ''),
                        'sentiment': article['sentiment'],
                        'time_to_impact': article['time_to_impact'],
                        'future_signal': article['future_signal']
                    }
                    # Remove category from template formatting since it's now in the header
                    formatted_article = article_template.replace('{category}\n', '')
                    content.append(formatted_article.format(**article_data))
                
                content.append("\n")  # Add spacing between categories
            
            return '\n'.join(content)
        except Exception as e:
            logger.error(f"Error generating categories section: {e}")
            raise

    def _generate_overview_section(self, articles: List[Dict]) -> str:
        try:
            total_articles = len(articles)
            date_range = self._get_date_range(articles)
            sources = len(set(a['news_source'] for a in articles))
            
            overview = f"This report analyzes {total_articles} articles from {sources} different sources, published between {date_range['start']} and {date_range['end']}."
            
            logger.debug(f"Generated overview section: {overview}")
            return overview
        except Exception as e:
            logger.error(f"Error generating overview section: {e}")
            raise

    def _generate_analysis_section(self, articles: List[Dict]) -> str:
        try:
            sentiment_counts = defaultdict(int)
            future_signals = defaultdict(int)
            
            for article in articles:
                sentiment_counts[article['sentiment']] += 1
                future_signals[article['future_signal']] += 1
                
            analysis = f"""## Sentiment Distribution\n{self._format_counts(sentiment_counts)}\n\n
                        ## Future Signals\n{self._format_counts(future_signals)}"""
            
            logger.debug(f"Generated analysis section: {analysis}")
            return analysis
        except Exception as e:
            logger.error(f"Error generating analysis section: {e}")
            raise

    def _generate_sources_section(self, articles: List[Dict]) -> str:
        sources = defaultdict(int)
        for article in articles:
            sources[article['news_source']] += 1
        return self._format_counts(sources)

    @staticmethod
    def _format_counts(counts: Dict) -> str:
        total = sum(counts.values())
        return "\n".join(f"- {k}: {v} ({v/total*100:.1f}%)" for k, v in counts.items())

    @staticmethod
    def _get_date_range(articles: List[Dict]) -> Dict:
        dates = [datetime.strptime(a['publication_date'], '%Y-%m-%d') for a in articles]
        return {
            'start': min(dates).strftime('%Y-%m-%d'),
            'end': max(dates).strftime('%Y-%m-%d')
        }

    def _generate_section_data(self, articles: List[Dict], custom_sections: Optional[Dict] = None) -> Dict:
        try:
            logger.debug(f"Starting _generate_section_data with custom sections: {custom_sections}")
            articles_by_category = defaultdict(list)
            for article in articles:
                articles_by_category[article['category']].append(article)
            
            # Initialize with required sections
            section_data = {
                'title': f"News Analysis Report - {datetime.now().strftime('%Y-%m-%d')}",
                'categories': self._generate_categories_section(articles_by_category),
            }
            logger.debug("Generated base section data")
            
            # Generate optional sections if requested
            if custom_sections:
                logger.debug("Processing optional sections")
                if custom_sections.get('include_overview', False):
                    logger.debug("Generating overview section")
                    section_data['overview'] = self._generate_overview_section(articles)
                    logger.debug(f"Overview section length: {len(section_data['overview'])}")
                    
                if custom_sections.get('include_analysis', False):
                    logger.debug("Generating analysis section")
                    section_data['analysis'] = self._generate_analysis_section(articles)
                    logger.debug(f"Analysis section length: {len(section_data['analysis'])}")
                    
                if custom_sections.get('include_sources', False):
                    logger.debug("Generating sources section")
                    section_data['sources'] = self._generate_sources_section(articles)
                    logger.debug(f"Sources section length: {len(section_data['sources'])}")
            
            logger.debug(f"Final section_data keys: {section_data.keys()}")
            logger.debug(f"Section data content lengths: {[(k, len(str(v))) for k, v in section_data.items()]}")
            return section_data
            
        except Exception as e:
            logger.error(f"Error in _generate_section_data: {e}")
            raise

    def get_articles_by_ids(self, article_ids: List[str]) -> List[Dict]:
        """Fetch articles from database by their IDs"""
        try:
            articles = []
            for article_id in article_ids:
                article = self.db.get_article(article_id)
                if article:
                    # Ensure URL is present by using URI if URL is missing
                    if 'url' not in article and 'uri' in article:
                        article['url'] = article['uri']
                    articles.append(article)
            return articles
        except Exception as e:
            logger.error(f"Error fetching articles: {e}")
            return []

