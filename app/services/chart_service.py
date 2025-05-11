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
        # Define sentiment colors (customize as needed)
        SENTIMENT_COLORS = {
            'positive': '#4caf50',
            'negative': '#f44336',
            'neutral': '#9e9e9e',
            'mixed': '#ff9800',
            'critical': '#673ab7',
            'hyperbolic': '#03a9f4',
        }
        fig = go.Figure()
        for sentiment in sentiments:
            sentiment_data = grouped[grouped['sentiment'] == sentiment]
            fig.add_trace(go.Scatterpolar(
                r=sentiment_data['count'],
                theta=sentiment_data['future_signal'],
                name=sentiment,
                marker=dict(
                    color=SENTIMENT_COLORS.get(sentiment, '#000'),
                    size=sentiment_data['count'],
                    sizemode='area',
                    sizeref=2.*max(grouped['count'])/(60.**2) if max(grouped['count']) > 0 else 1,
                    sizemin=4
                ),
                mode='markers+lines',
                line=dict(color=SENTIMENT_COLORS.get(sentiment, '#000')),
                fill='toself',
                opacity=0.6
            ))
        fig.update_layout(
            title='Radar Chart of Articles by Future Signal and Sentiment',
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, max(grouped['count'])*1.1 if len(grouped['count']) > 0 else 1]
                )
            ),
            showlegend=True,
            legend_title='Sentiment'
        )
        return self._fig_to_base64(fig)

    def _fig_to_base64(self, fig: go.Figure) -> str:
        img_bytes = fig.to_image(format="png")
        base64_str = base64.b64encode(img_bytes).decode('utf-8')
        return f"data:image/png;base64,{base64_str}" 