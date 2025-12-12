/**
 * Category View Modal - Full-screen modal showing all articles in a category
 * Shows full summaries and links directly to external articles
 */

import { X, ChevronLeft, Star, StarOff, ExternalLink, Clock, Building2, TrendingUp } from 'lucide-react';
import { type NewsArticle } from '../../services/newsFeedApi';
import { ArticleBiasIndicator } from './ArticleBiasIndicator';
import { getCategoryIcon } from './TopicCluster';
import { Button } from '../ui/button';

interface CategoryViewModalProps {
  category: string;
  topic?: string;
  articles: NewsArticle[];
  starredArticles: string[];
  onStar: (uri: string) => void;
  onUnstar: (uri: string) => void;
  onArticleClick: (article: NewsArticle) => void;
  onClose: () => void;
}

// Format relative time
function formatTimeAgo(dateString?: string): string {
  if (!dateString) return '';
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

// Get sentiment color
function getSentimentColor(sentiment?: string): string {
  if (!sentiment) return 'text-gray-600';
  const lower = sentiment.toLowerCase();
  if (lower === 'positive' || lower === 'bullish') return 'text-green-600';
  if (lower === 'negative' || lower === 'bearish') return 'text-red-600';
  return 'text-gray-600';
}

export function CategoryViewModal({
  category,
  topic,
  articles,
  starredArticles,
  onStar,
  onUnstar,
  onArticleClick,
  onClose,
}: CategoryViewModalProps) {
  if (!category) return null;

  const handleStarClick = (e: React.MouseEvent, article: NewsArticle) => {
    e.preventDefault();
    e.stopPropagation();
    if (starredArticles.includes(article.uri)) {
      onUnstar(article.uri);
    } else {
      onStar(article.uri);
    }
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/30 z-40"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto pt-8 pb-8">
        <div className="bg-white rounded-lg shadow-2xl w-full max-w-5xl mx-4 min-h-[80vh] max-h-[95vh] overflow-y-auto">
          {/* Header */}
          <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 z-10">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <button
                  onClick={onClose}
                  className="p-2 hover:bg-gray-100 rounded-full transition-colors"
                  title="Back to feed"
                >
                  <ChevronLeft className="w-5 h-5 text-gray-500" />
                </button>
                <span className="text-2xl">{getCategoryIcon(category)}</span>
                <div>
                  <div className="flex items-center gap-2">
                    {topic && (
                      <>
                        <span className="px-2 py-1 text-sm font-semibold rounded-full bg-pink-100 text-pink-700">
                          {topic}
                        </span>
                        <span className="text-gray-400">/</span>
                      </>
                    )}
                    <h1 className="text-xl font-bold text-gray-900">{category}</h1>
                  </div>
                  <p className="text-sm text-gray-500 mt-0.5">
                    {articles.length} articles
                  </p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="p-2 hover:bg-gray-100 rounded-full transition-colors"
                title="Close"
              >
                <X className="w-5 h-5 text-gray-500" />
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="p-6">
            {articles.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <span className="text-4xl mb-4 opacity-50">
                  {getCategoryIcon(category)}
                </span>
                <h3 className="text-lg font-medium text-gray-900">No articles</h3>
                <p className="text-gray-500 mt-1">
                  No articles found in this category
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {articles.map((article) => {
                  const isStarred = starredArticles.includes(article.uri);
                  const articleUrl = article.url || article.uri;

                  return (
                    <article
                      key={article.uri}
                      className="bg-white border border-gray-200 rounded-lg p-5 hover:shadow-md transition-shadow"
                    >
                      {/* Header row: Source, time, star */}
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2 text-sm text-gray-500">
                          <Building2 className="w-4 h-4" />
                          <span className="font-medium text-gray-700">{article.source?.name || 'Unknown'}</span>
                          {article.publication_date && (
                            <>
                              <span className="text-gray-300">•</span>
                              <Clock className="w-3.5 h-3.5" />
                              <span>{formatTimeAgo(article.publication_date)}</span>
                            </>
                          )}
                        </div>
                        <button
                          onClick={(e) => handleStarClick(e, article)}
                          className="p-1.5 hover:bg-gray-100 rounded-full transition-colors"
                          title={isStarred ? 'Unstar' : 'Star'}
                        >
                          {isStarred ? (
                            <Star className="w-4 h-4 text-yellow-500 fill-yellow-500" />
                          ) : (
                            <StarOff className="w-4 h-4 text-gray-400 hover:text-gray-600" />
                          )}
                        </button>
                      </div>

                      {/* Title - links directly to external article */}
                      <a
                        href={articleUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="group block"
                      >
                        <h2 className="text-lg font-semibold text-gray-900 group-hover:text-pink-600 transition-colors leading-tight">
                          {article.title}
                        </h2>
                      </a>

                      {/* Full Summary */}
                      {article.summary && (
                        <p className="mt-3 text-gray-600 leading-relaxed">
                          {article.summary}
                        </p>
                      )}

                      {/* Metadata row */}
                      <div className="mt-4 flex flex-wrap items-center gap-3">
                        {/* Bias indicator */}
                        {article.source && (article.source.bias || article.source.factuality) && (
                          <ArticleBiasIndicator
                            bias={article.source.bias}
                            factuality={article.source.factuality}
                            size="sm"
                          />
                        )}

                        {/* Sentiment */}
                        {article.sentiment && (
                          <span className={`text-xs font-medium px-2 py-1 rounded-full bg-gray-100 ${getSentimentColor(article.sentiment)}`}>
                            <TrendingUp className="w-3 h-3 inline mr-1" />
                            {article.sentiment}
                          </span>
                        )}

                        {/* Time to impact */}
                        {article.time_to_impact && (
                          <span className="text-xs text-gray-500 px-2 py-1 rounded-full bg-gray-100">
                            Impact: {article.time_to_impact}
                          </span>
                        )}

                        {/* Tags */}
                        {article.tags && article.tags.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {(Array.isArray(article.tags) ? article.tags : String(article.tags).split(','))
                              .slice(0, 3)
                              .map((tag, i) => (
                                <span
                                  key={i}
                                  className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded"
                                >
                                  {typeof tag === 'string' ? tag.trim() : tag}
                                </span>
                              ))}
                          </div>
                        )}

                        {/* Spacer */}
                        <div className="flex-1" />

                        {/* Read article link */}
                        <a
                          href={articleUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1.5 text-sm text-pink-600 hover:text-pink-700 font-medium transition-colors"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                          Read Article
                        </a>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
