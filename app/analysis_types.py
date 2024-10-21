from typing import List, Dict

class AnalysisType:
    def generate_prompt(self, article_text: str, summary_length: int, title: str, source: str, uri: str) -> str:
        raise NotImplementedError

class CuriousAIAnalysis(AnalysisType):
    def __init__(self, categories: List[str], future_signals: List[str], time_to_impact: List[str], driver_types: List[str]):
        self.categories = categories
        self.future_signals = future_signals
        self.time_to_impact = time_to_impact
        self.driver_types = driver_types

    def generate_prompt(self, article_text: str, summary_length: int, title: str, source: str, uri: str) -> str:
        return f"""
        Summarize the following news article in {summary_length} words, using the voice of a curious AI.

        Title: {title}
        Source: {source}
        URL: {uri}
        Content: {article_text}

        Provide a summary with the following characteristics:
        Length: Maximum {summary_length} words
        Voice: Curious AI
        Type: Detailed analysis

        Summarize the content using the specified characteristics. Format your response as follows:
        Summary: [Your summary here]

        Then, provide the following analyses:

        1. Category:
        Classify the article into one of these categories:
        {', '.join(self.categories)}
        If none of these categories fit, suggest a new category or classify it as "Other".

        2. Future Signal:
        Classify the article into one of these Future Signals:
        {', '.join(self.future_signals)}
        Base your classification on the overall tone and content of the article regarding the future of AI.
        Provide a brief explanation for your classification.

        3. Sentiment:
        Classify the sentiment as one of:
        Positive, Neutral, Negative
        Provide a brief explanation for your classification.

        4. Time to Impact:
        Classify the time to impact as one of:
        {', '.join(self.time_to_impact)}
        Provide a brief explanation for your classification.

        5. Driver Type:
        Classify the article into one of these Driver Types:
        {', '.join(self.driver_types)}
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

class AxiosAnalysis(AnalysisType):
    def generate_prompt(self, article_text: str, summary_length: int, title: str, source: str, uri: str) -> str:
        return f"""
        Summarize the following article in the style of Axios, known for its concise, bullet-point format:

        Title: {title}
        Source: {source}
        URL: {uri}
        Content: {article_text}

        1. Provide a brief, attention-grabbing headline (max 10 words).
        2. Write a concise summary of the main point (1-2 sentences).
        3. List 2-3 key takeaways or implications, each in a short bullet point.
        4. End with a "Go deeper" section, providing a brief insight or related information.

        Keep the entire summary within {summary_length} words.

        Format your response as follows:
        Headline: [Your headline here]
        Main Point: [Your main point summary here]
        Key Takeaways:
        • [First takeaway]
        • [Second takeaway]
        • [Third takeaway (if applicable)]
        Go deeper: [Your additional insight here]
        """

def get_analysis_type(summary_type: str, config: Dict = None) -> AnalysisType:
    if config is None:
        config = {}
    
    analysis_types = {
        "curious_ai": CuriousAIAnalysis(
            categories=config.get('categories', []),
            future_signals=config.get('future_signals', []),
            time_to_impact=config.get('time_to_impact', []),
            driver_types=config.get('driver_types', [])
        ),
        "axios": AxiosAnalysis()
    }
    return analysis_types.get(summary_type, CuriousAIAnalysis([], [], [], []))