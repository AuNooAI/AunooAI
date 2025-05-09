# Topic Dashboard Functionality and Development Summary

## Overview

The Topic Dashboard provides a comprehensive, interactive interface for analyzing news articles and generated content related to specific user-defined topics. It aims to deliver actionable insights through various visualizations, data aggregations, and AI-powered summaries.

## Key Features Implemented

1.  **Dynamic Topic Selection**: Users can select from a list of pre-configured topics to load relevant data.
2.  **Flexible Date Range Control**:
    *   Users can select predefined date ranges (Today, Week, Month, Quarter, Year).
    *   Custom date range selection is also supported.
    *   All data displays and insights are filtered according to the selected date range.
3.  **News Ticker**:
    *   Displays the latest article headlines for the selected topic in a scrolling ticker.
    *   Styled for better visual appeal with a distinct "LATEST" badge and clear link styling.
    *   Positioned in its own panel below the main header controls.
4.  **Podcast Panel ("AI Trends Today's Briefing")**:
    *   Displays the latest generated podcast for the selected topic.
    *   Includes an audio player, publication date, and duration.
    *   Enhanced with a microphone icon and a mock waveform visualizer that animates during playback.
    *   Lists previous briefings for the topic, allowing users to play them.
5.  **Generated Insights (Tabbed Panel)**:
    *   **Trend Insights**: Displays AI-generated analytical insights based on aggregated data trends (volume, sentiment, top tags) for the selected topic and period. Markdown is rendered for rich text.
    *   **Article Insights**: Displays AI-generated thematic analysis of articles. Common themes are identified, summarized, and linked to exemplifying articles.
    *   **Category Insights**: Shows a breakdown of article counts by category. For the top 5 most active categories, AI-generated insights summarizing trends and notable characteristics are provided.
6.  **Highlights Panel**:
    *   Displays key articles curated by an LLM, including a highlight summary and category (e.g., "Breaking", "Insight").
7.  **Trends (Tabbed Panel)**:
    *   **Statistical Analysis Tab**:
        *   **Volume Over Time**: A stacked bar chart showing article volume per day. Can be stacked by 'Category' or 'Sentiment' via a dropdown control.
        *   **Sentiment Over Time**: A line chart displaying daily counts for various sentiments (Positive, Neutral, Negative, Mixed, Critical, Hyperbolic), excluding 'Unknown'.
        *   **Distribution by Future Signal, Sentiment & TTI (Radar Chart)**: A radar chart visualizing article distribution. Axes are Future Signals, datasets are Sentiments, and point radii can vary by article count. Tooltips provide detailed Time to Impact (TTI) breakdown.
    *   **Lexical Analysis Tab**:
        *   **Top Tags**: Displays a tag cloud (using TagCanvas) and a list of the most frequent tags from articles.
        *   **Word Frequency**: Shows a word cloud (using WordCloud2.js) of the most frequent words from article titles and summaries, after stop-word removal.
8.  **Articles List**:
    *   Paginated list of articles for the selected topic and date range.
    *   Filters out articles that have not been enriched with a category by default.
    *   Each article entry shows title (linkable), source, publication date, summary snippet, tags, and sentiment.
    *   Chart interactions (clicking on a date in volume/sentiment charts) can filter this list.

## Backend API Endpoints (Illustrative Summary)

*   `/api/dashboard/topic-summary/{topic_name}`: Provides summary metrics.
*   `/api/dashboard/articles/{topic_name}`: Paginated articles, supports date and category filtering.
*   `/api/dashboard/volume-over-time/{topic_name}`: Data for (stacked) volume chart.
*   `/api/dashboard/sentiment-over-time/{topic_name}`: Data for sentiment chart.
*   `/api/dashboard/top-tags/{topic_name}`: Data for tag cloud/list.
*   `/api/dashboard/word-frequency/{topic_name}`: Data for word frequency cloud.
*   `/api/dashboard/key-articles/{topic_name}`: LLM-curated highlight articles.
*   `/api/dashboard/generated-insights/{topic_name}`: LLM-generated trend insights.
*   `/api/dashboard/article-insights/{topic_name}`: LLM-generated thematic article insights.
*   `/api/dashboard/category-insights/{topic_name}`: Article counts by category, with LLM insights for top categories.
*   `/api/dashboard/latest-podcast/{topic_name}`: Latest podcast for the topic.
*   `/api/dashboard/podcasts-for-topic/{topic_name}`: List of previous podcasts.
*   `/api/dashboard/radar-chart-data/{topic_name}`: Aggregated data for the radar chart.

