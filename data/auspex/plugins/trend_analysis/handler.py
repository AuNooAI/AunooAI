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

    # Color palettes for charts
    SIGNAL_COLORS = {
        "emerging technology": "#3b82f6",      # Blue
        "market disruption": "#f97316",        # Orange
        "regulatory change": "#ef4444",        # Red
        "industry shift": "#8b5cf6",           # Purple
        "competitive threat": "#dc2626",       # Dark red
        "innovation opportunity": "#22c55e",   # Green
        "consumer trend": "#ec4899",           # Pink
        "economic indicator": "#eab308",       # Yellow
        "policy impact": "#14b8a6",            # Teal
        "strategic development": "#6366f1",    # Indigo
    }

    TIME_COLORS = {
        "immediate": "#ef4444",     # Red - urgent
        "days": "#f97316",          # Orange
        "weeks": "#eab308",         # Yellow
        "1-3 months": "#22c55e",    # Green
        "3-6 months": "#14b8a6",    # Teal
        "6-12 months": "#3b82f6",   # Blue
        "1-2 years": "#6366f1",     # Indigo
        "2-5 years": "#8b5cf6",     # Purple
        "5+ years": "#a855f7",      # Violet
        "ongoing": "#6b7280",       # Gray
    }

    # Keywords for signal category detection
    SIGNAL_KEYWORDS = {
        "emerging technology": ["emerging", "new tech", "innovation", "breakthrough", "advancement", "cutting-edge", "novel"],
        "market disruption": ["disruption", "disrupt", "market shift", "industry change", "transformation", "upheaval"],
        "regulatory change": ["regula", "policy", "legislation", "law", "government", "compliance", "legal", "mandate"],
        "industry shift": ["industry", "sector", "shift", "pivot", "transition", "restructur"],
        "competitive threat": ["competitive", "threat", "competitor", "rivalry", "challenge", "pressure"],
        "innovation opportunity": ["opportunity", "potential", "growth", "expansion", "adoption", "promising"],
        "consumer trend": ["consumer", "customer", "demand", "trend", "preference", "behavior", "buying"],
        "economic indicator": ["economic", "financial", "market", "investment", "growth", "recession", "inflation"],
        "policy impact": ["policy", "impact", "effect", "consequence", "reform", "change"],
        "strategic development": ["strategic", "development", "milestone", "achievement", "progress", "launch"],
    }

    def _normalize_signal_to_category(self, signal: str) -> str:
        """Map a future signal value to a standard category for color lookup."""
        if not signal:
            return "unknown"

        signal_lower = signal.lower()

        # First try exact match
        if signal_lower in self.SIGNAL_COLORS:
            return signal_lower

        # Then try keyword matching
        for category, keywords in self.SIGNAL_KEYWORDS.items():
            if any(kw in signal_lower for kw in keywords):
                return category

        return "unknown"

    def _normalize_time_period(self, period: str) -> str:
        """Normalize a time-to-impact value for color lookup."""
        if not period:
            return "unknown"

        period_lower = period.lower().strip()

        # Direct match
        if period_lower in self.TIME_COLORS:
            return period_lower

        # Handle common variations
        normalizations = [
            (["immediate", "now", "today", "urgent"], "immediate"),
            (["day", "days", "24 hour", "24h"], "days"),
            (["week", "weeks", "7 day"], "weeks"),
            (["1-3 month", "1 month", "2 month", "3 month", "quarter", "q1", "q2", "q3", "q4"], "1-3 months"),
            (["3-6 month", "4 month", "5 month", "6 month", "half year"], "3-6 months"),
            (["6-12 month", "6 month", "year", "annual", "12 month"], "6-12 months"),
            (["1-2 year", "1 year", "2 year", "next year"], "1-2 years"),
            (["2-5 year", "3 year", "4 year", "5 year", "medium term"], "2-5 years"),
            (["5+ year", "5 year", "long term", "long-term", "decade", "10 year"], "5+ years"),
            (["ongoing", "continuous", "permanent", "indefinite"], "ongoing"),
        ]

        for keywords, normalized in normalizations:
            if any(kw in period_lower for kw in keywords):
                return normalized

        return "unknown"

    def _get_signal_color(self, signal: str) -> str:
        """Get color for a future signal value."""
        category = self._normalize_signal_to_category(signal)
        return self.SIGNAL_COLORS.get(category, "#6b7280")

    def _get_time_color(self, period: str) -> str:
        """Get color for a time-to-impact value."""
        normalized = self._normalize_time_period(period)
        return self.TIME_COLORS.get(normalized, "#6b7280")

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
            # Use the database facade's get_recent_articles_by_topic with date filtering
            # topic=None means cross-topic (All Topics) mode
            topic_for_query = topic if topic and topic != '__all__' else None
            articles = db.facade.get_recent_articles_by_topic(
                topic_name=topic_for_query,
                limit=1000,  # Get substantial sample for trend analysis
                start_date=start_date.strftime('%Y-%m-%d')
            )
            return articles if articles else []
        except Exception as e:
            self.logger.error(f"Failed to fetch articles via facade: {e}")
            # Fallback: try direct query with correct column name
            try:
                if topic and topic != '__all__':
                    query = """
                        SELECT * FROM articles
                        WHERE topic = :topic
                        AND publication_date >= :start_date
                        ORDER BY publication_date DESC
                        LIMIT 1000
                    """
                    result = db.execute_query(query, {"topic": topic, "start_date": start_date.strftime('%Y-%m-%d')})
                else:
                    # Cross-topic mode: no topic filter
                    query = """
                        SELECT * FROM articles
                        WHERE publication_date >= :start_date
                        ORDER BY publication_date DESC
                        LIMIT 1000
                    """
                    result = db.execute_query(query, {"start_date": start_date.strftime('%Y-%m-%d')})
                return [dict(row) for row in result] if result else []
            except Exception as e2:
                self.logger.error(f"Fallback query also failed: {e2}")
                return []

    def _analyze_sentiment_trends(self, articles: List[Dict]) -> Dict:
        """Analyze sentiment distribution and changes over time."""
        sentiment_counts = defaultdict(int)
        sentiment_by_week = defaultdict(lambda: defaultdict(int))

        for article in articles:
            sentiment = article.get("sentiment", "neutral")
            sentiment_counts[sentiment] += 1

            # Group by week - check both pub_date and publication_date for compatibility
            pub_date = article.get("publication_date") or article.get("pub_date")
            if pub_date:
                if isinstance(pub_date, str):
                    try:
                        if 'T' in pub_date:
                            pub_date = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                        else:
                            pub_date = datetime.strptime(pub_date[:10], '%Y-%m-%d')
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

            pub_date = article.get("publication_date") or article.get("pub_date")
            if pub_date:
                if isinstance(pub_date, str):
                    try:
                        if 'T' in pub_date:
                            pub_date = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                        else:
                            pub_date = datetime.strptime(pub_date[:10], '%Y-%m-%d')
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
        """Analyze future signal and time to impact distribution."""
        signal_counts = defaultdict(int)
        time_to_impact_counts = defaultdict(int)

        for article in articles:
            signal = article.get("future_signal", "No Signal")
            signal_counts[signal] += 1

            time_impact = article.get("time_to_impact", "")
            if time_impact and time_impact.strip():
                time_to_impact_counts[time_impact] += 1

        return {
            "distribution": dict(signal_counts),
            "top_signals": sorted(signal_counts.items(), key=lambda x: x[1], reverse=True)[:5],
            "time_to_impact": dict(time_to_impact_counts)
        }

    def _generate_time_series(self, articles: List[Dict], days: int) -> Dict:
        """Generate time series data for charting."""
        daily_counts = defaultdict(int)
        daily_sentiment = defaultdict(lambda: defaultdict(int))

        for article in articles:
            pub_date = article.get("publication_date") or article.get("pub_date")
            if pub_date:
                if isinstance(pub_date, str):
                    try:
                        if 'T' in pub_date:
                            pub_date = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                        else:
                            pub_date = datetime.strptime(pub_date[:10], '%Y-%m-%d')
                    except:
                        continue
                date_key = pub_date.strftime("%Y-%m-%d")
                daily_counts[date_key] += 1
                sentiment = article.get("sentiment", "neutral")
                daily_sentiment[date_key][sentiment] += 1

        # Fill in missing dates
        dates = []
        counts = []

        # Dynamically capture all sentiment categories from the data
        all_sentiments = set()
        for day_data in daily_sentiment.values():
            all_sentiments.update(day_data.keys())
        # Ensure we always have the basic ones even if no data
        all_sentiments.update({"positive", "negative", "neutral", "mixed", "critical"})
        sentiments = {sent: [] for sent in all_sentiments}

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
            "mixed": "#ffc107",
            "critical": "#fb923c",
            "unknown": "#9ca3af"
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

        # Sentiment pie chart - show overall distribution
        sentiment_counts = analysis.get("sentiment", {}).get("counts", {})
        sentiment_labels = []
        sentiment_values = []
        sentiment_colors = []

        for sent, count in sentiment_counts.items():
            if sent is not None and count > 0:
                sentiment_labels.append(sent.capitalize() if sent else "Unknown")
                sentiment_values.append(count)
                # Convert to lowercase for color lookup since DB stores capitalized sentiments
                sentiment_colors.append(colors.get(sent.lower() if sent else "unknown", "#999"))

        sentiment_chart = {
            "data": [
                {
                    "labels": sentiment_labels,
                    "values": sentiment_values,
                    "type": "pie",
                    "hole": 0.4,  # Makes it a donut chart
                    "marker": {"colors": sentiment_colors},
                    "textinfo": "label+percent",
                    "textposition": "outside"
                }
            ],
            "layout": {
                "title": "Sentiment Distribution",
                "showlegend": True,
                "legend": {"orientation": "h", "y": -0.1}
            }
        }

        charts = {
            "coverage": coverage_chart,
            "sentiment": sentiment_chart
        }

        # Category distribution chart (horizontal bar)
        category_data = analysis.get("categories", {})
        top_categories = category_data.get("top_categories", [])
        if top_categories:
            # Colors for categories - use a gradient palette
            category_colors = [
                "#3b82f6", "#8b5cf6", "#ec4899", "#f97316", "#eab308",
                "#22c55e", "#14b8a6", "#06b6d4", "#6366f1", "#a855f7"
            ]
            cat_labels = [cat[0] for cat in top_categories[:10]]
            cat_values = [cat[1] for cat in top_categories[:10]]
            cat_colors = category_colors[:len(cat_labels)]

            charts["categories"] = {
                "data": [
                    {
                        "x": cat_values,
                        "y": cat_labels,
                        "type": "bar",
                        "orientation": "h",
                        "marker": {"color": cat_colors}
                    }
                ],
                "layout": {
                    "title": "Top Categories",
                    "xaxis": {"title": "Article Count"},
                    "yaxis": {"autorange": "reversed"},
                    "margin": {"l": 150}
                }
            }

        # Future signals distribution chart (pie)
        signals_data = analysis.get("signals", {})
        signal_distribution = signals_data.get("distribution", {})
        if signal_distribution:
            # Filter out "No Signal" and empty values
            filtered_signals = {k: v for k, v in signal_distribution.items()
                              if k and k != "No Signal" and v > 0}
            if filtered_signals:
                sig_labels = list(filtered_signals.keys())
                sig_values = list(filtered_signals.values())
                # Use normalization to map actual signal values to color categories
                sig_colors = [self._get_signal_color(s) for s in sig_labels]

                charts["future_signals"] = {
                    "data": [
                        {
                            "labels": sig_labels,
                            "values": sig_values,
                            "type": "pie",
                            "hole": 0.4,
                            "marker": {"colors": sig_colors},
                            "textinfo": "label+percent",
                            "textposition": "outside"
                        }
                    ],
                    "layout": {
                        "title": "Future Signals Distribution",
                        "showlegend": True,
                        "legend": {"orientation": "h", "y": -0.1}
                    }
                }

        # Time to Impact chart (horizontal bar)
        time_to_impact_data = signals_data.get("time_to_impact", {})
        if time_to_impact_data:
            # Define order for time horizons (short-term to long-term)
            time_order = [
                "Immediate", "Days", "Weeks", "1-3 Months", "3-6 Months",
                "6-12 Months", "1-2 Years", "2-5 Years", "5+ Years", "Ongoing"
            ]

            # Sort by time horizon order
            sorted_times = []
            for t in time_order:
                for key, value in time_to_impact_data.items():
                    if key.lower() == t.lower() and value > 0:
                        sorted_times.append((key, value))
                        break
            # Add any not in our predefined order
            for key, value in time_to_impact_data.items():
                if value > 0 and not any(k.lower() == key.lower() for k, _ in sorted_times):
                    sorted_times.append((key, value))

            if sorted_times:
                tti_labels = [t[0] for t in sorted_times]
                tti_values = [t[1] for t in sorted_times]
                # Use normalization to handle variations in time period strings
                tti_colors = [self._get_time_color(t[0]) for t in sorted_times]

                charts["time_to_impact"] = {
                    "data": [
                        {
                            "x": tti_values,
                            "y": tti_labels,
                            "type": "bar",
                            "orientation": "h",
                            "marker": {"color": tti_colors}
                        }
                    ],
                    "layout": {
                        "title": "Time to Impact Distribution",
                        "xaxis": {"title": "Article Count"},
                        "yaxis": {"autorange": "reversed"},
                        "margin": {"l": 120}
                    }
                }

        return charts
