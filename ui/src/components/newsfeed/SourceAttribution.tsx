/**
 * Source Attribution Component
 * Shows source name with credibility info
 */

import { type ArticleSource } from '../../services/newsFeedApi';
import { ArticleBiasIndicator } from './ArticleBiasIndicator';

interface SourceAttributionProps {
  source: ArticleSource;
  publishedDate?: string;
  showBias?: boolean;
  size?: 'sm' | 'md';
}

export function SourceAttribution({
  source,
  publishedDate,
  showBias = false,
  size = 'sm'
}: SourceAttributionProps) {
  const textSize = size === 'sm' ? 'text-xs' : 'text-sm';

  // Format date
  const formattedDate = publishedDate ? formatRelativeTime(publishedDate) : null;

  // Handle missing source
  if (!source) {
    return (
      <div className={`flex items-center gap-2 ${textSize} text-gray-700 dark:text-gray-300`}>
        <span className="font-medium text-gray-700">Unknown Source</span>
        {formattedDate && (
          <>
            <span className="text-gray-600 dark:text-gray-300">|</span>
            <span>{formattedDate}</span>
          </>
        )}
      </div>
    );
  }

  return (
    <div className={`flex items-center gap-2 ${textSize} text-gray-700 dark:text-gray-300`}>
      <span className="font-medium text-gray-700">{source.name || 'Unknown'}</span>
      {source.country && (
        <span className="text-gray-600 dark:text-gray-300">({source.country})</span>
      )}
      {formattedDate && (
        <>
          <span className="text-gray-600 dark:text-gray-300">|</span>
          <span>{formattedDate}</span>
        </>
      )}
      {showBias && (source.bias || source.factuality) && (
        <>
          <span className="text-gray-600 dark:text-gray-300">|</span>
          <ArticleBiasIndicator
            bias={source.bias}
            factuality={source.factuality}
            size="sm"
          />
        </>
      )}
    </div>
  );
}

function formatRelativeTime(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    // For older dates, show the actual date
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric'
    });
  } catch {
    return dateStr;
  }
}
