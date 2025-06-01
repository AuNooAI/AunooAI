import json
import logging
from typing import Dict, List, Optional, Tuple
from app.analyzers.prompt_templates import PromptTemplates, PromptTemplateError
from app.ai_models import get_ai_model, LiteLLMModel

logger = logging.getLogger(__name__)

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

    def analyze_relevance(self, title: str, source: str, content: str, topic: str, keywords: str) -> Dict:
        """
        Perform comprehensive relevance analysis using the configured LLM model.
        
        Args:
            title: Article title
            source: Article source
            content: Article content
            topic: Target topic for monitoring
            keywords: Target keywords (comma-separated string)
            
        Returns:
            Dict containing relevance analysis results
        """
        if not self.ai_model:
            raise RelevanceCalculatorError("No AI model initialized for relevance analysis")
        
        try:
            # Format the prompt using the template
            messages = self.prompt_templates.format_relevance_analysis_prompt(
                title=title or "No title available",
                source=source or "Unknown source",
                content=content or "No content available",
                topic=topic or "No topic specified",
                keywords=keywords or "No keywords specified"
            )
            
            logger.info(f"Analyzing relevance for article: {title[:50]}... using model: {self.model_name}")
            
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
            
            # Parse the JSON response
            try:
                # Clean the response text to extract JSON
                response_text = response_text.strip()
                
                # Find JSON object in the response
                start_idx = response_text.find('{')
                end_idx = response_text.rfind('}') + 1
                
                if start_idx == -1 or end_idx == 0:
                    raise ValueError("No JSON object found in response")
                
                json_str = response_text[start_idx:end_idx]
                result = json.loads(json_str)
                
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
                    "extracted_article_keywords": []
                }
                
        except Exception as e:
            logger.error(f"Error during relevance analysis: {str(e)}")
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
                    "extracted_article_keywords": []
                })
                results.append(result)
        
        logger.info(f"Completed batch analysis of {len(articles)} articles")
        return results 