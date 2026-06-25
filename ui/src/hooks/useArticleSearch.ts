/**
 * useArticleSearch Hook
 * Fetches and filters articles for insertion into the newsletter editor
 */

import { useState, useCallback, useMemo } from 'react';

export interface SearchableArticle {
  uri: string;
  title: string;
  source: string;
  date: string;
  summary: string;
  url?: string;
  category?: string;
}

interface UseArticleSearchOptions {
  daysBack: number;
  topic?: string;
}

export function useArticleSearch({ daysBack, topic }: UseArticleSearchOptions) {
  const [articles, setArticles] = useState<SearchableArticle[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');

  /**
   * Fetch articles from the API
   */
  const fetchArticles = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      // Build query params
      const params = new URLSearchParams();

      // Convert days_back to date_range format
      if (daysBack <= 1) {
        params.append('date_range', '24h');
      } else if (daysBack <= 3) {
        params.append('date_range', '72h');
      } else if (daysBack <= 7) {
        params.append('date_range', '7d');
      } else if (daysBack <= 30) {
        params.append('date_range', '30d');
      } else {
        params.append('date_range', '3m');
      }

      if (topic) {
        params.append('topic', topic);
      }
      // Use per_page for the news-feed API (limit is a different parameter)
      params.append('per_page', '100');

      const response = await fetch(`/api/news-feed/articles?${params}`, {
        credentials: 'include'
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch articles: ${response.status}`);
      }

      const data = await response.json();

      // Transform to SearchableArticle format
      const transformedArticles: SearchableArticle[] = (data.articles?.items || data.articles || []).map((a: any) => ({
        uri: a.uri,
        title: a.title || 'Untitled',
        source: a.news_source || a.source || 'Unknown',
        date: (a.publication_date || a.pub_date || a.date || '').substring(0, 10),
        summary: a.summary || '',
        url: a.url || a.uri,
        category: a.category
      }));

      setArticles(transformedArticles);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load articles';
      setError(message);
      console.error('Article fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, [daysBack, topic]);

  /**
   * Filter articles by search term
   */
  const filteredArticles = useMemo(() => {
    if (!searchTerm.trim()) return articles;

    const term = searchTerm.toLowerCase();
    return articles.filter(a =>
      a.title.toLowerCase().includes(term) ||
      a.source.toLowerCase().includes(term) ||
      a.summary.toLowerCase().includes(term) ||
      (a.category && a.category.toLowerCase().includes(term))
    );
  }, [articles, searchTerm]);

  /**
   * Clear all loaded articles
   */
  const clear = useCallback(() => {
    setArticles([]);
    setSearchTerm('');
    setError(null);
  }, []);

  return {
    articles: filteredArticles,
    allArticles: articles,
    loading,
    error,
    searchTerm,
    setSearchTerm,
    fetchArticles,
    clear,
    articleCount: articles.length,
    filteredCount: filteredArticles.length
  };
}
