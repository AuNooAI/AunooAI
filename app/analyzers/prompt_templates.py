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
            "version": "1.0.0",
            "system_prompt": "You are an expert assistant that analyzes and summarizes articles. Provide summaries in the style of {summary_voice} and format of {summary_type}.",
            "user_prompt": """
            Summarize the following news article in {summary_length} words, using the voice of a {summary_voice}.

            Title: {title}
            Source: {source}
            URL: {uri}
            Content: {article_text}

            Provide a summary with the following characteristics:
            Length: Maximum {summary_length} words
            Voice: {summary_voice}
            Type: {summary_type}

            Summarize the content using the specified characteristics. Format your response as follows:
            Summary: [Your summary here]

            Then, provide the following analyses:

            1. Category:
            Classify the article into one of these categories:
            {categories}
            If none of these categories fit, suggest a new category or classify it as "Other".

            2. Future Signal:
            Classify the article into one of these Future Signals:
            {future_signals}
            Base your classification on the overall tone and content of the article regarding the future of AI.
            Provide a brief explanation for your classification.

            3. Sentiment:
            Classify the sentiment as one of:
            {sentiment_options}
            Provide a brief explanation for your classification.

            4. Time to Impact:
            Classify the time to impact as one of:
            {time_to_impact_options}
            Provide a brief explanation for your classification.

            5. Driver Type:
            Classify the article into one of these Driver Types:
            {driver_types}
            Provide a brief explanation for your classification.

            6. Relevant tags:
            Generate 3-5 relevant tags for the article. These should be concise keywords or short phrases that capture the main topics or themes of the article.

            Format your response as follows:
            Title: [Your title here]
            Summary: [Your summary here]
            Category: [Your classification here]
            Future Signal: [Your classification here]
            Future Signal Explanation: [Your explanation here]
            Sentiment: [Your classification here]
            Sentiment Explanation: [Your explanation here]
            Time to Impact: [Your classification here]
            Time to Impact Explanation: [Your explanation here]
            Driver Type: [Your classification here]
            Driver Type Explanation: [Your explanation here]
            Tags: [tag1, tag2, tag3, ...]
            """
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