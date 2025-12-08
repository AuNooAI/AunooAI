import json
import logging
import re
from typing import Dict, List, Optional, Tuple
from app.analyzers.prompt_templates import PromptTemplates, PromptTemplateError
from app.ai_models import get_ai_model, LiteLLMModel
from app.exceptions import PipelineError, ErrorSeverity, LLMErrorClassifier
import litellm

logger = logging.getLogger(__name__)


def _parse_llm_json(raw_content: str) -> dict:
    """Parse JSON from LLM response, handling common issues with local models (Ollama/vLLM).

    Handles:
    - <think>...</think> blocks from Qwen3 models
    - Truncated JSON responses
    - Control characters in strings
    - Malformed JSON with regex fallback for key fields
    """
    if not raw_content or not raw_content.strip():
        raise ValueError("Empty response from LLM")

    # Strip <think>...</think> blocks (Qwen3 thinking mode)
    content = re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL).strip()
    if not content:
        content = raw_content

    # Find JSON object
    start = content.find('{')
    end = content.rfind('}')

    # Handle truncated JSON (no closing brace)
    if start != -1 and (end == -1 or end <= start):
        # Try to repair truncated JSON by closing it
        json_str = content[start:]
        # Count unclosed braces and brackets
        brace_count = json_str.count('{') - json_str.count('}')
        bracket_count = json_str.count('[') - json_str.count(']')

        # Check if we're in an incomplete string
        in_string = False
        last_char = ''
        for c in json_str:
            if c == '"' and last_char != '\\':
                in_string = not in_string
            last_char = c

        # Close incomplete string if needed
        if in_string:
            json_str += '"'

        # Close any open arrays/objects
        json_str += ']' * bracket_count
        json_str += '}' * brace_count

        logger.warning(f"Attempted to repair truncated JSON (added {brace_count} braces, {bracket_count} brackets)")
    elif start == -1:
        raise ValueError("No JSON object found in response")
    else:
        json_str = content[start:end+1]

    # First try direct parsing
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Try with strict=False to allow control characters
    try:
        return json.loads(json_str, strict=False)
    except json.JSONDecodeError:
        pass

    # Clean up: replace literal newlines/tabs with escaped versions
    cleaned = json_str.replace('\n', '\\n').replace('\t', '\\t').replace('\r', '\\r')
    try:
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        pass

    # Last resort: try to extract key fields using regex
    # This handles cases where JSON is mostly valid but has corruption
    result = {}

    # Extract numeric scores
    for field in ['topic_alignment_score', 'keyword_relevance_score', 'confidence_score']:
        match = re.search(rf'"{field}"\s*:\s*([\d.]+)', content)
        if match:
            try:
                result[field] = float(match.group(1))
            except ValueError:
                pass

    # Extract overall_match_explanation
    match = re.search(r'"overall_match_explanation"\s*:\s*"([^"]*(?:\\"[^"]*)*)"', content)
    if match:
        result['overall_match_explanation'] = match.group(1).replace('\\"', '"')

    # Extract array fields
    for field in ['extracted_article_topics', 'extracted_article_keywords']:
        match = re.search(rf'"{field}"\s*:\s*\[([^\]]*)\]', content)
        if match:
            try:
                items = re.findall(r'"([^"]*)"', match.group(1))
                result[field] = items
            except:
                result[field] = []

    if result:
        logger.warning(f"Extracted partial JSON using regex fallback: {list(result.keys())}")
        return result

    raise ValueError(f"Could not parse JSON: {json_str[:200]}...")


class RelevanceCalculatorError(Exception):
    """Custom exception for relevance calculation errors."""
    pass

