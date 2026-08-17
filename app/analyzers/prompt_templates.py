from typing import Dict, List
import json
import os
import logging
import hashlib
from .prompt_manager import PromptManager, PromptManagerError

logger = logging.getLogger(__name__)

class PromptTemplateError(Exception):
    pass

class PromptTemplates:
    VERSION = "1.0.0"
    DEFAULT_TEMPLATES = {
        "title_extraction": {
            "version": "1.0.0",
            "system_prompt": "You are an expert editor skilled at creating and extracting perfect titles for news articles.",
            "user_prompt": """
            Extract or generate an appropriate title for the following article. Follow these guidelines:

            1. If there's a clear, existing title in the text, extract and use it.
            2. If there's no clear title, create a concise and informative title based on the main topic of the article.
            3. The title should be attention-grabbing but not clickbait.
            4. Keep the title under 15 words.
            5. Capitalize the first letter of each major word (except articles, conjunctions, and prepositions unless they're the first or last word).
            6. Do not use quotation marks in the title unless they're part of a quote that's central to the article.

            Article text:
            {article_text}

            Respond with only the title, nothing else.
            """
        },
        "content_analysis": {
            "version": "1.0.4",
            "system_prompt": "You are an expert analyst who summarizes and classifies news articles. Write summaries in the voice of {summary_voice}, as {summary_type} content. Reply only with the labelled fields requested, in the exact order and wording given, with no preamble, commentary, or markdown.",
            "user_prompt": "Analyze the following news article.\n\nTitle: {title}\nSource: {source}\nURL: {uri}\nContent: {article_text}\n\nProduce every field listed under OUTPUT FORMAT below, in that order.\n\nTitle\nReuse the article's title shown above if it is present and meaningful. If it is\nmissing, empty, or a placeholder, write your own concise title of under 15 words.\n\nSummary\nSummarize the article in at most {summary_length} words, in the voice of a\n{summary_voice}, as {summary_type} content.\n\nCategory\nClassify the article as exactly one of: {categories}\nIf none of these fit, use \"Other\".\n\nFuture Signal\nClassify the article as exactly one of: {future_signals}\nJudge this on what the article implies about how its subject develops from here,\nnot on its tone alone.\n\nSentiment\nClassify the sentiment as exactly one of: {sentiment_options}\n\nTime to Impact\nClassify the time to impact as exactly one of: {time_to_impact_options}\n\nDriver Type\nClassify the underlying driver as exactly one of: {driver_types}\n\nPolitical Bias\nClassify as exactly one of: Left-leaning, Center-left, Center, Center-right, Right-leaning, Neutral, Mixed\nJudge the political perspective, ideological stance, and any partisan framing.\n\nFactuality\nClassify as exactly one of: Very High, High, Mixed, Low, Very Low\nJudge the use of sources, evidence, fact-checking, and overall credibility.\n\nTags\nGive 3-5 concise tags capturing the article's main topics or themes. Write each\ntag as a normal English phrase with spaces between words (for example: chip\nmanufacturing, export controls) - never hashtags, never camelCase, never words\njoined together.\n\nEvery field whose label ends in \"Explanation\" is one or two sentences justifying\nthe classification on the line directly above it.\n\nOUTPUT FORMAT\nReply with exactly the lines below, in this order, one field per line.\nCopy each label character-for-character, followed by a colon and a space.\nDo not number the lines. Do not add markdown - no asterisks, hashes, or bold.\nDo not rename, merge, reorder, add, or omit any line.\n\nTitle: <title>\nSummary: <summary>\nCategory: <one of the categories listed above>\nFuture Signal: <one of the future signals listed above>\nFuture Signal Explanation: <one or two sentences>\nSentiment: <one of the sentiment values listed above>\nSentiment Explanation: <one or two sentences>\nTime to Impact: <one of the time to impact values listed above>\nTime to Impact Explanation: <one or two sentences>\nDriver Type: <one of the driver types listed above>\nDriver Type Explanation: <one or two sentences>\nPolitical Bias: <one of the political bias values listed above>\nPolitical Bias Explanation: <one or two sentences>\nFactuality: <one of the factuality values listed above>\nFactuality Explanation: <one or two sentences>\nTags: first tag, second tag, third tag"
        },
        "date_extraction": {
            "version": "1.0.0",
            "system_prompt": "You are an expert at extracting and parsing publication dates from news articles.",
            "user_prompt": """Extract the publication date from the following article text. Follow these guidelines:

1. Look for explicit publication dates in common formats
2. Look for contextual date references like 'yesterday', 'last week', etc.
3. Consider metadata dates if present
4. Return the date in YYYY-MM-DD format only

Article text:
{content}

Respond with only the date in YYYY-MM-DD format, nothing else."""
        },
        "relevance_analysis": {
            "version": "1.0.0",
            "system_prompt": "You are an expert news analyst AI. Your primary function is to meticulously evaluate news articles against specified monitoring criteria (a target topic and target keywords). Provide scores and brief, clear justifications for your assessment. Output ONLY a valid JSON object with the requested fields.",
            "user_prompt": """You are an AI assistant evaluating a news article's relevance to a specific topic and set of keywords.

Article Information:
- Title: {title}
- Source: {source}
- Content: {content}

Monitoring Criteria:
- Target Topic: {topic}
- Target Keywords: {keywords}

Evaluation Tasks:
1.  **Topic Alignment:** Assess how closely the article's main subject aligns with the Target Topic ("{topic}"). Provide a score from 0.0 (no alignment) to 1.0 (perfect alignment).
2.  **Keyword Presence & Relevance:** Determine if the Target Keywords ("{keywords}") are present in the article, and how relevant they are to the article's core message. Provide a score from 0.0 (keywords not present or irrelevant) to 1.0 (keywords present and highly relevant).
3.  **Overall Match Explanation:** Briefly explain your reasoning for the topic alignment and keyword relevance scores. Specifically highlight how the article content supports your assessment.
4.  **Confidence Score:** Rate your confidence in this overall evaluation (0.0 to 1.0).
5.  **Extracted Article Topics:** Identify the 1-3 main topics actually discussed in the article.
6.  **Extracted Article Keywords:** Extract 3-5 keywords that best represent the article's content.

Output Format (JSON Object):
{{
    "topic_alignment_score": <float, 0.0-1.0, for Target Topic>,
    "keyword_relevance_score": <float, 0.0-1.0, for Target Keywords>,
    "overall_match_explanation": "<string, your reasoning>",
    "confidence_score": <float, 0.0-1.0>,
    "extracted_article_topics": ["<string>", "<string>", ...],
    "extracted_article_keywords": ["<string>", "<string>", ...]
}}"""
        }
    }

    def __init__(self, custom_templates_path: str = None):
        try:
            self.prompt_manager = PromptManager()
            self.prompt_manager.initialize_defaults(self.DEFAULT_TEMPLATES)
            if custom_templates_path:
                self.load_custom_templates(custom_templates_path)
        except PromptManagerError as e:
            logger.error(f"Failed to initialize prompt manager: {str(e)}")
            raise PromptTemplateError(f"Failed to initialize prompt manager: {str(e)}")

    def load_custom_templates(self, path: str) -> None:
        try:
            if not os.path.exists(path):
                logger.warning(f"Custom templates file not found at {path}")
                return

            with open(path, 'r') as f:
                custom_templates = json.load(f)

            # Validate and save custom templates
            for template_name, template in custom_templates.items():
                if not self._validate_template(template):
                    logger.warning(f"Invalid template format for {template_name}, skipping")
                    continue
                self.prompt_manager.save_version(
                    template_name,
                    template["system_prompt"],
                    template["user_prompt"]
                )

            logger.info(f"Successfully loaded custom templates from {path}")
        except Exception as e:
            logger.error(f"Error loading custom templates: {str(e)}")
            raise PromptTemplateError(f"Failed to load custom templates: {str(e)}")

    def _validate_template(self, template: Dict) -> bool:
        return (
            isinstance(template, dict) and
            "system_prompt" in template and
            "user_prompt" in template and
            isinstance(template["system_prompt"], str) and
            isinstance(template["user_prompt"], str)
        )

    def get_template(self, template_name: str) -> Dict[str, str]:
        try:
            template = self.prompt_manager.get_current_version(template_name)
            return {
                "system_prompt": template["system_prompt"],
                "user_prompt": template["user_prompt"]
            }
        except PromptManagerError as e:
            logger.error(f"Failed to get template: {str(e)}")
            raise PromptTemplateError(f"Failed to get template: {str(e)}")

    def format_title_prompt(self, article_text: str) -> List[Dict[str, str]]:
        template = self.get_template("title_extraction")
        return [
            {"role": "system", "content": template["system_prompt"]},
            {"role": "user", "content": template["user_prompt"].format(
                article_text=article_text[:2000]  # First 2000 chars for title extraction
            )}
        ]

    def format_analysis_prompt(self, **kwargs) -> List[Dict[str, str]]:
        template = self.get_template("content_analysis")
        
        # Format lists as comma-separated strings
        kwargs["categories"] = ', '.join(kwargs.get("categories", []))
        kwargs["future_signals"] = ', '.join(kwargs.get("future_signals", []))
        kwargs["sentiment_options"] = ', '.join(kwargs.get("sentiment_options", []))
        kwargs["time_to_impact_options"] = ', '.join(kwargs.get("time_to_impact_options", []))
        kwargs["driver_types"] = ', '.join(kwargs.get("driver_types", []))

        return [
            {"role": "system", "content": template["system_prompt"].format(**kwargs)},
            {"role": "user", "content": template["user_prompt"].format(**kwargs)}
        ]

    def get_template_version(self, template_name: str) -> str:
        try:
            template = self.prompt_manager.get_current_version(template_name)
            return template.get("version", "1.0.0")
        except PromptManagerError as e:
            logger.error(f"Failed to get template version: {str(e)}")
            raise PromptTemplateError(f"Failed to get template version: {str(e)}")

    def get_template_hash(self) -> str:
        try:
            # Get current versions of all templates
            templates = {}
            for prompt_type in ["title_extraction", "content_analysis"]:
                template = self.prompt_manager.get_current_version(prompt_type)
                templates[prompt_type] = {
                    "system_prompt": template["system_prompt"],
                    "user_prompt": template["user_prompt"]
                }
            
            # Compute hash of all templates
            template_str = json.dumps(templates, sort_keys=True)
            return hashlib.sha256(template_str.encode()).hexdigest()[:16]
        except PromptManagerError as e:
            logger.error(f"Failed to get template hash: {str(e)}")
            raise PromptTemplateError(f"Failed to get template hash: {str(e)}")

    def format_prompt(self, prompt_type: str, variables: Dict) -> List[Dict[str, str]]:
        """Generic prompt formatting method."""
        try:
            template = self.DEFAULT_TEMPLATES.get(prompt_type)
            if not template:
                raise PromptTemplateError(f"Unknown prompt type: {prompt_type}")
            
            # Format both system and user prompts with variables
            formatted_system = template["system_prompt"].format(**variables)
            formatted_user = template["user_prompt"].format(**variables)
            
            return [
                {"role": "system", "content": formatted_system},
                {"role": "user", "content": formatted_user}
            ]
        except Exception as e:
            logger.error(f"Error formatting {prompt_type} prompt: {str(e)}")
            raise PromptTemplateError(f"Failed to format {prompt_type} prompt: {str(e)}")

    def format_date_extraction_prompt(self, content: str) -> List[Dict[str, str]]:
        template = self.get_template("date_extraction")
        return [
            {"role": "system", "content": template["system_prompt"]},
            {"role": "user", "content": template["user_prompt"].format(
                content=content[:10000]  # First 10000 chars for date extraction
            )}
        ]

    def format_relevance_analysis_prompt(self, title: str, source: str, content: str, topic: str, keywords: str, topic_description: str = "") -> List[Dict[str, str]]:
        """Format relevance analysis prompt for evaluating article relevance."""
        template = self.get_template("relevance_analysis")

        # Build context string with topic description if available
        topic_context = f"{topic}"
        if topic_description:
            topic_context = f"{topic}\nTopic Description: {topic_description}"

        return [
            {"role": "system", "content": template["system_prompt"]},
            {"role": "user", "content": template["user_prompt"].format(
                title=title,
                source=source,
                content=content[:8000],  # Limit content to avoid token limits
                topic=topic_context,  # Use enhanced topic context
                keywords=keywords
            )}
        ] 