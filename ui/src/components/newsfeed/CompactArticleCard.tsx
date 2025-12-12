/**
 * Compact Article Card - Small format for related articles and lists
 * Used in sidebars and "more headlines" sections
 */

import { ExternalLink, Star, StarOff, Clock, TrendingUp } from 'lucide-react';
import { type NewsArticle } from '../../services/newsFeedApi';
import { SourceAttribution } from './SourceAttribution';
import { ArticleBiasIndicator } from './ArticleBiasIndicator';

// Helper to get sentiment color
function getSentimentColor(sentiment?: string): string {
  if (!sentiment) return 'bg-gray-100 text-gray-600';
  const lower = sentiment.toLowerCase();
  if (lower === 'positive' || lower === 'bullish') return 'bg-green-100 text-green-700';
  if (lower === 'negative' || lower === 'bearish') return 'bg-red-100 text-red-700';
  return 'bg-gray-100 text-gray-600';
}

interface CompactArticleCardProps {
  article: NewsArticle;
  isStarred?: boolean;
  onStar?: (uri: string) => void;
  onUnstar?: (uri: string) => void;
  showSummary?: boolean;
  showBias?: boolean;
  onClick?: (article: NewsArticle) => void;
}

export function CompactArticleCard({
  article,
  isStarred = false,
  onStar,
  onUnstar,
  showSummary = true,
  showBias = true,
  onClick
}: CompactArticleCardProps) {
  const handleStarClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (isStarred) {
      onUnstar?.(article.uri);
    } else {
      onStar?.(article.uri);
    }
  };

  const handleCardClick = () => {
    if (onClick) {
      onClick(article);
    }
  };

  const hasMetadata = article.sentiment || article.time_to_impact || article.source?.credibility_rating;

  return (
    <div className="relative">
      <div
        className={`group py-3 border-b border-gray-100 last:border-b-0 hover:bg-gray-50 px-2 -mx-2 rounded transition-colors ${onClick ? 'cursor-pointer' : ''}`}
        onClick={handleCardClick}
      >
        <div className="flex items-start gap-3">
          {/* Content */}
          <div className="flex-1 min-w-0">
            {/* Source */}
            <SourceAttribution
              source={article.source}
              publishedDate={article.publication_date}
              size="sm"
            />

            {/* Title */}
            <h4 className="mt-1 text-sm font-medium text-gray-900 group-hover:text-pink-600 transition-colors line-clamp-2">
              {article.url && !onClick ? (
                <a
                  href={article.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-start gap-1"
                  onClick={(e) => e.stopPropagation()}
                >
                  <span className="flex-1">{article.title}</span>
                  <ExternalLink className="w-3.5 h-3.5 shrink-0 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                </a>
              ) : (
                article.title
              )}
            </h4>

            {/* Summary (optional) */}
            {showSummary && article.summary && (
              <p className="mt-1 text-xs text-gray-500 line-clamp-2">
                {article.summary}
              </p>
            )}

            {/* Bias indicator */}
            {showBias && article.source && (article.source.bias || article.source.factuality) && (
              <div className="mt-1.5">
                <ArticleBiasIndicator
                  bias={article.source.bias}
                  factuality={article.source.factuality}
                  size="sm"
                />
              </div>
            )}

            {/* Metadata badges - always visible */}
            {hasMetadata && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {article.sentiment && (
                  <span className={`inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded ${getSentimentColor(article.sentiment)}`}>
                    <TrendingUp className="w-3 h-3" />
                    {article.sentiment}
                  </span>
                )}
                {article.time_to_impact && (
                  <span className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-blue-100 text-blue-700">
                    <Clock className="w-3 h-3" />
                    {article.time_to_impact}
                  </span>
                )}
                {article.source?.credibility_rating && (
                  <span className="text-xs px-1.5 py-0.5 rounded bg-purple-100 text-purple-700">
                    {article.source.credibility_rating}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Star button */}
          {(onStar || onUnstar) && (
            <button
              onClick={handleStarClick}
              className="p-1 hover:bg-gray-200 rounded transition-colors shrink-0"
              title={isStarred ? 'Remove from briefing' : 'Add to briefing'}
            >
              {isStarred ? (
                <Star className="w-4 h-4 text-yellow-500 fill-yellow-500" />
              ) : (
                <StarOff className="w-4 h-4 text-gray-300 group-hover:text-gray-400" />
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
