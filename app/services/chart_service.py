"""Chart generation service module."""
import logging
from datetime import date
from typing import Dict, List
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import base64

logger = logging.getLogger(__name__)

class ChartService:
    """Service for generating charts and visualizations."""

    def __init__(self):
        pass

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

    def _fig_to_base64(self, fig: go.Figure) -> str:
        """Convert figure to base64 encoded image with enhanced quality settings."""
        # Set higher quality for image rendering
        config = {
            'toImageButtonOptions': {
                'format': 'png',
                'filename': 'chart',
                'height': 800,
                'width': 1200,
                'scale': 2  # Higher scale for better resolution
            }
        }
        
        # Use higher quality settings for the image
        img_bytes = fig.to_image(
            format="png", 
            engine="kaleido", 
            width=1000,
            height=800,
            scale=2
        )
        
        base64_str = base64.b64encode(img_bytes).decode('utf-8')
        return f"data:image/png;base64,{base64_str}" 