/**
 * Featured Article Card - Clean card design for news articles
 * Used in "Your Briefing" section and news feed grid
 */

import { ExternalLink, Star, StarOff, Calendar } from 'lucide-react';
import { type NewsArticle } from '../../services/newsFeedApi';
import { Card, CardContent } from '../ui/card';
import { getCategoryBadgeColor, getSentimentDotColor, formatDate } from './cardUtils';

interface FeaturedArticleCardProps {
  article: NewsArticle;
  isStarred?: boolean;
  onStar?: (uri: string) => void;
  onUnstar?: (uri: string) => void;
  showCategory?: boolean;
  onClick?: (article: NewsArticle) => void;
}

export function FeaturedArticleCard({
  article,
  isStarred = false,
  onStar,
  onUnstar,
  showCategory = true,
  onClick
}: FeaturedArticleCardProps) {
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
    <Card
      className={`group hover:shadow-md transition-all duration-200 overflow-hidden h-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 ${onClick ? 'cursor-pointer' : ''}`}
      onClick={handleCardClick}
    >
      <CardContent className="p-4 h-full flex flex-col">
        {/* Header: Category badge + Star button */}
        <div className="flex items-start justify-between gap-2 mb-3">
          {showCategory && article.category && (
            <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${getCategoryBadgeColor(article.category)}`}>
              {article.category}
            </span>
          )}
          {!article.category && <div />}

          <div className="flex items-center gap-2">
            {/* Sentiment dot */}
            {article.sentiment && (
              <span
                className={`w-2.5 h-2.5 rounded-full ${getSentimentDotColor(article.sentiment)}`}
                title={article.sentiment}
              />
            )}

            {/* Star button */}
            {(onStar || onUnstar) && (
              <button
                onClick={handleStarClick}
                className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors"
                title={isStarred ? 'Remove from briefing' : 'Add to briefing'}
              >
                {isStarred ? (
                  <Star className="w-4 h-4 text-yellow-500 fill-yellow-500" />
                ) : (
                  <StarOff className="w-4 h-4 text-gray-600 dark:text-gray-300 dark:text-gray-700 dark:text-gray-300" />
                )}
              </button>
            )}
          </div>
        </div>

        {/* Title */}
        <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors line-clamp-2 mb-2">
          {article.url && !onClick ? (
            <a
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-start gap-1"
              onClick={(e) => e.stopPropagation()}
            >
              {article.title}
              <ExternalLink className="w-3.5 h-3.5 shrink-0 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity" />
            </a>
          ) : (
            article.title
          )}
        </h3>

        {/* Summary */}
        <p className="text-sm text-gray-600 dark:text-gray-300 line-clamp-3 flex-1 mb-3">
          {article.summary}
        </p>

        {/* Footer: Source + Date */}
        <div className="flex items-center justify-between text-xs text-gray-700 dark:text-gray-300 dark:text-gray-300 pt-3 border-t border-gray-300 dark:border-gray-700 dark:border-gray-700">
          <div className="flex items-center gap-1.5">
            <Calendar className="w-3.5 h-3.5" />
            <span>{formatDate(article.publication_date)}</span>
          </div>

          {article.source?.name && (
            <a
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 dark:text-blue-400 hover:underline truncate max-w-[150px]"
              onClick={(e) => e.stopPropagation()}
            >
              {article.source.name}
            </a>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
