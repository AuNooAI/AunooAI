"""Chart generation service module."""
import logging
import json
from datetime import date
from typing import Dict, List, Optional, Literal, Union
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import base64
import io

logger = logging.getLogger(__name__)

# Type alias for output formats
OutputFormat = Literal["base64", "json", "html"]


class ChartService:
    """Service for generating charts and visualizations."""

    # Sentiment color palette - consistent across all charts
    SENTIMENT_COLORS = {
        'positive': 'rgb(76, 175, 80)',     # Bright green
        'negative': 'rgb(244, 67, 54)',     # Bright red
        'neutral': 'rgb(158, 158, 158)',    # Gray
        'mixed': 'rgb(255, 152, 0)',        # Orange
        'critical': 'rgb(156, 39, 176)',    # Purple
        'hyperbolic': 'rgb(33, 150, 243)',  # Blue
        'unknown': 'rgb(0, 0, 0)',          # Black
        'other': 'rgb(233, 30, 99)'         # Pink
    }

    def __init__(self):
        pass

    def generate_chart(
        self,
        chart_type: str,
        articles: List[Dict],
        output_format: OutputFormat = "json",
        **kwargs
    ) -> Dict:
        """
        Unified chart generation method supporting multiple output formats.

        Args:
            chart_type: Type of chart ("sentiment_donut", "sentiment_timeline",
                       "volume", "radar", "category_bar")
            articles: List of article dictionaries
            output_format: "json" (Plotly JSON), "base64" (PNG), or "html"
            **kwargs: Additional chart-specific parameters

        Returns:
            Dict with chart data in specified format
        """
        chart_methods = {
            "sentiment_donut": self._generate_sentiment_donut,
            "sentiment_timeline": self._generate_sentiment_timeline,
            "volume": self._generate_volume,
            "radar": self._generate_radar,
            "category_bar": self._generate_category_bar,
        }

        if chart_type not in chart_methods:
            return {
                "error": f"Unknown chart type: {chart_type}",
                "available_types": list(chart_methods.keys())
            }

        try:
            fig = chart_methods[chart_type](articles, **kwargs)
            if fig is None:
                return {"error": "Insufficient data for chart generation"}

            return self._format_output(fig, chart_type, output_format)
        except Exception as e:
            logger.error(f"Error generating {chart_type} chart: {e}")
            return {"error": str(e)}

    def _format_output(
        self,
        fig: go.Figure,
        chart_type: str,
        output_format: OutputFormat
    ) -> Dict:
        """Format figure output based on requested format."""
        result = {
            "type": chart_type,
            "format": output_format,
            "title": fig.layout.title.text if fig.layout.title else chart_type
        }

        if output_format == "json":
            # Return Plotly JSON for frontend rendering
            result["data"] = json.loads(fig.to_json())
        elif output_format == "html":
            # Return embeddable HTML
            result["data"] = fig.to_html(include_plotlyjs=False, full_html=False)
        else:  # base64
            result["data"] = self._fig_to_base64(fig)

        return result

    def _generate_sentiment_donut(self, articles: List[Dict], **kwargs) -> Optional[go.Figure]:
        """Generate a sentiment distribution donut chart."""
        if not articles:
            return None

        df = pd.DataFrame(articles)
        if 'sentiment' not in df.columns:
            return None

        sentiment_counts = df['sentiment'].value_counts()

        # Get colors for each sentiment
        colors = [self.SENTIMENT_COLORS.get(s, self.SENTIMENT_COLORS['unknown'])
                  for s in sentiment_counts.index]

        fig = go.Figure(data=[go.Pie(
            labels=sentiment_counts.index,
            values=sentiment_counts.values,
            hole=0.4,
            marker=dict(colors=colors),
            textinfo='label+percent',
            textposition='outside',
            hovertemplate='<b>%{label}</b><br>Count: %{value}<br>Percentage: %{percent}<extra></extra>'
        )])

        fig.update_layout(
            title={
                'text': kwargs.get('title', 'Sentiment Distribution'),
                'font': {'size': 20, 'color': 'black'}
            },
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.2,
                xanchor="center",
                x=0.5
            ),
            paper_bgcolor='white',
            plot_bgcolor='white',
            font=dict(color='black'),
            template=None  # Remove template to ensure explicit colors are used
        )

        return fig

    def _generate_sentiment_timeline(
        self,
        articles: List[Dict],
        **kwargs
    ) -> Optional[go.Figure]:
        """Generate a sentiment over time line chart."""
        if not articles:
            return None

        df = pd.DataFrame(articles)
        if 'publication_date' not in df.columns or 'sentiment' not in df.columns:
            return None

        df['publication_date'] = pd.to_datetime(df['publication_date'], format='%Y-%m-%d', errors='coerce')
        df = df.dropna(subset=['publication_date'])

        if df.empty:
            return None

        sentiment_over_time = df.groupby(['publication_date', 'sentiment']).size().unstack(fill_value=0)

        fig = go.Figure()

        for sentiment in sentiment_over_time.columns:
            color = self.SENTIMENT_COLORS.get(sentiment, self.SENTIMENT_COLORS['unknown'])
            fig.add_trace(go.Scatter(
                x=sentiment_over_time.index,
                y=sentiment_over_time[sentiment],
                name=sentiment,
                mode='lines+markers',
                line=dict(color=color, width=3),
                marker=dict(color=color, size=8),
                hovertemplate='<b>%{x|%Y-%m-%d}</b><br>%{y} articles<extra></extra>'
            ))

        fig.update_layout(
            title={
                'text': kwargs.get('title', 'Sentiment Over Time'),
                'font': {'size': 20, 'color': 'black'}
            },
            xaxis_title='Date',
            yaxis_title='Article Count',
            hovermode='x unified',
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            paper_bgcolor='white',
            plot_bgcolor='white',
            font=dict(color='black'),
            template=None  # Remove template to ensure explicit colors are used
        )

        fig.update_xaxes(gridcolor='lightgray', linecolor='black', linewidth=1)
        fig.update_yaxes(gridcolor='lightgray', linecolor='black', linewidth=1)

        return fig

    def _generate_volume(self, articles: List[Dict], **kwargs) -> Optional[go.Figure]:
        """Generate article volume over time chart."""
        if not articles:
            return None

        df = pd.DataFrame(articles)
        if 'publication_date' not in df.columns:
            return None

        df['publication_date'] = pd.to_datetime(df['publication_date'], format='%Y-%m-%d', errors='coerce')
        df = df.dropna(subset=['publication_date'])

        if df.empty:
            return None

        daily_counts = df.groupby('publication_date').size()

        fig = go.Figure()

        fig.add_trace(go.Bar(
            x=daily_counts.index,
            y=daily_counts.values,
            marker_color='rgb(55, 83, 109)',
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>%{y} articles<extra></extra>'
        ))

        # Add trend line
        if len(daily_counts) > 2:
            fig.add_trace(go.Scatter(
                x=daily_counts.index,
                y=daily_counts.rolling(window=3, min_periods=1).mean(),
                mode='lines',
                name='3-day average',
                line=dict(color='rgb(255, 127, 14)', width=2, dash='dash')
            ))

        fig.update_layout(
            title={
                'text': kwargs.get('title', 'Article Volume Over Time'),
                'font': {'size': 20, 'color': 'black'}
            },
            xaxis_title='Date',
            yaxis_title='Article Count',
            paper_bgcolor='white',
            plot_bgcolor='white',
            font=dict(color='black'),
            showlegend=True
        )

        return fig

    def _generate_radar(self, articles: List[Dict], **kwargs) -> Optional[go.Figure]:
        """Generate radar chart for signal analysis by sentiment."""
        if not articles:
            return None

        df = pd.DataFrame(articles)
        required_cols = ['future_signal', 'sentiment']
        if not all(col in df.columns for col in required_cols):
            return None

        grouped = df.groupby(['future_signal', 'sentiment']).size().reset_index(name='count')
        if grouped.empty:
            return None

        sentiments = grouped['sentiment'].unique()

        fig = go.Figure()

        for sentiment in sentiments:
            sentiment_data = grouped[grouped['sentiment'] == sentiment]
            color = self.SENTIMENT_COLORS.get(sentiment, self.SENTIMENT_COLORS['unknown'])

            fig.add_trace(go.Scatterpolar(
                r=sentiment_data['count'],
                theta=sentiment_data['future_signal'],
                name=sentiment,
                marker=dict(color=color, size=10),
                mode='markers+lines',
                line=dict(color=color, width=2),
                fill='toself',
                opacity=0.7
            ))

        fig.update_layout(
            title={
                'text': kwargs.get('title', 'Signal Analysis by Sentiment'),
                'font': {'size': 20, 'color': 'black'}
            },
            polar=dict(
                radialaxis=dict(visible=True, color='black'),
                angularaxis=dict(color='black'),
                bgcolor='white'
            ),
            showlegend=True,
            paper_bgcolor='white',
            font=dict(color='black')
        )

        return fig

    def _generate_category_bar(self, articles: List[Dict], **kwargs) -> Optional[go.Figure]:
        """Generate category distribution bar chart."""
        if not articles:
            return None

        df = pd.DataFrame(articles)
        if 'category' not in df.columns:
            return None

        category_counts = df['category'].value_counts().head(10)  # Top 10 categories

        fig = go.Figure(data=[go.Bar(
            x=category_counts.values,
            y=category_counts.index,
            orientation='h',
            marker_color='rgb(55, 83, 109)',
            hovertemplate='<b>%{y}</b><br>%{x} articles<extra></extra>'
        )])

        fig.update_layout(
            title={
                'text': kwargs.get('title', 'Top Categories'),
                'font': {'size': 20, 'color': 'black'}
            },
            xaxis_title='Article Count',
            yaxis_title='Category',
            paper_bgcolor='white',
            plot_bgcolor='white',
            font=dict(color='black'),
            yaxis=dict(autorange='reversed')
        )

        return fig

    def generate_chart_marker(
        self,
        chart_type: str,
        articles: List[Dict],
        title: Optional[str] = None
    ) -> str:
        """
        Generate a chart and return as an embeddable marker for streaming responses.

        This returns a special marker that the frontend can parse and render.
        Format: <!-- CHART_DATA:{json}:END_CHART -->
        """
        chart_data = self.generate_chart(
            chart_type=chart_type,
            articles=articles,
            output_format="json",
            title=title
        )

        if "error" in chart_data:
            return f"<!-- CHART_ERROR:{chart_data['error']}:END_CHART -->"

        return f"<!-- CHART_DATA:{json.dumps(chart_data)}:END_CHART -->"

    def get_available_chart_types(self) -> List[Dict]:
        """Return list of available chart types with descriptions."""
        return [
            {
                "type": "sentiment_donut",
                "name": "Sentiment Distribution",
                "description": "Donut chart showing sentiment breakdown",
                "required_fields": ["sentiment"]
            },
            {
                "type": "sentiment_timeline",
                "name": "Sentiment Over Time",
                "description": "Line chart showing sentiment trends",
                "required_fields": ["publication_date", "sentiment"]
            },
            {
                "type": "volume",
                "name": "Article Volume",
                "description": "Bar chart showing article count over time",
                "required_fields": ["publication_date"]
            },
            {
                "type": "radar",
                "name": "Signal Analysis",
                "description": "Radar chart showing future signals by sentiment",
                "required_fields": ["future_signal", "sentiment"]
            },
            {
                "type": "category_bar",
                "name": "Category Distribution",
                "description": "Horizontal bar chart of top categories",
                "required_fields": ["category"]
            }
        ]

    def generate_volume_chart(
        self,
        articles: List[Dict],
        start_date: date,
        end_date: date
    ) -> str:
        df = pd.DataFrame(articles)
        df['publication_date'] = pd.to_datetime(df['publication_date'], format='%Y-%m-%d', errors='coerce')
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        category_counts = df.groupby(['publication_date', 'category']).size().unstack(fill_value=0)
        for category in category_counts.columns:
            fig.add_trace(
                go.Scatter(
                    x=category_counts.index,
                    y=category_counts[category],
                    name=f"{category}",
                    mode='lines+markers'
                ),
                secondary_y=False
            )
        sentiment_counts = df.groupby(['publication_date', 'sentiment']).size().unstack(fill_value=0)
        for sentiment in sentiment_counts.columns:
            fig.add_trace(
                go.Scatter(
                    x=sentiment_counts.index,
                    y=sentiment_counts[sentiment],
                    name=f"{sentiment}",
                    mode='lines+markers',
                    line=dict(dash='dot')
                ),
                secondary_y=True
            )
        fig.update_layout(
            title="Article Volume Over Time",
            xaxis_title="Date",
            yaxis_title="Article Count",
            hovermode="x unified",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        fig.update_yaxes(title_text="Category Count", secondary_y=False)
        fig.update_yaxes(title_text="Sentiment Count", secondary_y=True)
        return self._fig_to_base64(fig)

    def generate_sentiment_chart(self, articles: List[Dict]) -> str:
        df = pd.DataFrame(articles)
        sentiment_counts = df['sentiment'].value_counts()
        fig = go.Figure(data=[go.Pie(
            labels=sentiment_counts.index,
            values=sentiment_counts.values,
            hole=.3
        )])
        fig.update_layout(
            title="Sentiment Distribution",
            showlegend=True
        )
        return self._fig_to_base64(fig)

    def generate_radar_chart(self, articles: List[Dict]) -> str:
        df = pd.DataFrame(articles)
        if df.empty or 'future_signal' not in df.columns or 'sentiment' not in df.columns or 'time_to_impact' not in df.columns:
            return ""
        # Count combinations of future_signal and sentiment
        grouped = df.groupby(['future_signal', 'sentiment']).size().reset_index(name='count')
        sentiments = grouped['sentiment'].unique()
        
        # Define sentiment colors with very bright, high-contrast colors
        SENTIMENT_COLORS = {
            'positive': 'rgb(76, 175, 80)',     # Bright green
            'negative': 'rgb(244, 67, 54)',     # Bright red
            'neutral': 'rgb(158, 158, 158)',    # Gray
            'mixed': 'rgb(255, 152, 0)',        # Orange
            'critical': 'rgb(156, 39, 176)',    # Purple
            'hyperbolic': 'rgb(33, 150, 243)',  # Blue
            # Fallbacks for other sentiments
            'unknown': 'rgb(0, 0, 0)',          # Black
            'other': 'rgb(233, 30, 99)'         # Pink
        }
        
        fig = go.Figure()
        
        for sentiment in sentiments:
            sentiment_data = grouped[grouped['sentiment'] == sentiment]
            color = SENTIMENT_COLORS.get(sentiment, SENTIMENT_COLORS['unknown'])
            
            fig.add_trace(go.Scatterpolar(
                r=sentiment_data['count'],
                theta=sentiment_data['future_signal'],
                name=sentiment,
                marker=dict(
                    color=color,
                    size=sentiment_data['count'],
                    sizemode='area',
                    sizeref=2.*max(grouped['count'])/(60.**2) if max(grouped['count']) > 0 else 1,
                    sizemin=4,
                    line=dict(color=color, width=2)
                ),
                mode='markers+lines',
                line=dict(color=color, width=4),
                fill='toself',
                opacity=0.7
            ))
            
        # Enhanced layout
        fig.update_layout(
            title={
                'text': "Signal Analysis by Sentiment",
                'font': {'size': 24, 'color': 'black'}
            },
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, max(grouped['count'])*1.1 if len(grouped['count']) > 0 else 1],
                    color='black',
                    linecolor='black',
                    linewidth=2
                ),
                angularaxis=dict(
                    color='black',
                    linecolor='black',
                    linewidth=2
                ),
                bgcolor='white'
            ),
            showlegend=True,
            legend=dict(
                title="Sentiment",
                font=dict(size=14, color="black")
            ),
            paper_bgcolor='white',
            plot_bgcolor='white',
            font=dict(color='black'),
            colorway=[SENTIMENT_COLORS[s] if s in SENTIMENT_COLORS else SENTIMENT_COLORS['unknown'] 
                     for s in sentiments]
        )
        
        return self._fig_to_base64(fig)

    def generate_sentiment_over_time_chart(
        self,
        articles: List[Dict],
        start_date: date,
        end_date: date
    ) -> str:
        """
        Generate a line chart showing article volume over time with separate lines for each sentiment.
        """
        if not articles:
            return ""
            
        df = pd.DataFrame(articles)
        if 'publication_date' not in df.columns or 'sentiment' not in df.columns:
            return ""
            
        # Convert publication_date to datetime
        df['publication_date'] = pd.to_datetime(df['publication_date'], format='%Y-%m-%d', errors='coerce')
        
        # Group by date and sentiment
        sentiment_over_time = df.groupby(['publication_date', 'sentiment']).size().unstack(fill_value=0)
        
        # Define sentiment colors with very bright, high-contrast colors
        SENTIMENT_COLORS = {
            'positive': 'rgb(76, 175, 80)',     # Bright green
            'negative': 'rgb(244, 67, 54)',     # Bright red
            'neutral': 'rgb(158, 158, 158)',    # Gray
            'mixed': 'rgb(255, 152, 0)',        # Orange
            'critical': 'rgb(156, 39, 176)',    # Purple
            'hyperbolic': 'rgb(33, 150, 243)',  # Blue
            # Fallbacks for other sentiments
            'unknown': 'rgb(0, 0, 0)',          # Black
            'other': 'rgb(233, 30, 99)'         # Pink
        }
        
        # Create figure with white background
        fig = go.Figure()
        
        # Add a line for each sentiment with vibrant colors and thicker lines
        for sentiment in sentiment_over_time.columns:
            color = SENTIMENT_COLORS.get(sentiment, SENTIMENT_COLORS['unknown'])
            fig.add_trace(
                go.Scatter(
                    x=sentiment_over_time.index,
                    y=sentiment_over_time[sentiment],
                    name=sentiment,
                    mode='lines+markers',
                    line=dict(
                        color=color,
                        width=4
                    ),
                    marker=dict(
                        color=color,
                        size=10,
                        line=dict(
                            color=color,
                            width=2
                        )
                    )
                )
            )
        
        # Use a cleaner, more modern layout
        fig.update_layout(
            title={
                'text': "Sentiment Over Time",
                'font': {'size': 24, 'color': 'black'}
            },
            xaxis_title={
                'text': "Date", 
                'font': {'size': 18, 'color': 'black'}
            },
            yaxis_title={
                'text': "Article Count", 
                'font': {'size': 18, 'color': 'black'}
            },
            hovermode="x unified",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                font=dict(size=14, color="black")
            ),
            paper_bgcolor='white',
            plot_bgcolor='white',
            font=dict(color='black'),
            colorway=[SENTIMENT_COLORS[s] if s in SENTIMENT_COLORS else SENTIMENT_COLORS['unknown'] 
                     for s in sentiment_over_time.columns]
        )
        
        # Update axes
        fig.update_xaxes(
            gridcolor='lightgray', 
            zerolinecolor='black',
            showgrid=True,
            linecolor='black',
            linewidth=2
        )
        fig.update_yaxes(
            gridcolor='lightgray', 
            zerolinecolor='black',
            showgrid=True,
            linecolor='black',
            linewidth=2
        )
        
        return self._fig_to_base64(fig)

    def _fig_to_base64(self, fig) -> str:
        """Convert a Plotly figure to base64 string for embedding in HTML/markdown."""
        import base64
        import io
        
        try:
            # Try Plotly's built-in HTML method first, which doesn't require kaleido
            if hasattr(fig, 'to_html'):
                # Create HTML with embedded image
                html = fig.to_html(include_plotlyjs=False, full_html=False)
                # Extract the image src which is already base64 encoded
                import re
                match = re.search(r'src="data:image/png;base64,([^"]+)"', html)
                if match:
                    return f"data:image/png;base64,{match.group(1)}"

            # Try using to_image if available (requires kaleido)
            if hasattr(fig, 'to_image'):
                try:
                    img_bytes = fig.to_image(format="png", width=800, height=500)
                    encoded = base64.b64encode(img_bytes).decode('utf-8')
                    return f"data:image/png;base64,{encoded}"
                except Exception as e:
                    logger.warning(f"Plotly to_image failed: {e}, falling back to other methods")
                    
            # Try a JSON approach if to_image and to_html failed
            if hasattr(fig, 'to_json'):
                try:
                    # Create a simple placeholder image with the chart JSON data
                    logger.info("Using fallback JSON method for chart")
                    # Return a placeholder image
                    return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
                except Exception as e:
                    logger.warning(f"JSON fallback failed: {e}")
                    
            # Last resort for matplotlib figures or similar
            if hasattr(fig, 'savefig'):
                buf = io.BytesIO()
                fig.savefig(buf, format='png', bbox_inches='tight', dpi=100)
                buf.seek(0)
                encoded = base64.b64encode(buf.getvalue()).decode('utf-8')
                return f"data:image/png;base64,{encoded}"
                
            logger.error("Unable to convert figure to base64, no suitable method found")
            return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
                
        except Exception as e:
            logger.error(f"Error converting figure to base64: {e}")
            # Return a placeholder image if conversion fails
            return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==" 