## Key Technical Decisions & Implementations

*   **Frontend**: HTML templates rendered by FastAPI (Jinja2), extensive use of vanilla JavaScript for dynamic data loading (fetch API) and DOM manipulation. Chart.js and WordCloud2.js are used for visualizations.
*   **Backend**: FastAPI with Pydantic models for data validation and serialization. SQLite database accessed via an async-friendly `Database` class using `run_in_threadpool`. LiteLLM for interfacing with language models (e.g., GPT-4o).
*   **Date Handling**: Consistent date range filtering (specific start/end dates or `days_limit`) applied across frontend requests and backend processing.
*   **Modularity**: Separation of concerns between frontend rendering, API routing, data aggregation logic, and database interactions.

## Next Steps & Future Enhancements

1.  **Daily Podcast Generation**:
    *   Implement a scheduled background task (e.g., using Celery, APScheduler, or a cron job with a script) to automatically generate a new podcast summary for each active topic at the start of each day.
    *   This podcast should cover significant news and trends from the previous 24-48 hours.
    *   Ensure the "AI Trends Today's Briefing" panel automatically picks up this latest daily podcast.
2.  **Daily Summary Panel**:
    *   Add a new dedicated panel on the dashboard (perhaps above or alongside "Generated Insights").
    *   This panel should display a concise, AI-generated textual summary of the key developments, news, and insights for the selected topic over the past 24 hours.
    *   This requires a new backend endpoint and LLM prompting logic focused on daily summarization.
3.  **Caching for Insights & Highlights**:
    *   **Database Storage**: Create new database tables to store generated content:
        *   `trend_insights_cache` (topic, date_range_key, insight_id, text, confidence, details, generated_at)
        *   `article_insights_cache` (topic, date_range_key, theme_name, theme_summary, article_uris_json, generated_at)
        *   `category_insights_cache` (topic, date_range_key, category_name, article_count, insight_text, generated_at)
        *   `key_articles_cache` (topic, date_range_key, article_uri, highlight_summary, highlight_category, generated_at)
    *   **Cache Key**: Use a combination of `topic_name` and a normalized representation of the `date_range` (e.g., `YYYYMMDD-YYYYMMDD` or `last_X_days`) as a cache key.
    *   **Backend Logic**:
        *   Before generating new insights/highlights, check the cache for fresh data matching the topic and date range.
        *   If valid cached data exists, return it.
        *   If not, generate new data, store it in the cache with a timestamp, and then return it.
    *   **Cache Invalidation/Renewal**: Implement a strategy for cache renewal:
        *   Time-based: e.g., regenerate insights every X minutes or hours (configurable).
        *   Event-based (more complex): Regenerate if significant new data for the topic/period arrives.
        *   A manual refresh button on the dashboard could also be an option.
4.  **Refine Radar Chart Visuals**:
    *   Further explore Chart.js options or custom plugins to make point sizes more directly proportional to article counts in a way similar to Plotly's `sizeref` and `sizemode='area'`.
    *   Adjust color palettes for better differentiation if many sentiments are present.
5.  **Error Handling & UI Feedback**:
    *   More user-friendly error messages on the frontend when API calls fail or return no data.
    *   Visual cues for data loading states in all panels that fetch data asynchronously.
6.  **Performance Optimization**:
    *   Review and optimize database queries, especially for aggregation endpoints.
    *   Consider more advanced frontend state management if complexity grows.
7.  **Configuration for LLM Prompts**: Allow prompts used for generating insights, summaries, etc., to be configurable rather than hardcoded.
8.  **User Authentication & Personalization**: Secure dashboard access and potentially allow users to save their preferred topics or default date ranges. (Some session management is in place but not fully utilized by dashboard routes yet).

This document provides a snapshot of the current Topic Dashboard and outlines a roadmap for its continued development. 