"""
Trend Analysis Tool Handler

Analyzes temporal patterns in article coverage to identify trends,
sentiment shifts, and changes in media focus.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List

from app.services.tool_plugin_base import ToolHandler, ToolResult


class TrendAnalysisHandler(ToolHandler):
    """Handler for trend analysis tool."""

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        """
        Execute trend analysis on articles.

        Args:
            params: Tool parameters (topic, time_period, focus_area, include_chart)
            context: Execution context with db, vector_store, etc.

        Returns:
            ToolResult with trend analysis data
        """
        topic = params["topic"]
        time_period = params.get("time_period", "30d")
        focus_area = params.get("focus_area", "all")
        include_chart = params.get("include_chart", True)

        # Get database from context
        db = context.get("db")
        if not db:
            return ToolResult(
                success=False,
                error="Database not available in context"
            )

        # Parse time period
        days = self._parse_time_period(time_period)
        start_date = datetime.now() - timedelta(days=days)

        try:
            # Fetch articles for the time period
            articles = self._fetch_articles(db, topic, start_date)

            if not articles:
                return ToolResult(
                    success=True,
                    data={
                        "trends": [],
                        "summary": f"No articles found for topic '{topic}' in the last {days} days.",
                        "article_count": 0
                    },
                    message="No data available for trend analysis"
                )

            # Analyze based on focus area
            analysis = {}

            if focus_area in ["all", "sentiment"]:
                analysis["sentiment"] = self._analyze_sentiment_trends(articles)

            if focus_area in ["all", "categories"]:
                analysis["categories"] = self._analyze_category_trends(articles)

            if focus_area in ["all", "sources"]:
                analysis["sources"] = self._analyze_source_trends(articles)

            if focus_area in ["all", "signals"]:
                analysis["signals"] = self._analyze_signal_trends(articles)

            # Generate time series data
            time_series = self._generate_time_series(articles, days)

            # Identify key trends
            trends = self._identify_trends(analysis, articles)

            # Generate summary
            summary = self._generate_summary(trends, len(articles), days)

            # Build response
            result_data = {
                "trends": trends,
                "time_series": time_series,
                "summary": summary,
                "article_count": len(articles),
                "time_period": time_period,
                "analysis": analysis
            }

            # Add chart data if requested
            if include_chart:
                result_data["chart_data"] = self._generate_chart_data(time_series, analysis)

            return ToolResult(
                success=True,
                data=result_data,
                message=f"Analyzed {len(articles)} articles over {days} days"
            )

        except Exception as e:
            self.logger.error(f"Trend analysis failed: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e)
            )

    def _parse_time_period(self, period: str) -> int:
        """Convert time period string to days."""
        period_map = {
            "7d": 7,
            "14d": 14,
            "30d": 30,
            "90d": 90,
            "365d": 365
        }
        return period_map.get(period, 30)

    def _fetch_articles(self, db, topic: str, start_date: datetime) -> List[Dict]:
        """Fetch articles from database for the given topic and time range."""
        try:
            # Use the database facade to get articles
            articles = db.facade.get_articles_by_topic(
                topic=topic,
                start_date=start_date.isoformat(),
                limit=1000  # Get substantial sample for trend analysis
            )
            return articles if articles else []
        except Exception as e:
            self.logger.error(f"Failed to fetch articles: {e}")
            # Fallback: try direct query
            try:
                query = """
                    SELECT * FROM articles
                    WHERE topic = :topic
                    AND pub_date >= :start_date
                    ORDER BY pub_date DESC
                    LIMIT 1000
                """
                result = db.execute_query(query, {"topic": topic, "start_date": start_date})
                return [dict(row) for row in result] if result else []
            except:
                return []

    def _analyze_sentiment_trends(self, articles: List[Dict]) -> Dict:
        """Analyze sentiment distribution and changes over time."""
        sentiment_counts = defaultdict(int)
        sentiment_by_week = defaultdict(lambda: defaultdict(int))

        for article in articles:
            sentiment = article.get("sentiment", "neutral")
            sentiment_counts[sentiment] += 1

            # Group by week
            pub_date = article.get("pub_date")
            if pub_date:
                if isinstance(pub_date, str):
                    try:
                        pub_date = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                    except:
                        continue
                week_key = pub_date.strftime("%Y-W%W")
                sentiment_by_week[week_key][sentiment] += 1

        total = sum(sentiment_counts.values())
        distribution = {
            k: round(v / total * 100, 1) if total > 0 else 0
            for k, v in sentiment_counts.items()
        }

        # Calculate trend direction
        weeks = sorted(sentiment_by_week.keys())
        trend_direction = "stable"
        if len(weeks) >= 2:
            first_half = weeks[:len(weeks)//2]
            second_half = weeks[len(weeks)//2:]

            first_positive = sum(sentiment_by_week[w].get("positive", 0) for w in first_half)
            second_positive = sum(sentiment_by_week[w].get("positive", 0) for w in second_half)

            if second_positive > first_positive * 1.2:
                trend_direction = "improving"
            elif second_positive < first_positive * 0.8:
                trend_direction = "declining"

        return {
            "distribution": distribution,
            "counts": dict(sentiment_counts),
            "by_week": {k: dict(v) for k, v in sentiment_by_week.items()},
            "trend_direction": trend_direction
        }

    def _analyze_category_trends(self, articles: List[Dict]) -> Dict:
        """Analyze category distribution and emerging topics."""
        category_counts = defaultdict(int)
        category_by_week = defaultdict(lambda: defaultdict(int))

        for article in articles:
            category = article.get("category", "Uncategorized")
            category_counts[category] += 1

            pub_date = article.get("pub_date")
            if pub_date:
                if isinstance(pub_date, str):
                    try:
                        pub_date = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                    except:
                        continue
                week_key = pub_date.strftime("%Y-W%W")
                category_by_week[week_key][category] += 1

        # Find emerging and declining categories
        weeks = sorted(category_by_week.keys())
        emerging = []
        declining = []

        if len(weeks) >= 2:
            mid = len(weeks) // 2
            first_half_weeks = weeks[:mid]
            second_half_weeks = weeks[mid:]

            for cat in category_counts.keys():
                first_count = sum(category_by_week[w].get(cat, 0) for w in first_half_weeks)
                second_count = sum(category_by_week[w].get(cat, 0) for w in second_half_weeks)

                if second_count > first_count * 1.5 and second_count >= 3:
                    emerging.append({"category": cat, "growth": round((second_count / max(first_count, 1) - 1) * 100)})
                elif second_count < first_count * 0.5 and first_count >= 3:
                    declining.append({"category": cat, "decline": round((1 - second_count / max(first_count, 1)) * 100)})

        return {
            "distribution": dict(category_counts),
            "emerging": sorted(emerging, key=lambda x: x["growth"], reverse=True)[:5],
            "declining": sorted(declining, key=lambda x: x["decline"], reverse=True)[:5],
            "top_categories": sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        }

    def _analyze_source_trends(self, articles: List[Dict]) -> Dict:
        """Analyze source diversity and concentration."""
        source_counts = defaultdict(int)

        for article in articles:
            source = article.get("news_source", "Unknown")
            source_counts[source] += 1

        total = sum(source_counts.values())
        top_sources = sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        # Calculate concentration (top 3 sources share)
        top_3_share = sum(c for _, c in top_sources[:3]) / total * 100 if total > 0 else 0

        return {
            "unique_sources": len(source_counts),
            "top_sources": [{"source": s, "count": c, "share": round(c/total*100, 1)} for s, c in top_sources],
            "concentration": round(top_3_share, 1),
            "diversity_score": round(100 - top_3_share, 1)
        }

    def _analyze_signal_trends(self, articles: List[Dict]) -> Dict:
        """Analyze future signal distribution."""
        signal_counts = defaultdict(int)

        for article in articles:
            signal = article.get("future_signal", "No Signal")
            signal_counts[signal] += 1

        return {
            "distribution": dict(signal_counts),
            "top_signals": sorted(signal_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        }

    def _generate_time_series(self, articles: List[Dict], days: int) -> Dict:
        """Generate time series data for charting."""
        daily_counts = defaultdict(int)
        daily_sentiment = defaultdict(lambda: defaultdict(int))

        for article in articles:
            pub_date = article.get("pub_date")
            if pub_date:
                if isinstance(pub_date, str):
                    try:
                        pub_date = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                    except:
                        continue
                date_key = pub_date.strftime("%Y-%m-%d")
                daily_counts[date_key] += 1
                sentiment = article.get("sentiment", "neutral")
                daily_sentiment[date_key][sentiment] += 1

        # Fill in missing dates
        dates = []
        counts = []
        sentiments = {"positive": [], "negative": [], "neutral": [], "mixed": []}

        current = datetime.now() - timedelta(days=days)
        while current <= datetime.now():
            date_key = current.strftime("%Y-%m-%d")
            dates.append(date_key)
            counts.append(daily_counts.get(date_key, 0))

            day_sent = daily_sentiment.get(date_key, {})
            for sent in sentiments.keys():
                sentiments[sent].append(day_sent.get(sent, 0))

            current += timedelta(days=1)

        return {
            "dates": dates,
            "total_counts": counts,
            "sentiment_series": sentiments
        }

    def _identify_trends(self, analysis: Dict, articles: List[Dict]) -> List[Dict]:
        """Identify key trends from the analysis."""
        trends = []
        min_articles = self.config.get("min_articles_for_trend", 5)

        # Sentiment trend
        if "sentiment" in analysis:
            sent = analysis["sentiment"]
            if sent["trend_direction"] != "stable":
                trends.append({
                    "type": "sentiment",
                    "description": f"Sentiment is {sent['trend_direction']}",
                    "direction": "up" if sent["trend_direction"] == "improving" else "down",
                    "confidence": "medium",
                    "details": sent["distribution"]
                })

        # Emerging categories
        if "categories" in analysis:
            for emerging in analysis["categories"].get("emerging", [])[:3]:
                trends.append({
                    "type": "emerging_category",
                    "description": f"'{emerging['category']}' coverage is growing ({emerging['growth']}% increase)",
                    "direction": "up",
                    "confidence": "high" if emerging["growth"] > 100 else "medium",
                    "category": emerging["category"]
                })

        # Source concentration
        if "sources" in analysis:
            conc = analysis["sources"]["concentration"]
            if conc > 60:
                trends.append({
                    "type": "source_concentration",
                    "description": f"Coverage is highly concentrated (top 3 sources = {conc}%)",
                    "direction": "warning",
                    "confidence": "high"
                })

        return trends[:self.config.get("max_trends_to_report", 10)]

    def _generate_summary(self, trends: List[Dict], article_count: int, days: int) -> str:
        """Generate a natural language summary of the trends."""
        if not trends:
            return f"Analysis of {article_count} articles over {days} days shows stable patterns with no significant trends detected."

        summary_parts = [f"Analysis of {article_count} articles over {days} days reveals:"]

        for trend in trends[:5]:
            summary_parts.append(f"- {trend['description']}")

        return "\n".join(summary_parts)

    def _generate_chart_data(self, time_series: Dict, analysis: Dict) -> Dict:
        """Generate Plotly-compatible chart configuration."""
        colors = self.config.get("chart_colors", {
            "positive": "#28a745",
            "negative": "#dc3545",
            "neutral": "#6c757d",
            "mixed": "#ffc107"
        })

        # Coverage over time chart
        coverage_chart = {
            "data": [
                {
                    "x": time_series["dates"],
                    "y": time_series["total_counts"],
                    "type": "scatter",
                    "mode": "lines+markers",
                    "name": "Article Count",
                    "line": {"color": "#007bff"}
                }
            ],
            "layout": {
                "title": "Coverage Volume Over Time",
                "xaxis": {"title": "Date"},
                "yaxis": {"title": "Articles"}
            }
        }

        # Sentiment stacked area chart
        sentiment_chart = {
            "data": [
                {
                    "x": time_series["dates"],
                    "y": time_series["sentiment_series"].get(sent, []),
                    "type": "scatter",
                    "mode": "lines",
                    "stackgroup": "one",
                    "name": sent.capitalize(),
                    "line": {"color": colors.get(sent, "#999")}
                }
                for sent in ["positive", "neutral", "negative", "mixed"]
            ],
            "layout": {
                "title": "Sentiment Distribution Over Time",
                "xaxis": {"title": "Date"},
                "yaxis": {"title": "Articles"}
            }
        }

        return {
            "coverage": coverage_chart,
            "sentiment": sentiment_chart
        }
