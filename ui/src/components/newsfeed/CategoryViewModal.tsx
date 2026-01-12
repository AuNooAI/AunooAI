/**
 * Category View Modal - Full-screen modal showing all articles in a category
 * Features: Infinite scroll, Ask Auspex, full metadata badges
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { X, ChevronLeft, Star, StarOff, ExternalLink, Clock, Building2, TrendingUp, Loader2, Bot, Zap, AlertTriangle } from 'lucide-react';
import { type NewsArticle, getCategoryArticles } from '../../services/newsFeedApi';
import { ArticleBiasIndicator } from './ArticleBiasIndicator';
import { AgentSignalBadge, extractSignalTags } from './AgentSignalBadge';
import { getCategoryIcon } from './TopicCluster';
import { openAuspexWithQuery } from '../../utils/auspexEvents';

interface CategoryViewModalProps {
  category: string;
  topic?: string;
  articles: NewsArticle[];
  starredArticles: string[];
  onStar: (uri: string) => void;
  onUnstar: (uri: string) => void;
  onArticleClick: (article: NewsArticle) => void;
  onClose: () => void;
  dateRange?: string;
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

// Get sentiment styling
function getSentimentStyle(sentiment?: string): { color: string; bg: string } {
  if (!sentiment) return { color: 'text-gray-600', bg: 'bg-gray-100' };
  const lower = sentiment.toLowerCase();
  if (lower === 'positive' || lower === 'bullish') return { color: 'text-green-700', bg: 'bg-green-100' };
  if (lower === 'negative' || lower === 'bearish') return { color: 'text-red-700', bg: 'bg-red-100' };
  return { color: 'text-gray-600', bg: 'bg-gray-100' };
}

// Get future signal styling
function getFutureSignalStyle(signal?: string): { color: string; bg: string; icon: typeof Zap } {
  if (!signal) return { color: 'text-gray-600', bg: 'bg-gray-100', icon: Zap };
  const lower = signal.toLowerCase();
  if (lower.includes('strong') || lower.includes('high')) return { color: 'text-purple-700', bg: 'bg-purple-100', icon: Zap };
  if (lower.includes('weak') || lower.includes('low')) return { color: 'text-gray-600', bg: 'bg-gray-100', icon: Zap };
  return { color: 'text-blue-700', bg: 'bg-blue-100', icon: Zap };
}

export function CategoryViewModal({
  category,
  topic,
  articles: initialArticles,
  starredArticles,
  onStar,
  onUnstar,
  onArticleClick,
  onClose,
  dateRange = '7d',
}: CategoryViewModalProps) {
  const safeInitialArticles = initialArticles || [];
  const [articles, setArticles] = useState<NewsArticle[]>(safeInitialArticles);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [totalCount, setTotalCount] = useState(safeInitialArticles.length);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  // Refs for infinite scroll
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const loadMoreRef = useRef<HTMLDivElement>(null);

  // Fetch initial articles
  useEffect(() => {
    if (!category) return;

    const fetchInitialArticles = async () => {
      setInitialLoading(true);
      try {
        const response = await getCategoryArticles(category, dateRange, topic, 1, 50);
        setArticles(response.articles);
        setTotalCount(response.total_count);
        setPage(1);
        setHasMore(response.page < response.total_pages);
      } catch (error) {
        console.error('Error fetching category articles:', error);
      } finally {
        setInitialLoading(false);
      }
    };

    fetchInitialArticles();
  }, [category, dateRange, topic]);

  // Load more articles
  const loadMore = useCallback(async () => {
    if (loading || !hasMore) return;

    setLoading(true);
    try {
      const nextPage = page + 1;
      const response = await getCategoryArticles(category, dateRange, topic, nextPage, 50);
      setArticles(prev => [...prev, ...response.articles]);
      setPage(nextPage);
      setHasMore(nextPage < response.total_pages);
    } catch (error) {
      console.error('Error loading more articles:', error);
    } finally {
      setLoading(false);
    }
  }, [category, dateRange, topic, page, loading, hasMore]);

  // Infinite scroll using IntersectionObserver
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loading && !initialLoading) {
          loadMore();
        }
      },
      { threshold: 0.1, rootMargin: '100px' }
    );

    if (loadMoreRef.current) {
      observer.observe(loadMoreRef.current);
    }

    return () => observer.disconnect();
  }, [loadMore, hasMore, loading, initialLoading]);

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

  const handleAskAuspex = (article: NewsArticle) => {
    const sourceName = article.source?.name || 'Unknown source';
    const sourceInfo = [];
    if (article.source?.bias) sourceInfo.push(`Bias: ${article.source.bias}`);
    if (article.source?.factuality) sourceInfo.push(`Factuality: ${article.source.factuality}`);
    const sourceText = sourceInfo.length > 0 ? sourceInfo.join(', ') : '';

    const tagsText = article.tags
      ? (Array.isArray(article.tags) ? article.tags.join(', ') : article.tags)
      : '';

    const prompt = `Analyze this article: "${article.title}"
Article URI: ${article.uri}
Source: ${sourceName}${sourceText ? ` (${sourceText})` : ''}

ARTICLE METADATA:
${article.category ? `Category: ${article.category}` : ''}
${article.topic ? `Topic: ${article.topic}` : ''}
${article.sentiment ? `Sentiment: ${article.sentiment}` : ''}
${article.time_to_impact ? `Time to Impact: ${article.time_to_impact}` : ''}
${tagsText ? `Tags: ${tagsText}` : ''}

${article.summary ? `SUMMARY:\n${article.summary}` : ''}

Please provide:
1. Key insights and implications from this article
2. Entities and organizations mentioned
3. Potential impact on our organization
4. Related trends or developments to monitor
5. Suggested follow-up questions`;

    openAuspexWithQuery(prompt);
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/40 z-40 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-start justify-center pt-4 pb-4">
        <div
          ref={scrollContainerRef}
          className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-4xl mx-4 max-h-[95vh] overflow-y-auto"
        >
          {/* Sticky Header */}
          <div className="sticky top-0 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 px-6 py-4 z-10">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <button
                  onClick={onClose}
                  className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full transition-colors"
                  title="Back to feed"
                >
                  <ChevronLeft className="w-5 h-5 text-gray-700 dark:text-gray-300" />
                </button>
                <span className="text-2xl">{getCategoryIcon(category)}</span>
                <div>
                  <div className="flex items-center gap-2">
                    {topic && (
                      <>
                        <span className="px-2 py-1 text-sm font-semibold rounded-full bg-pink-100 dark:bg-pink-900/50 text-pink-700 dark:text-pink-300">
                          {topic}
                        </span>
                        <span className="text-gray-600 dark:text-gray-600 dark:text-gray-400">/</span>
                      </>
                    )}
                    <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">{category}</h1>
                  </div>
                  <p className="text-sm text-gray-700 dark:text-gray-300 dark:text-gray-600 dark:text-gray-400 mt-0.5">
                    {totalCount} articles
                    {articles.length < totalCount && ` • Showing ${articles.length}`}
                  </p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full transition-colors"
                title="Close"
              >
                <X className="w-5 h-5 text-gray-700 dark:text-gray-300" />
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="p-6">
            {/* Initial loading state */}
            {initialLoading ? (
              <div className="flex flex-col items-center justify-center py-16">
                <Loader2 className="w-10 h-10 animate-spin text-pink-500 mb-4" />
                <p className="text-gray-700 dark:text-gray-300 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400">Loading articles...</p>
              </div>
            ) : articles.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <span className="text-4xl mb-4 opacity-50">
                  {getCategoryIcon(category)}
                </span>
                <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">No articles</h3>
                <p className="text-gray-700 dark:text-gray-300 dark:text-gray-600 dark:text-gray-400 mt-1">
                  No articles found in this category
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {articles.map((article) => {
                  const isStarred = starredArticles.includes(article.uri);
                  const articleUrl = article.url || article.uri;
                  const signalTags = extractSignalTags(article.tags);
                  const sentimentStyle = getSentimentStyle(article.sentiment);
                  const futureSignalStyle = getFutureSignalStyle(article.future_signal);

                  return (
                    <article
                      key={article.uri}
                      className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-5 hover:shadow-lg transition-all"
                    >
                      {/* Header row: Source, time, badges, actions */}
                      <div className="flex items-start justify-between gap-3 mb-3">
                        <div className="flex flex-wrap items-center gap-2 text-sm">
                          <div className="flex items-center gap-1.5 text-gray-600 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400">
                            <Building2 className="w-4 h-4" />
                            <span className="font-medium text-gray-800 dark:text-gray-200">
                              {article.source?.name || 'Unknown Source'}
                            </span>
                          </div>
                          {article.publication_date && (
                            <>
                              <span className="text-gray-600 dark:text-gray-600 dark:text-gray-400 dark:text-gray-600">•</span>
                              <div className="flex items-center gap-1 text-gray-700 dark:text-gray-300 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400">
                                <Clock className="w-3.5 h-3.5" />
                                <span>{formatTimeAgo(article.publication_date)}</span>
                              </div>
                            </>
                          )}
                          {/* Agent Signal Badge */}
                          {signalTags.length > 0 && (
                            <AgentSignalBadge agentNames={signalTags} />
                          )}
                        </div>

                        {/* Action buttons */}
                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            onClick={() => handleAskAuspex(article)}
                            className="p-1.5 hover:bg-pink-100 dark:hover:bg-pink-900/30 rounded-full transition-colors"
                            title="Ask Auspex about this article"
                          >
                            <Bot className="w-4 h-4 text-pink-500" />
                          </button>
                          <button
                            onClick={(e) => handleStarClick(e, article)}
                            className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full transition-colors"
                            title={isStarred ? 'Unstar' : 'Star'}
                          >
                            {isStarred ? (
                              <Star className="w-4 h-4 text-yellow-500 fill-yellow-500" />
                            ) : (
                              <StarOff className="w-4 h-4 text-gray-600 dark:text-gray-400 hover:text-yellow-500" />
                            )}
                          </button>
                        </div>
                      </div>

                      {/* Title */}
                      <a
                        href={articleUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="group block"
                      >
                        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 group-hover:text-pink-600 transition-colors leading-tight">
                          {article.title}
                        </h2>
                      </a>

                      {/* Summary */}
                      {article.summary && (
                        <p className="mt-3 text-gray-600 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400 leading-relaxed line-clamp-3">
                          {article.summary}
                        </p>
                      )}

                      {/* Metadata row */}
                      <div className="mt-4 flex flex-wrap items-center gap-2">
                        {/* Bias indicator */}
                        {article.source && (article.source.bias || article.source.factuality) && (
                          <ArticleBiasIndicator
                            bias={article.source.bias}
                            factuality={article.source.factuality}
                            size="sm"
                          />
                        )}

                        {/* Sentiment badge */}
                        {article.sentiment && (
                          <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-full ${sentimentStyle.bg} ${sentimentStyle.color}`}>
                            <TrendingUp className="w-3 h-3" />
                            {article.sentiment}
                          </span>
                        )}

                        {/* Future Signal badge */}
                        {article.future_signal && (
                          <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-full ${futureSignalStyle.bg} ${futureSignalStyle.color}`}>
                            <Zap className="w-3 h-3" />
                            {article.future_signal}
                          </span>
                        )}

                        {/* Time to impact badge */}
                        {article.time_to_impact && (
                          <span className="inline-flex items-center gap-1 text-xs text-orange-700 dark:text-orange-300 px-2 py-1 rounded-full bg-orange-100 dark:bg-orange-900/30">
                            <AlertTriangle className="w-3 h-3" />
                            {article.time_to_impact}
                          </span>
                        )}

                        {/* Tags (non-signal) */}
                        {article.tags && article.tags.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {(Array.isArray(article.tags) ? article.tags : String(article.tags).split(','))
                              .filter(tag => !String(tag).includes('SIGNAL_'))
                              .slice(0, 3)
                              .map((tag, i) => (
                                <span
                                  key={i}
                                  className="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400 rounded"
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
                          Read
                        </a>
                      </div>
                    </article>
                  );
                })}

                {/* Infinite scroll trigger */}
                <div ref={loadMoreRef} className="h-4" />

                {/* Loading more indicator */}
                {loading && (
                  <div className="flex justify-center py-6">
                    <Loader2 className="w-6 h-6 animate-spin text-pink-500" />
                  </div>
                )}

                {/* End of list indicator */}
                {!hasMore && articles.length > 0 && (
                  <div className="text-center py-4 text-sm text-gray-700 dark:text-gray-300 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400">
                    All {totalCount} articles loaded
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
