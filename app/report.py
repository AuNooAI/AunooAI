import markdown
from datetime import datetime, timedelta
from typing import List, Optional
from collections import defaultdict

class Report:
    def __init__(self, db):
        self.db = db

    async def search_articles(self, category, future_signal, sentiment, tags, keyword,
                              pub_date_start, pub_date_end, sub_date_start, sub_date_end):
        query = "SELECT * FROM articles WHERE 1=1"
        params = []

        if category:
            query += " AND category = ?"
            params.append(category)
        if future_signal:
            query += " AND future_signal = ?"
            params.append(future_signal)
        if sentiment:
            query += " AND sentiment = ?"
            params.append(sentiment)
        if tags:
            query += " AND tags LIKE ?"
            params.append(f"%{','.join(tags)}%")
        if keyword:
            query += " AND (title LIKE ? OR summary LIKE ?)"
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        if pub_date_start:
            query += " AND date(publication_date) >= date(?)"
            params.append(pub_date_start)
        if pub_date_end:
            query += " AND date(publication_date) <= date(?)"
            params.append(pub_date_end)
        if sub_date_start:
            query += " AND date(submission_date) >= date(?)"
            params.append(sub_date_start)
        if sub_date_end:
            query += " AND date(submission_date) <= date(?)"
            params.append(sub_date_end)

        query += " ORDER BY date(publication_date) DESC"

        return self.db.fetch_all(query, params)

    def generate_report(self, article_ids: List[str]) -> str:
        articles = self.db.get_articles_by_ids(article_ids)
        print(f"Generating report for {len(articles)} articles")  # Add this line for debugging
        articles_by_category = defaultdict(list)

        for article in articles:
            articles_by_category[article['category']].append(article)

        report_content = "# Article Summaries\n\n"
        
        for category, category_articles in sorted(articles_by_category.items()):
            report_content += f"## {category}\n\n"
            for article in category_articles:
                report_content += f"### {article['title']}\n\n"
                report_content += f"**{article['news_source']}** | {article['url']}\n\n"
                report_content += f"{article['summary']}\n\n"
                report_content += f"**Sentiment:** {article['sentiment']} | **Time to Impact:** {article['time_to_impact']} | **Future Signal:** {article['future_signal']}\n\n"
                report_content += "\n\n"

        return report_content

    def get_date_range(self, days):
        if days == 'all':
            return None, None
        end_date = datetime.now()
        start_date = end_date - timedelta(days=int(days))
        return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')
