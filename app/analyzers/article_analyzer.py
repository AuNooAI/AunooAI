from typing import Dict, List, Optional
from datetime import datetime, timezone
import logging
from urllib.parse import urlparse
import hashlib
from .prompt_templates import PromptTemplates, PromptTemplateError
from .cache import AnalysisCache, CacheError
import json
import traceback
import re

logger = logging.getLogger(__name__)

class ArticleAnalyzerError(Exception):
    pass

class ArticleAnalyzer:
    DATE_FORMATS = [
        '%Y-%m-%d',           # 2024-03-14
        '%Y/%m/%d',           # 2024/03/14
        '%d-%m-%Y',           # 14-03-2024
        '%d/%m/%Y',           # 14/03/2024
        '%Y-%m-%dT%H:%M:%S',  # 2024-03-14T15:30:00
        '%Y-%m-%dT%H:%M:%S.%f%z',  # 2024-03-14T15:30:00.000Z
        '%Y-%m-%dT%H:%M:%SZ', # 2024-03-14T15:30:00Z
        '%B %d, %Y',          # March 14, 2024
        '%d %B %Y',           # 14 March 2024
        '%d %B, %Y',          # 14 March, 2024
        '%Y-%m-%d %H:%M:%S',  # 2024-03-14 15:30:00
        '%d %B %Y',           # 06 December 2024
        '%d-%B-%Y',           # 06-December-2024
        '%d %b %Y',           # 06 Dec 2024
        '%d-%b-%Y',           # 06-Dec-2024
        '%b %d, %Y',          # Dec 06, 2024
        '%B %d, %Y',          # December 06, 2024
    ]
    
    DATE_PATTERNS = [
        r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
        r'\d{2}/\d{2}/\d{4}',  # DD/MM/YYYY
        r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}'  # Month DD, YYYY
    ]

    DATE_EXTRACTION_TEMPLATE = """
Extract the publication date from the following article text. 
Return ONLY the date in YYYY-MM-DD format. If no date is found, return today's date.

Article text:
{content}
"""

    def __init__(self, ai_model, custom_templates_path: str = None, cache_dir: str = "cache", cache_ttl_hours: int = 24, use_cache: bool = True):
        if not ai_model:
            raise ArticleAnalyzerError("AI model is required")
        self.ai_model = ai_model
        # Store model name for cache key
        self.model_name = getattr(ai_model, 'model_name', 'default')
        self.use_cache = use_cache
        logger.debug(f"Initialized ArticleAnalyzer with model={self.model_name}, use_cache={self.use_cache}")
        try:
            self.prompt_templates = PromptTemplates(custom_templates_path)
            self.cache = AnalysisCache(cache_dir, cache_ttl_hours)
        except (PromptTemplateError, CacheError) as e:
            logger.error(f"Failed to initialize: {str(e)}")
            raise ArticleAnalyzerError(f"Failed to initialize: {str(e)}")

    def _compute_content_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def extract_title(self, article_text: str) -> str:
        """Extract or generate a title from the article text."""
        if not article_text:
            raise ArticleAnalyzerError("Article text cannot be empty")

        try:
            prompts = self.prompt_templates.format_title_prompt(article_text)
            title_response = self.ai_model.generate_response(prompts)
            self._extracted_title = title_response.strip()  # Store for potential fallback
            return self._extracted_title
        except PromptTemplateError as e:
            logger.error(f"Error with prompt template: {str(e)}")
            raise ArticleAnalyzerError(f"Failed to extract title: {str(e)}")
        except Exception as e:
            logger.error(f"Error extracting title: {str(e)}")
            raise ArticleAnalyzerError(f"Failed to extract title: {str(e)}")

    def analyze_content(self, article_text: str, title: str, source: str, uri: str, 
                       summary_length: int, summary_voice: str, summary_type: str,
                       categories: List[str], future_signals: List[str], 
                       sentiment_options: List[str], time_to_impact_options: List[str],
                       driver_types: List[str]) -> Dict:

        # Validate inputs
        if not article_text:
            raise ArticleAnalyzerError("Article text cannot be empty")
        if not title:
            raise ArticleAnalyzerError("Title cannot be empty")
        if not source:
            raise ArticleAnalyzerError("Source cannot be empty")
        if not uri:
            raise ArticleAnalyzerError("URI cannot be empty")
        if not categories:
            raise ArticleAnalyzerError("Categories list cannot be empty")
        if not future_signals:
            raise ArticleAnalyzerError("Future signals list cannot be empty")
        if not sentiment_options:
            raise ArticleAnalyzerError("Sentiment options list cannot be empty")
        if not time_to_impact_options:
            raise ArticleAnalyzerError("Time to impact options list cannot be empty")
        if not driver_types:
            raise ArticleAnalyzerError("Driver types list cannot be empty")

        try:
            # Get template hash for cache validation
            template_hash = self.prompt_templates.get_template_hash()

            # Check cache first
            if self.use_cache:
                logger.debug(f"Cache check enabled for model {self.model_name}")
                content_hash = self._compute_content_hash(article_text)
                cache_key = f"{uri}_{self.model_name}"
                logger.debug(f"Checking cache with key: {cache_key}, content_hash: {content_hash}")
                cached_result = self.cache.get(cache_key, content_hash, template_hash)
                
                if cached_result:
                    cached_model = cached_result.get('model_name')
                    logger.debug(f"Found cached result for model {cached_model}, current model is {self.model_name}")
                    if cached_model == self.model_name:
                        logger.info(f"Using cached analysis for {uri} with model {self.model_name}")
                        cached_result["uri"] = uri
                        return cached_result
                    else:
                        logger.debug(f"Cache hit but model mismatch. Cached: {cached_model}, Current: {self.model_name}")
            else:
                logger.debug(f"Cache check disabled for model {self.model_name}")

            prompts = self.prompt_templates.format_analysis_prompt(
                article_text=article_text,
                title=title,
                source=source,
                uri=uri,
                summary_length=summary_length,
                summary_voice=summary_voice,
                summary_type=summary_type,
                categories=categories,
                future_signals=future_signals,
                sentiment_options=sentiment_options,
                time_to_impact_options=time_to_impact_options,
                driver_types=driver_types
            )

            logger.debug(f"Sending prompt to AI model: {prompts}")
            analysis = self.ai_model.generate_response(prompts)
            logger.debug(f"Received AI response: {analysis}")

            if not analysis:
                raise ArticleAnalyzerError("Failed to generate analysis")

            result = self.parse_analysis(analysis)
            
            # Add uri and publication_date to result
            result["uri"] = uri
            # Extract publication date using only article_text
            result["publication_date"] = self.extract_publication_date(article_text)
            
            logger.debug(f"Parsed analysis result: {json.dumps(result, indent=2)}")

            # When storing the result, include the model name
            result['model_name'] = self.ai_model.model_name
            if self.use_cache:
                try:
                    content_hash = self._compute_content_hash(article_text)
                    cache_key = f"{uri}_{self.ai_model.model_name}"
                    self.cache.set(cache_key, content_hash, result, template_hash)
                except CacheError as e:
                    logger.warning(f"Failed to cache analysis: {str(e)}")

            return result
        except PromptTemplateError as e:
            logger.error(f"Error with prompt template: {str(e)}")
            raise ArticleAnalyzerError(f"Failed to analyze content: {str(e)}")
        except Exception as e:
            logger.error(f"Error analyzing content: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise ArticleAnalyzerError(f"Failed to analyze content: {str(e)}")

    def parse_analysis(self, analysis: str) -> Dict:
        if not analysis:
            return {}

        try:
            # Split the analysis into lines and clean them
            lines = [line.strip() for line in analysis.split('\n') if line.strip()]
            logger.debug(f"Analysis lines: {lines}")

            parsed_analysis = {}
            current_key = None
            current_value = []

            for line in lines:
                if ':' in line:
                    # If we have a previous key, save its value
                    if current_key:
                        parsed_analysis[current_key] = '\n'.join(current_value).strip()
                    
                    # Start a new key
                    key, value = line.split(':', 1)
                    # Remove any asterisks and whitespace from key
                    current_key = key.strip().strip('*').strip()
                    current_value = [value.strip()]
                elif current_key:
                    # Continue with previous key
                    current_value.append(line.strip())

            # Save the last key's value
            if current_key:
                parsed_analysis[current_key] = '\n'.join(current_value).strip()

            logger.debug(f"Initial parsed analysis: {json.dumps(parsed_analysis, indent=2)}")

            # If Title is missing and we have an extracted title, use it as fallback
            if "Title" not in parsed_analysis and hasattr(self, '_extracted_title') and self._extracted_title:
                logger.debug(f"Using extracted title as fallback: {self._extracted_title}")
                parsed_analysis["Title"] = self._extracted_title

            # Validate required fields
            required_fields = ["Title", "Summary", "Category", "Future Signal", 
                             "Future Signal Explanation", "Sentiment", "Time to Impact", 
                             "Driver Type", "Tags"]
            
            missing_fields = [field for field in required_fields if field not in parsed_analysis]
            if missing_fields:
                logger.error(f"Missing fields in analysis: {missing_fields}")
                logger.error(f"Available fields: {list(parsed_analysis.keys())}")
                raise ArticleAnalyzerError(f"Missing required fields in analysis: {', '.join(missing_fields)}")

            # Convert keys to expected format
            key_mapping = {
                "Title": "title",
                "Summary": "summary",
                "Category": "category",
                "Future Signal": "future_signal",
                "Future Signal Explanation": "future_signal_explanation",
                "Sentiment": "sentiment",
                "Sentiment Explanation": "sentiment_explanation",
                "Time to Impact": "time_to_impact",
                "Time to Impact Explanation": "time_to_impact_explanation",
                "Driver Type": "driver_type",
                "Driver Type Explanation": "driver_type_explanation",
                "Tags": "tags",
                "Publication Date": "publication_date"
            }

            result = {}
            for old_key, value in parsed_analysis.items():
                if old_key in key_mapping:
                    new_key = key_mapping[old_key]
                    # Handle tags specially
                    if new_key == "tags":
                        # Convert string of comma-separated tags into a list
                        tags_str = value.strip('[]')  # Remove square brackets if present
                        result[new_key] = self.format_tags(tags_str)
                    else:
                        result[new_key] = value

            logger.debug(f"Final parsed result: {json.dumps(result, indent=2)}")
            return result
        except ArticleAnalyzerError:
            raise
        except Exception as e:
            logger.error(f"Error parsing analysis: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise ArticleAnalyzerError(f"Failed to parse analysis: {str(e)}")

    def truncate_text(self, text: str, max_chars: int = 65000) -> str:
        if not text:
            return ""
        if not isinstance(max_chars, int) or max_chars <= 0:
            raise ArticleAnalyzerError("max_chars must be a positive integer")

        if len(text) > max_chars:
            return text[:max_chars] + "..."
        return text

    def format_tags(self, tags_input) -> List[str]:
        if not tags_input:
            return []

        try:
            # If already a list, clean each tag
            if isinstance(tags_input, list):
                return [tag.strip().replace(' ', '') for tag in tags_input if tag.strip()]
            
            # If string, remove brackets and split by commas
            if isinstance(tags_input, str):
                tags = tags_input.strip('[]').split(',')
                return [tag.strip().replace(' ', '') for tag in tags if tag.strip()]
            
            raise ArticleAnalyzerError(f"Invalid tags input type: {type(tags_input)}")
        except Exception as e:
            logger.error(f"Error formatting tags: {str(e)}")
            raise ArticleAnalyzerError(f"Failed to format tags: {str(e)}")

    def truncate_summary(self, summary: str, max_words: int) -> str:
        if not summary:
            return ""
        if not isinstance(max_words, int) or max_words <= 0:
            raise ArticleAnalyzerError("max_words must be a positive integer")

        summary_words = summary.split()
        if len(summary_words) > max_words:
            return ' '.join(summary_words[:max_words])
        return summary

    def get_cache_stats(self) -> Dict:
        try:
            return self.cache.get_stats()
        except CacheError as e:
            logger.error(f"Error getting cache stats: {str(e)}")
            raise ArticleAnalyzerError(f"Failed to get cache stats: {str(e)}")

    def clear_cache(self) -> None:
        try:
            self.cache.clear()
        except CacheError as e:
            logger.error(f"Error clearing cache: {str(e)}")
            raise ArticleAnalyzerError(f"Failed to clear cache: {str(e)}")

    def cleanup_expired_cache(self) -> int:
        try:
            return self.cache.cleanup_expired()
        except CacheError as e:
            logger.error(f"Error cleaning up expired cache: {str(e)}")
            raise ArticleAnalyzerError(f"Failed to clean up expired cache: {str(e)}")

    def get_template_version(self, template_name: str) -> str:
        try:
            return self.prompt_templates.get_template_version(template_name)
        except PromptTemplateError as e:
            logger.error(f"Error getting template version: {str(e)}")
            raise ArticleAnalyzerError(f"Failed to get template version: {str(e)}")

    def get_template_hash(self) -> str:
        return self.prompt_templates.get_template_hash() 

    def extract_publication_date(self, content: str) -> str:
        try:
            # Use managed prompt template for date extraction
            prompts = self.prompt_templates.format_date_extraction_prompt(content)
            ai_extracted_date = self.ai_model.generate_response(prompts)
            
            if ai_extracted_date:
                logger.debug(f"AI extracted date: {ai_extracted_date}")
                try:
                    parsed_date = datetime.strptime(ai_extracted_date.strip(), '%Y-%m-%d')
                    return parsed_date.date().isoformat()
                except ValueError:
                    pass

            # If AI extraction fails, return current date
            logger.debug(f"Using todays date")
            return datetime.now(timezone.utc).date().isoformat()
            
        except Exception as e:
            logger.warning(f"Error extracting publication date: {str(e)}")
            return datetime.now(timezone.utc).date().isoformat() 

    #logger.debug(f"AI extracted date: {ai_extracted_date}") 