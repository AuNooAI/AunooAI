"""
Partisan Analysis Tool Handler

Analyzes political bias distribution in media coverage with chart generation.
"""

from collections import defaultdict
from typing import Any, Dict, List

from app.services.tool_plugin_base import ToolHandler, ToolResult


class PartisanAnalysisHandler(ToolHandler):
    """Handler for partisan analysis tool."""

    # Bias category colors
    BIAS_COLORS = {
        "left": "#2563eb",        # Blue
        "center-left": "#60a5fa", # Light blue
        "center": "#9ca3af",      # Gray
        "center-right": "#f87171",# Light red
        "right": "#dc2626",       # Red
        "unknown": "#d1d5db"      # Light gray
    }

    # Map various bias labels to standard categories
    BIAS_MAPPING = {
        "left": "left",
        "left-wing": "left",
        "far-left": "left",
        "center-left": "center-left",
        "left-center": "center-left",
        "lean left": "center-left",
        "center": "center",
        "centrist": "center",
        "moderate": "center",
        "center-right": "center-right",
        "right-center": "center-right",
        "lean right": "center-right",
        "right": "right",
        "right-wing": "right",
        "far-right": "right",
        "conservative": "right",
        "liberal": "left",
        "unknown": "unknown",
        "": "unknown",
        None: "unknown"
    }

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        """
        Execute partisan analysis on articles.

        Args:
            params: Tool parameters (topic, limit, include_chart)
            context: Execution context with db, vector_store, etc.

        Returns:
            ToolResult with partisan analysis data and chart
        """
        topic = params.get("topic", "")
        limit = params.get("limit", 100)
        include_chart = params.get("include_chart", True)

        db = context.get("db")
        if not db:
            return ToolResult(
                success=False,
                error="Database not available in context"
            )

        try:
            # Fetch articles for the topic
            articles = self._fetch_articles(db, topic, limit)

            if not articles:
                return ToolResult(
                    success=True,
                    data={
                        "bias_distribution": {},
                        "summary": f"No articles found for topic '{topic}'.",
                        "article_count": 0
                    },
                    message="No data available for partisan analysis"
                )

            # Analyze bias distribution
            analysis = self._analyze_bias_distribution(articles)

            # Build response
            result_data = {
                "bias_distribution": analysis["distribution"],
                "bias_counts": analysis["counts"],
                "source_breakdown": analysis["source_breakdown"],
                "summary": self._generate_summary(analysis, len(articles)),
                "article_count": len(articles),
                "analysis": analysis
            }

            # Add chart data if requested
            if include_chart:
                chart_data = self._generate_chart_data(analysis)
                result_data["chart_data"] = chart_data
                self.logger.info(f"Generated {len(chart_data)} charts for partisan analysis")

            return ToolResult(
                success=True,
                data=result_data,
                message=f"Analyzed {len(articles)} articles for partisan bias"
            )

        except Exception as e:
            self.logger.error(f"Partisan analysis failed: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e)
            )

    def _fetch_articles(self, db, topic: str, limit: int) -> List[Dict]:
        """Fetch articles from database."""
        try:
            query = """
                SELECT a.title, a.source, a.url, a.publication_date, a.sentiment,
                       s.bias_rating, s.name as source_name
                FROM articles a
                LEFT JOIN sources s ON a.source = s.name OR a.source = s.url
                WHERE a.topic = %s
                ORDER BY a.publication_date DESC
                LIMIT %s
            """
            result = db.execute_query(query, (topic, limit))
            return [dict(row) for row in result] if result else []
        except Exception as e:
            self.logger.error(f"Query failed: {e}")
            # Fallback query without source join
            try:
                query = """
                    SELECT title, source, url, publication_date, sentiment
                    FROM articles
                    WHERE topic = %s
                    ORDER BY publication_date DESC
                    LIMIT %s
                """
                result = db.execute_query(query, (topic, limit))
                return [dict(row) for row in result] if result else []
            except Exception as e2:
                self.logger.error(f"Fallback query also failed: {e2}")
                return []

    def _normalize_bias(self, bias: str) -> str:
        """Normalize bias label to standard category."""
        if bias is None:
            return "unknown"
        bias_lower = str(bias).lower().strip()
        return self.BIAS_MAPPING.get(bias_lower, "unknown")

    def _analyze_bias_distribution(self, articles: List[Dict]) -> Dict:
        """Analyze bias distribution across articles."""
        bias_counts = defaultdict(int)
        source_by_bias = defaultdict(set)

        for article in articles:
            # Check multiple possible field names for bias
            bias = article.get("bias") or article.get("bias_rating") or article.get("political_bias", "unknown")
            normalized = self._normalize_bias(bias)
            bias_counts[normalized] += 1

            source = article.get("news_source") or article.get("source_name") or article.get("source", "Unknown")
            source_by_bias[normalized].add(source)

        total = sum(bias_counts.values())
        distribution = {
            k: round(v / total * 100, 1) if total > 0 else 0
            for k, v in bias_counts.items()
        }

        # Calculate overall lean
        left_weight = bias_counts.get("left", 0) * 2 + bias_counts.get("center-left", 0)
        right_weight = bias_counts.get("right", 0) * 2 + bias_counts.get("center-right", 0)

        if left_weight > right_weight * 1.5:
            overall_lean = "left-leaning"
        elif right_weight > left_weight * 1.5:
            overall_lean = "right-leaning"
        else:
            overall_lean = "balanced"

        return {
            "counts": dict(bias_counts),
            "distribution": distribution,
            "source_breakdown": {k: list(v) for k, v in source_by_bias.items()},
            "overall_lean": overall_lean
        }

    def _generate_summary(self, analysis: Dict, article_count: int) -> str:
        """Generate a text summary of the bias analysis."""
        dist = analysis["distribution"]
        lean = analysis["overall_lean"]

        parts = [f"Analyzed {article_count} articles."]
        parts.append(f"Overall coverage appears {lean}.")

        # Top bias categories
        sorted_bias = sorted(dist.items(), key=lambda x: x[1], reverse=True)
        if sorted_bias:
            top = sorted_bias[0]
            parts.append(f"Most common bias: {top[0]} ({top[1]}%)")

        return " ".join(parts)

    def _generate_chart_data(self, analysis: Dict) -> Dict:
        """Generate Plotly-compatible chart configuration."""
        counts = analysis.get("counts", {})

        # Order categories from left to right
        category_order = ["left", "center-left", "center", "center-right", "right", "unknown"]

        labels = []
        values = []
        colors = []

        for category in category_order:
            if category in counts and counts[category] > 0:
                labels.append(category.replace("-", " ").title())
                values.append(counts[category])
                colors.append(self.BIAS_COLORS.get(category, "#999"))

        # Pie chart for bias distribution
        bias_chart = {
            "data": [
                {
                    "labels": labels,
                    "values": values,
                    "type": "pie",
                    "hole": 0.4,
                    "marker": {"colors": colors},
                    "textinfo": "label+percent",
                    "textposition": "outside",
                    "sort": False  # Keep our left-to-right order
                }
            ],
            "layout": {
                "title": "Political Bias Distribution",
                "showlegend": True,
                "legend": {"orientation": "h", "y": -0.1}
            }
        }

        # Also create a horizontal bar chart for comparison
        bar_chart = {
            "data": [
                {
                    "x": values,
                    "y": labels,
                    "type": "bar",
                    "orientation": "h",
                    "marker": {"color": colors}
                }
            ],
            "layout": {
                "title": "Articles by Political Bias",
                "xaxis": {"title": "Number of Articles"},
                "yaxis": {"title": "Bias Category", "autorange": "reversed"}
            }
        }

        return {
            "bias_pie": bias_chart,
            "bias_bar": bar_chart
        }