class RelevanceCalculator:
    def __init__(self, model_name: str = None):
        """Initialize the relevance calculator with an optional model name."""
        self.model_name = model_name
        self.ai_model = None
        self.prompt_templates = PromptTemplates()
        
        if model_name:
            self._initialize_model(model_name)

    def _initialize_model(self, model_name: str) -> None:
        """Initialize the AI model for relevance analysis."""
        try:
            # Always use LiteLLMModel which has proper handling for custom providers
            logger.info(f"Initializing relevance calculator with LiteLLM model: {model_name}")
            self.ai_model = LiteLLMModel.get_instance(model_name)
            self.model_name = model_name
            logger.info(f"Successfully initialized relevance calculator with model: {model_name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize model {model_name}: {str(e)}")
            raise RelevanceCalculatorError(f"Failed to initialize model {model_name}: {str(e)}")

    def set_model(self, model_name: str) -> None:
        """Set or change the AI model for relevance analysis."""
        self._initialize_model(model_name)

    def calculate_topic_alignment(self, article_content: str, topic: str) -> float:
        """Calculate topic alignment score (legacy method for backward compatibility)."""
        if not self.ai_model:
            logger.warning("No AI model initialized for relevance calculation")
            return 0.0
        
        # This is a simplified version that just returns a basic score
        # The full analysis is done in analyze_relevance method
        try:
            result = self.analyze_relevance(
                title="",
                source="",
                content=article_content,
                topic=topic,
                keywords=""
            )
            return result.get("topic_alignment_score", 0.0)
        except Exception as e:
            logger.error(f"Error calculating topic alignment: {str(e)}")
            return 0.0

    def calculate_keyword_relevance(self, article_content: str, keywords: list[str]) -> float:
        """Calculate keyword relevance score (legacy method for backward compatibility)."""
        if not self.ai_model:
            logger.warning("No AI model initialized for relevance calculation")
            return 0.0
        
        # This is a simplified version that just returns a basic score
        # The full analysis is done in analyze_relevance method
        try:
            keywords_str = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)
            result = self.analyze_relevance(
                title="",
                source="",
                content=article_content,
                topic="",
                keywords=keywords_str
            )
            return result.get("keyword_relevance_score", 0.0)
        except Exception as e:
            logger.error(f"Error calculating keyword relevance: {str(e)}")
            return 0.0

    def calculate_confidence_score(self, alignment_score: float, relevance_score: float) -> float:
        """Calculate confidence score based on alignment and relevance scores (legacy method)."""
        # Simple heuristic: average of the two scores
        return (alignment_score + relevance_score) / 2.0

    def generate_match_explanation(self, article_content: str, topic: str, keywords: list[str]) -> str:
        """Generate explanation for the match (legacy method for backward compatibility)."""
        if not self.ai_model:
            return "Explanation not available - no AI model initialized."
        
        try:
            keywords_str = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)
            result = self.analyze_relevance(
                title="",
                source="",
                content=article_content,
                topic=topic,
                keywords=keywords_str
            )
            return result.get("overall_match_explanation", "No explanation available.")
        except Exception as e:
            logger.error(f"Error generating match explanation: {str(e)}")
            return f"Error generating explanation: {str(e)}"

    def extract_article_topics(self, article_content: str) -> list[str]:
        """Extract topics from article content (legacy method for backward compatibility)."""
        if not self.ai_model:
            return []
        
        try:
            result = self.analyze_relevance(
                title="",
                source="",
                content=article_content,
                topic="",
                keywords=""
            )
            return result.get("extracted_article_topics", [])
        except Exception as e:
            logger.error(f"Error extracting article topics: {str(e)}")
            return []

    def extract_article_keywords(self, article_content: str) -> list[str]:
        """Extract keywords from article content (legacy method for backward compatibility)."""
        if not self.ai_model:
            return []
        
        try:
            result = self.analyze_relevance(
                title="",
                source="",
                content=article_content,
                topic="",
                keywords=""
            )
            return result.get("extracted_article_keywords", [])
        except Exception as e:
            logger.error(f"Error extracting article keywords: {str(e)}")
            return []

    def analyze_relevance(self, title: str, source: str, content: str, topic: str, keywords: str, topic_description: str = None) -> Dict:
        """
        Perform comprehensive relevance analysis using the configured LLM model.

        Args:
            title: Article title
            source: Article source
            content: Article content
            topic: Target topic for monitoring
            keywords: Target keywords (comma-separated string)
            topic_description: Optional detailed description of the topic for better context

        Returns:
            Dict containing relevance analysis results
        """
        if not self.ai_model:
            raise RelevanceCalculatorError("No AI model initialized for relevance analysis")

        try:
            # Truncate content for models with small context windows
            # Local models (vLLM, Ollama) typically have 4k-8k context
            max_content_chars = 6000  # ~1500 tokens, leaves room for prompt and response
            if self.model_name and ('vllm' in self.model_name.lower() or ':' in self.model_name):
                max_content_chars = 3000  # More aggressive truncation for local models
                logger.debug(f"Using reduced content limit ({max_content_chars} chars) for local model: {self.model_name}")

            if content and len(content) > max_content_chars:
                original_len = len(content)
                content = content[:max_content_chars] + "... [truncated]"
                logger.info(f"Truncated content from {original_len} to {max_content_chars} chars for model {self.model_name}")

            # Format the prompt using the template
            messages = self.prompt_templates.format_relevance_analysis_prompt(
                title=title or "No title available",
                source=source or "Unknown source",
                content=content or "No content available",
                topic=topic or "No topic specified",
                keywords=keywords or "No keywords specified",
                topic_description=topic_description or ""
            )

            logger.info(f"Analyzing relevance for article: {title[:50]}... using model: {self.model_name}")

            # Debug logging at appropriate level
            logger.debug(f"Messages: type={type(messages)}, len={len(messages) if isinstance(messages, list) else 'N/A'}")
            if isinstance(messages, list) and len(messages) > 0:
                logger.debug(f"First message: {messages[0]}")

            # Generate response using the AI model
            if hasattr(self.ai_model, 'generate_response'):
                response_text = self.ai_model.generate_response(messages)
            else:
                # Fallback for older model interface
                combined_prompt = f"{messages[0]['content']}\n\n{messages[1]['content']}"
                response = self.ai_model.generate(combined_prompt)
                if hasattr(response, 'message') and hasattr(response.message, 'content'):
                    response_text = response.message.content
                elif hasattr(response, 'content'):
                    response_text = response.content
                else:
                    response_text = str(response)
            
            # Parse the JSON response using robust parser for local models
            try:
                result = _parse_llm_json(response_text)
                
                # Validate required fields and provide defaults
                validated_result = {
                    "topic_alignment_score": float(result.get("topic_alignment_score", 0.0)),
                    "keyword_relevance_score": float(result.get("keyword_relevance_score", 0.0)),
                    "overall_match_explanation": str(result.get("overall_match_explanation", "No explanation provided")),
                    "confidence_score": float(result.get("confidence_score", 0.0)),
                    "extracted_article_topics": result.get("extracted_article_topics", []),
                    "extracted_article_keywords": result.get("extracted_article_keywords", [])
                }
                
                # Ensure scores are within valid range [0.0, 1.0]
                for score_field in ["topic_alignment_score", "keyword_relevance_score", "confidence_score"]:
                    score = validated_result[score_field]
                    validated_result[score_field] = max(0.0, min(1.0, score))
                
                # Calculate combined relevance score (average of topic and keyword scores)
                topic_score = validated_result["topic_alignment_score"]
                keyword_score = validated_result["keyword_relevance_score"]
                validated_result["relevance_score"] = (topic_score + keyword_score) / 2.0
                
                # Ensure lists are actually lists
                for list_field in ["extracted_article_topics", "extracted_article_keywords"]:
                    if not isinstance(validated_result[list_field], list):
                        validated_result[list_field] = []
                
                logger.info(f"Successfully analyzed relevance. Topic alignment: {validated_result['topic_alignment_score']:.2f}, "
                           f"Keyword relevance: {validated_result['keyword_relevance_score']:.2f}")
                
                return validated_result
                
            except (json.JSONDecodeError, ValueError, KeyError) as parse_error:
                logger.error(f"Failed to parse LLM response as JSON: {str(parse_error)}")
                logger.error(f"Raw response: {response_text}")
                
                # Return default values if parsing fails
                return {
                    "topic_alignment_score": 0.0,
                    "keyword_relevance_score": 0.0,
                    "overall_match_explanation": f"Failed to parse analysis response: {str(parse_error)}",
                    "confidence_score": 0.0,
                    "extracted_article_topics": [],
                    "extracted_article_keywords": [],
                    "relevance_score": 0.0
                }

        # Handle PipelineError (fatal errors from LLM)
        except PipelineError as e:
            logger.error(f"🚨 FATAL error during relevance analysis: {e}")
            # Re-raise PipelineError to allow pipeline to handle it (e.g., stop processing)
            raise

        # Handle other exceptions
        except Exception as e:
            logger.error(f"Error during relevance analysis: {str(e)}")
            # For non-fatal errors, wrap in RelevanceCalculatorError
            raise RelevanceCalculatorError(f"Relevance analysis failed: {str(e)}")

    def analyze_articles_batch(self, articles: List[Dict], topic: str, keywords: str) -> List[Dict]:
        """
        Analyze relevance for a batch of articles.
        
        Args:
            articles: List of article dictionaries with 'title', 'source', 'content', 'uri' keys
            topic: Target topic for monitoring
            keywords: Target keywords (comma-separated string)
            
        Returns:
            List of dictionaries containing original article data plus relevance analysis
        """
        if not self.ai_model:
            raise RelevanceCalculatorError("No AI model initialized for batch relevance analysis")
        
        results = []
        
        for i, article in enumerate(articles):
            try:
                logger.info(f"Analyzing article {i+1}/{len(articles)}: {article.get('title', 'No title')[:50]}...")
                
                # Perform relevance analysis
                relevance_result = self.analyze_relevance(
                    title=article.get('title', ''),
                    source=article.get('source', ''),
                    content=article.get('content', ''),
                    topic=topic,
                    keywords=keywords
                )
                
                # Combine original article data with relevance analysis
                result = article.copy()
                result.update(relevance_result)
                results.append(result)
                
            except Exception as e:
                logger.error(f"Failed to analyze article {i+1}: {str(e)}")
                # Add the article with default relevance scores
                result = article.copy()
                result.update({
                    "topic_alignment_score": 0.0,
                    "keyword_relevance_score": 0.0,
                    "overall_match_explanation": f"Analysis failed: {str(e)}",
                    "confidence_score": 0.0,
                    "extracted_article_topics": [],
                    "extracted_article_keywords": [],
                    "relevance_score": 0.0
                })
                results.append(result)
        
        logger.info(f"Completed batch analysis of {len(articles)} articles")
        return results 