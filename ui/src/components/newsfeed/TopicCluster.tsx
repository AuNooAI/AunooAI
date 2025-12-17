/**
 * Topic Cluster - Google News style compact category section
 * Shows stories as compact cards with related coverage indicators
 */

import { useState } from 'react';
import { ChevronRight, Layers } from 'lucide-react';
import { type NewsArticle, type ArticleCluster, type ClusterRelatedArticle, clusterArticleToNewsArticle } from '../../services/newsFeedApi';

interface TopicClusterProps {
  category: string;
  articles: NewsArticle[];
  clusters?: ArticleCluster[];
  starredArticles: string[];
  onStar: (uri: string) => void;
  onUnstar: (uri: string) => void;
  onArticleClick?: (article: NewsArticle, relatedArticles?: ClusterRelatedArticle[]) => void;
  onSeeMore?: (category: string, topic?: string) => void;
  icon?: string;
  topic?: string;
  maxItems?: number;  // Max stories to show
}

// Format relative time (e.g., "2 hours ago")
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

export function TopicCluster({
  category,
  articles,
  clusters,
  starredArticles,
  onStar,
  onUnstar,
  onArticleClick,
  onSeeMore,
  icon,
  topic,
  maxItems = 4
}: TopicClusterProps) {
  // Use clusters if available, otherwise convert articles to single-item clusters
  const hasClusters = clusters && clusters.length > 0;

  // Debug: log cluster data
  if (hasClusters) {
    const withRelated = clusters.filter(c => c.related && c.related.length > 0);
    console.log(`[TopicCluster] ${category}: ${clusters.length} clusters, ${withRelated.length} with related articles`);
    if (withRelated.length > 0) {
      console.log(`[TopicCluster] First cluster with related:`, withRelated[0]);
    }
  }

  // Convert flat articles to pseudo-clusters for uniform rendering
  const displayItems: ArticleCluster[] = hasClusters
    ? clusters
    : articles.map(article => ({
        primary: {
          uri: article.uri,
          title: article.title,
          summary: article.summary,
          news_source: article.source.name,
          publication_date: article.publication_date,
          category: article.category,
          topic: article.topic,
          sentiment: article.sentiment,
          time_to_impact: article.time_to_impact,
          tags: article.tags,
          bias: article.source.bias,
          factual_reporting: article.source.factuality,
        },
        related: [],
        article_count: 1
      }));

  const totalArticles = hasClusters
    ? clusters.reduce((sum, c) => sum + c.article_count, 0)
    : articles.length;

  if (totalArticles === 0) {
    return null;
  }

  const visibleItems = displayItems.slice(0, maxItems);
  const hasMore = displayItems.length > maxItems || totalArticles > maxItems;
  const remainingStories = displayItems.length - maxItems;

  return (
    <section className="mb-6">
      {/* Section Header */}
      <div className="flex items-center justify-between mb-3">
        <button
          onClick={() => onSeeMore?.(category, topic)}
          className="flex items-center gap-2 group"
        >
          {topic && (
            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300">
              {topic}
            </span>
          )}
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100 group-hover:text-blue-600">
            {category}
          </h2>
          <ChevronRight className="w-4 h-4 text-gray-400 group-hover:text-blue-600" />
        </button>
        <span className="text-xs text-gray-600 dark:text-gray-400 font-medium">
          {totalArticles} {totalArticles === 1 ? 'article' : 'articles'}
        </span>
      </div>

      {/* Compact Story List */}
      <div className="space-y-1">
        {visibleItems.map((item, idx) => (
          <StoryRow
            key={item.primary.uri || idx}
            cluster={item}
            onArticleClick={onArticleClick}
          />
        ))}
      </div>

      {/* See more link */}
      {hasMore && (
        <button
          onClick={() => onSeeMore?.(category, topic)}
          className="text-xs text-blue-600 hover:underline mt-3 flex items-center gap-1 font-medium"
        >
          {remainingStories > 0 ? `+${remainingStories} more stories` : `View all ${totalArticles} articles`}
          <ChevronRight className="w-3 h-3" />
        </button>
      )}
    </section>
  );
}

