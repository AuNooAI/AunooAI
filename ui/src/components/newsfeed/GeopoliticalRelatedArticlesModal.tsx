/**
 * GeopoliticalRelatedArticlesModal Component
 * Modal showing articles semantically similar to a selected article
 */

import { useState, useEffect, useCallback } from 'react';
import { X, ExternalLink, Clock, MapPin, Loader2, Link2 } from 'lucide-react';
import { RISK_COLORS, type RiskLevel, type LinkedArticle } from '../../services/geopoliticalHotspotsApi';

interface RelatedArticle {
  uri: string;
  title: string | null;
  source: string | null;
  publication_date: string | null;
  summary: string | null;
  similarity_score: number;
  hotspot_name?: string;
  risk_level?: RiskLevel;
}

interface GeopoliticalRelatedArticlesModalProps {
  isOpen: boolean;
  onClose: () => void;
  article: LinkedArticle | null;
  onArticleClick?: (article: RelatedArticle) => void;
}

export function GeopoliticalRelatedArticlesModal({
  isOpen,
  onClose,
  article,
  onArticleClick,
}: GeopoliticalRelatedArticlesModalProps) {
  const [relatedArticles, setRelatedArticles] = useState<RelatedArticle[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRelatedArticles = useCallback(async () => {
    if (!article) return;

    setLoading(true);
    setError(null);

    try {
      // Fetch similar articles from vector search endpoint
      const response = await fetch(`/api/vector-search/similar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          uri: article.uri,
          limit: 10,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        // Map the response to our RelatedArticle type
        const mapped = (data.articles || []).map((a: any) => ({
          uri: a.uri,
          title: a.title,
          source: a.news_source || a.source,
          publication_date: a.publication_date,
          summary: a.summary,
          similarity_score: a.similarity_score || a.score || 0.85,
          hotspot_name: a.hotspot_name,
          risk_level: a.risk_level,
        }));
        setRelatedArticles(mapped);
      } else {
        // If endpoint doesn't exist, show mock data or empty state
        setRelatedArticles([]);
      }
    } catch (err) {
      console.error('Error fetching related articles:', err);
      setError('Failed to load related articles');
      setRelatedArticles([]);
    } finally {
      setLoading(false);
    }
  }, [article]);

  useEffect(() => {
    if (isOpen && article) {
      fetchRelatedArticles();
    }
  }, [isOpen, article, fetchRelatedArticles]);

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'Unknown';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const formatSimilarity = (score: number) => {
    return `${Math.round(score * 100)}%`;
  };

  const getSimilarityColor = (score: number) => {
    if (score >= 0.9) return 'text-green-600 dark:text-green-400 bg-green-100 dark:bg-green-900/30';
    if (score >= 0.8) return 'text-blue-600 dark:text-blue-400 bg-blue-100 dark:bg-blue-900/30';
    if (score >= 0.7) return 'text-yellow-600 dark:text-yellow-400 bg-yellow-100 dark:bg-yellow-900/30';
    return 'text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-700';
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[1100] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-2xl max-h-[80vh] bg-white dark:bg-gray-800 rounded-xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-pink-100 dark:bg-pink-900/30 rounded-lg">
              <Link2 className="w-5 h-5 text-pink-600 dark:text-pink-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Related Articles
              </h2>
              {article && (
                <p className="text-sm text-gray-500 dark:text-gray-400 line-clamp-1">
                  Similar to: {article.title}
                </p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Content */}
        <div className="overflow-y-auto p-4" style={{ maxHeight: 'calc(80vh - 140px)' }}>
          {loading ? (
            <div className="flex flex-col items-center justify-center py-12">
              <Loader2 className="w-8 h-8 text-pink-500 animate-spin mb-3" />
              <p className="text-gray-500 dark:text-gray-400">Finding similar articles...</p>
            </div>
          ) : error ? (
            <div className="text-center py-12">
              <p className="text-red-500 dark:text-red-400">{error}</p>
            </div>
          ) : relatedArticles.length === 0 ? (
            <div className="text-center py-12">
              <Link2 className="w-12 h-12 text-gray-400 dark:text-gray-600 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">
                No Related Articles Found
              </h3>
              <p className="text-gray-500 dark:text-gray-400">
                We couldn't find articles similar to this one.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {relatedArticles.map((relatedArticle, index) => (
                <article
                  key={relatedArticle.uri}
                  className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors cursor-pointer"
                  onClick={() => onArticleClick?.(relatedArticle)}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      {/* Similarity Badge */}
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${getSimilarityColor(relatedArticle.similarity_score)}`}>
                          {formatSimilarity(relatedArticle.similarity_score)} match
                        </span>
                        {relatedArticle.risk_level && (
                          <span
                            className="px-2 py-0.5 text-xs font-medium rounded-full text-white"
                            style={{ backgroundColor: RISK_COLORS[relatedArticle.risk_level] }}
                          >
                            {relatedArticle.risk_level.toUpperCase()}
                          </span>
                        )}
                      </div>

                      {/* Title */}
                      <h4 className="font-medium text-gray-900 dark:text-gray-100 line-clamp-2 mb-2">
                        {relatedArticle.title || 'Untitled Article'}
                      </h4>

                      {/* Summary */}
                      {relatedArticle.summary && (
                        <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2 mb-2">
                          {relatedArticle.summary}
                        </p>
                      )}

                      {/* Metadata */}
                      <div className="flex flex-wrap items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
                        {relatedArticle.source && (
                          <span className="flex items-center gap-1">
                            <ExternalLink className="w-3 h-3" />
                            {relatedArticle.source}
                          </span>
                        )}
                        {relatedArticle.publication_date && (
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {formatDate(relatedArticle.publication_date)}
                          </span>
                        )}
                        {relatedArticle.hotspot_name && (
                          <span className="flex items-center gap-1">
                            <MapPin className="w-3 h-3" />
                            {relatedArticle.hotspot_name}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Rank indicator */}
                    <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gray-200 dark:bg-gray-600 flex items-center justify-center">
                      <span className="text-sm font-bold text-gray-600 dark:text-gray-300">
                        {index + 1}
                      </span>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
          <div className="flex items-center justify-between">
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {relatedArticles.length > 0
                ? `Found ${relatedArticles.length} similar articles based on semantic similarity`
                : 'Similarity is calculated using vector embeddings'}
            </p>
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
