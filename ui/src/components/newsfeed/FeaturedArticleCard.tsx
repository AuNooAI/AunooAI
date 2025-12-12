/**
 * Featured Article Card - Large format for hero/featured stories
 * Used in "Your Briefing" section and as category featured items
 */

import { ExternalLink, Star, StarOff, Clock } from 'lucide-react';
import { type NewsArticle } from '../../services/newsFeedApi';
import { SourceAttribution } from './SourceAttribution';
import { ArticleBiasIndicator } from './ArticleBiasIndicator';
import { Card, CardContent } from '../ui/card';

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
      className={`group hover:shadow-lg transition-shadow duration-200 overflow-hidden h-full ${onClick ? 'cursor-pointer' : ''}`}
      onClick={handleCardClick}
    >
      <CardContent className="p-0 h-full flex flex-col">
        {/* Image placeholder - could be replaced with actual article images */}
        <div className="relative h-48 bg-gradient-to-br from-pink-100 to-purple-100 flex items-center justify-center">
          {showCategory && article.category && (
            <span className="absolute top-3 left-3 bg-pink-500 text-white text-xs px-2 py-1 rounded font-medium">
              {article.category}
            </span>
          )}
          <span className="text-6xl opacity-20">
            {getCategoryEmoji(article.category)}
          </span>
          {(onStar || onUnstar) && (
            <button
              onClick={handleStarClick}
              className="absolute top-3 right-3 p-1.5 bg-white/80 hover:bg-white rounded-full shadow-sm transition-colors"
              title={isStarred ? 'Remove from briefing' : 'Add to briefing'}
            >
              {isStarred ? (
                <Star className="w-4 h-4 text-yellow-500 fill-yellow-500" />
              ) : (
                <StarOff className="w-4 h-4 text-gray-400" />
              )}
            </button>
          )}
        </div>

        {/* Content */}
        <div className="p-4 flex-1 flex flex-col">
          {/* Source and date */}
          <SourceAttribution
            source={article.source}
            publishedDate={article.publication_date}
            size="sm"
          />

          {/* Title */}
          <h3 className="mt-2 text-lg font-semibold text-gray-900 group-hover:text-pink-600 transition-colors line-clamp-2">
            {article.url && !onClick ? (
              <a
                href={article.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-start gap-1"
                onClick={(e) => e.stopPropagation()}
              >
                {article.title}
                <ExternalLink className="w-4 h-4 shrink-0 mt-1 opacity-0 group-hover:opacity-100 transition-opacity" />
              </a>
            ) : (
              article.title
            )}
          </h3>

          {/* Summary */}
          <p className="mt-2 text-sm text-gray-600 line-clamp-3 flex-1">
            {article.summary}
          </p>

          {/* Footer with bias indicators and metadata */}
          <div className="mt-3 flex items-center justify-between">
            <ArticleBiasIndicator
              bias={article.source?.bias}
              factuality={article.source?.factuality}
              showLabels
              size="sm"
            />
            <div className="flex items-center gap-2">
              {article.time_to_impact && (
                <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-blue-100 text-blue-700">
                  <Clock className="w-3 h-3" />
                  {article.time_to_impact}
                </span>
              )}
              {article.sentiment && (
                <span className={`text-xs px-2 py-0.5 rounded ${getSentimentStyle(article.sentiment)}`}>
                  {article.sentiment}
                </span>
              )}
              {article.source?.credibility_rating && (
                <span className="text-xs px-2 py-0.5 rounded bg-purple-100 text-purple-700">
                  {article.source.credibility_rating}
                </span>
              )}
            </div>
          </div>

          {/* Tags */}
          {article.tags.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {article.tags.slice(0, 3).map((tag, i) => (
                <span
                  key={i}
                  className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded"
                >
                  {tag}
                </span>
              ))}
              {article.tags.length > 3 && (
                <span className="text-xs text-gray-400">
                  +{article.tags.length - 3} more
                </span>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function getCategoryEmoji(category?: string): string {
  if (!category) return '\u{1F4F0}'; // newspaper
  const lower = category.toLowerCase();
  if (lower.includes('tech')) return '\u{1F4BB}'; // laptop
  if (lower.includes('business') || lower.includes('finance')) return '\u{1F4B0}'; // money bag
  if (lower.includes('politic')) return '\u{1F3DB}'; // classical building
  if (lower.includes('science')) return '\u{1F52C}'; // microscope
  if (lower.includes('health')) return '\u{1F3E5}'; // hospital
  if (lower.includes('sport')) return '\u{26BD}'; // soccer ball
  if (lower.includes('entertain')) return '\u{1F3AC}'; // clapper board
  if (lower.includes('world') || lower.includes('international')) return '\u{1F30D}'; // globe
  if (lower.includes('security') || lower.includes('cyber')) return '\u{1F512}'; // lock
  return '\u{1F4F0}'; // newspaper
}

function getSentimentStyle(sentiment: string): string {
  const lower = sentiment.toLowerCase();
  if (lower === 'positive' || lower === 'bullish') {
    return 'bg-green-100 text-green-700';
  }
  if (lower === 'negative' || lower === 'bearish') {
    return 'bg-red-100 text-red-700';
  }
  return 'bg-gray-100 text-gray-600';
}
