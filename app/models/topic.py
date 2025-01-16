class Topic:
    def __init__(self, topic_id: str, name: str, news_query: str, paper_query: str):
        self.topic = topic_id
        self.name = name
        self.news_query = news_query
        self.paper_query = paper_query
        # Add default arxiv categories if none are mapped
        self.arxiv_categories = [
            "cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.NE", "cs.RO"
        ] 