/**
 * StoryRow - Compact story card with optional related coverage indicator
 * Shows summary on hover
 */
interface StoryRowProps {
  cluster: ArticleCluster;
  onArticleClick?: (article: NewsArticle, relatedArticles?: ClusterRelatedArticle[]) => void;
}

function StoryRow({ cluster, onArticleClick }: StoryRowProps) {
  const [showRelated, setShowRelated] = useState(false);
  const [showTooltip, setShowTooltip] = useState(false);
  const primaryArticle = clusterArticleToNewsArticle(cluster.primary);
  const hasRelated = cluster.related.length > 0;
  const totalSources = 1 + cluster.related.length;

  // Get all unique source names for display
  const allSources = [cluster.primary.news_source, ...cluster.related.map(r => r.news_source)];
  const uniqueSources = [...new Set(allSources)];

  // Handle click with related articles
  const handleArticleClick = () => {
    console.log(`[StoryRow] Click: ${cluster.primary.title?.substring(0, 50)}...`);
    console.log(`[StoryRow] Related articles:`, cluster.related?.length || 0, cluster.related);
    onArticleClick?.(primaryArticle, cluster.related);
  };

  return (
    <div className="group relative">
      {/* Main story row */}
      <div
        className="py-2.5 px-3 rounded-md bg-white/80 dark:bg-gray-800/80 hover:bg-white dark:hover:bg-gray-800 hover:shadow-sm transition-all border border-transparent hover:border-gray-200 dark:hover:border-gray-600"
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        {/* Headline - clickable */}
        <button
          onClick={handleArticleClick}
          className="text-left w-full"
        >
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 leading-snug line-clamp-2 group-hover:text-blue-600 dark:group-hover:text-blue-400">
            {cluster.primary.title}
          </h3>
        </button>

        {/* Summary tooltip on hover */}
        {showTooltip && cluster.primary.summary && (
          <div className="absolute left-full top-0 ml-2 z-50 w-72 p-3 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 pointer-events-none">
            <p className="text-xs text-gray-600 dark:text-gray-300 leading-relaxed line-clamp-4">
              {cluster.primary.summary}
            </p>
            {cluster.primary.sentiment && (
              <div className="mt-2 flex items-center gap-2 text-xs">
                <span className={`font-medium ${getSentimentColor(cluster.primary.sentiment)}`}>
                  {cluster.primary.sentiment}
                </span>
                {cluster.primary.time_to_impact && (
                  <>
                    <span className="text-gray-400">•</span>
                    <span className="text-gray-600 dark:text-gray-400">{cluster.primary.time_to_impact}</span>
                  </>
                )}
              </div>
            )}
          </div>
        )}

        {/* Source info row */}
        <div className="flex items-center gap-2 mt-1.5 text-xs">
          {/* Primary source */}
          <span className="font-medium text-gray-700 dark:text-gray-300">
            {cluster.primary.news_source}
          </span>

          {/* Time ago */}
          {cluster.primary.publication_date && (
            <>
              <span className="text-gray-400 dark:text-gray-500">·</span>
              <span className="text-gray-600 dark:text-gray-400">
                {formatTimeAgo(cluster.primary.publication_date)}
              </span>
            </>
          )}

          {/* Related sources count - Google News style */}
          {hasRelated && (
            <>
              <span className="text-gray-400 dark:text-gray-500">·</span>
              <button
                onClick={() => setShowRelated(!showRelated)}
                className="flex items-center gap-1 text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400"
              >
                <Layers className="w-3 h-3" />
                <span className="font-medium">{totalSources} sources</span>
              </button>
            </>
          )}
        </div>
      </div>

      {/* Expandable full coverage panel */}
      {hasRelated && showRelated && (
        <div className="mx-2 mb-2 p-3 bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700">
          <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">
            Full Coverage ({totalSources} sources)
          </div>
          <div className="space-y-2">
            {/* Primary article */}
            <button
              onClick={handleArticleClick}
              className="block w-full text-left p-2 bg-white dark:bg-gray-800 rounded hover:bg-blue-50 dark:hover:bg-blue-900/30 transition-colors border border-transparent hover:border-blue-200 dark:hover:border-blue-700"
            >
              <div className="flex items-center gap-2 text-xs mb-1">
                <span className="font-semibold text-blue-600 dark:text-blue-400">{cluster.primary.news_source}</span>
                {cluster.primary.publication_date && (
                  <span className="text-gray-600 dark:text-gray-400">{formatTimeAgo(cluster.primary.publication_date)}</span>
                )}
              </div>
              <p className="text-sm text-gray-900 dark:text-gray-100 line-clamp-2">{cluster.primary.title}</p>
            </button>

            {/* Related articles */}
            {cluster.related.slice(0, 4).map((related) => {
              const relatedArticle: NewsArticle = {
                uri: related.uri,
                title: related.title,
                summary: related.summary || '',
                publication_date: related.publication_date,
                source: {
                  name: related.news_source,
                  bias: related.bias as any,
                  factuality: related.factual_reporting as any,
                },
                tags: [],
              };

              return (
                <button
                  key={related.uri}
                  onClick={() => onArticleClick?.(relatedArticle)}
                  className="block w-full text-left p-2 bg-white dark:bg-gray-800 rounded hover:bg-blue-50 dark:hover:bg-blue-900/30 transition-colors border border-transparent hover:border-blue-200 dark:hover:border-blue-700"
                >
                  <div className="flex items-center gap-2 text-xs mb-1">
                    <span className="font-medium text-gray-600 dark:text-gray-300">{related.news_source}</span>
                    {related.publication_date && (
                      <span className="text-gray-600 dark:text-gray-400">{formatTimeAgo(related.publication_date)}</span>
                    )}
                  </div>
                  <p className="text-sm text-gray-700 dark:text-gray-200 line-clamp-2">{related.title}</p>
                </button>
              );
            })}

            {cluster.related.length > 4 && (
              <p className="text-xs text-gray-600 dark:text-gray-400 text-center py-1">
                +{cluster.related.length - 4} more sources covering this story
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Get sentiment color class
 */
function getSentimentColor(sentiment?: string): string {
  if (!sentiment) return 'text-gray-600';
  const lower = sentiment.toLowerCase();
  if (lower === 'positive' || lower === 'bullish') return 'text-green-600';
  if (lower === 'negative' || lower === 'bearish') return 'text-red-600';
  if (lower === 'neutral') return 'text-gray-600';
  return 'text-gray-600';
}

/**
 * Get category icon (fallback emojis)
 */
export function getCategoryIcon(category: string): string {
  const lower = category.toLowerCase();

  const iconMap: Record<string, string> = {
    'technology': '\u{1F4BB}',
    'tech': '\u{1F4BB}',
    'business': '\u{1F4B0}',
    'finance': '\u{1F4B0}',
    'economy': '\u{1F4B0}',
    'politics': '\u{1F3DB}',
    'political': '\u{1F3DB}',
    'science': '\u{1F52C}',
    'health': '\u{1F3E5}',
    'healthcare': '\u{1F3E5}',
    'sports': '\u{26BD}',
    'sport': '\u{26BD}',
    'entertainment': '\u{1F3AC}',
    'world': '\u{1F30D}',
    'international': '\u{1F30D}',
    'security': '\u{1F512}',
    'cybersecurity': '\u{1F512}',
    'cyber': '\u{1F512}',
    'ai': '\u{1F916}',
    'artificial intelligence': '\u{1F916}',
    'climate': '\u{1F30D}',
    'environment': '\u{1F331}',
    'education': '\u{1F393}',
    'automotive': '\u{1F697}',
    'energy': '\u{26A1}',
    'real estate': '\u{1F3E0}',
    'retail': '\u{1F6D2}',
    'media': '\u{1F4FA}',
    'general': '\u{1F4F0}',
  };

  if (iconMap[lower]) {
    return iconMap[lower];
  }

  for (const [key, icon] of Object.entries(iconMap)) {
    if (lower.includes(key)) {
      return icon;
    }
  }

  return '\u{1F4F0}';
}
