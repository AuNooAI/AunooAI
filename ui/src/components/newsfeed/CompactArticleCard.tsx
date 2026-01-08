/**
 * Compact Article Card - Small format for related articles and lists
 * Used in sidebars, "more headlines" sections, and article lists
 */

import { ExternalLink, Star, StarOff, Calendar } from 'lucide-react';
import { type NewsArticle } from '../../services/newsFeedApi';
import { getCategoryBadgeColor, getSentimentDotColor, formatDate } from './cardUtils';

interface CompactArticleCardProps {
  article: NewsArticle;
  isStarred?: boolean;
  onStar?: (uri: string) => void;
  onUnstar?: (uri: string) => void;
  showSummary?: boolean;
  showCategory?: boolean;
  onClick?: (article: NewsArticle) => void;
}

export function CompactArticleCard({
  article,
  isStarred = false,
  onStar,
  onUnstar,
  showSummary = true,
  showCategory = true,
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

  return (
    <div
      className={`group py-3 border-b border-gray-100 dark:border-gray-700 last:border-b-0 hover:bg-gray-50 dark:hover:bg-gray-800 px-3 -mx-3 rounded transition-colors ${onClick ? 'cursor-pointer' : ''}`}
      onClick={handleCardClick}
    >
      <div className="flex items-start gap-3">
        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Header: Category + Sentiment */}
          <div className="flex items-center gap-2 mb-1.5">
            {showCategory && article.category && (
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${getCategoryBadgeColor(article.category)}`}>
                {article.category}
              </span>
            )}
            {article.sentiment && (
              <span
                className={`w-2 h-2 rounded-full ${getSentimentDotColor(article.sentiment)}`}
                title={article.sentiment}
              />
            )}
          </div>

          {/* Title */}
          <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors line-clamp-2">
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
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 line-clamp-2">
              {article.summary}
            </p>
          )}

          {/* Footer: Date + Source */}
          <div className="mt-2 flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
            <div className="flex items-center gap-1">
              <Calendar className="w-3 h-3" />
              <span>{formatDate(article.publication_date)}</span>
            </div>
            {article.source?.name && (
              <a
                href={article.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 dark:text-blue-400 hover:underline truncate"
                onClick={(e) => e.stopPropagation()}
              >
                {article.source.name}
              </a>
            )}
          </div>
        </div>

        {/* Star button */}
        {(onStar || onUnstar) && (
          <button
            onClick={handleStarClick}
            className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-colors shrink-0"
            title={isStarred ? 'Remove from briefing' : 'Add to briefing'}
          >
            {isStarred ? (
              <Star className="w-4 h-4 text-yellow-500 fill-yellow-500" />
            ) : (
              <StarOff className="w-4 h-4 text-gray-300 dark:text-gray-500 group-hover:text-gray-400" />
            )}
          </button>
        )}
      </div>
    </div>
  );
}
