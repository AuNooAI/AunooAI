/**
 * Narrative Theme Card - Individual narrative/theme display
 * Shows AI-identified narrative patterns with expandable article list
 */

import { useState } from 'react';
import { ChevronDown, ChevronUp, Calendar, ExternalLink } from 'lucide-react';
import { type TopStory, type RelatedArticle } from '../../services/newsFeedApi';
import { Card, CardContent } from '../ui/card';
import { formatDate } from './cardUtils';

interface NarrativeThemeCardProps {
  story: TopStory;
  expanded?: boolean;
  onToggleExpand?: () => void;
}

export function NarrativeThemeCard({
  story,
  expanded: controlledExpanded,
  onToggleExpand
}: NarrativeThemeCardProps) {
  const [internalExpanded, setInternalExpanded] = useState(false);

  // Support both controlled and uncontrolled modes
  const isExpanded = controlledExpanded !== undefined ? controlledExpanded : internalExpanded;
  const handleToggle = () => {
    if (onToggleExpand) {
      onToggleExpand();
    } else {
      setInternalExpanded(!internalExpanded);
    }
  };

  const articleCount = (story.related_articles?.length || 0) + 1; // +1 for primary

  return (
    <Card className="overflow-hidden bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 hover:shadow-md transition-shadow">
      <CardContent className="p-4">
        {/* Header: Articles label + See More/Less */}
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-medium text-gray-700 dark:text-gray-300 dark:text-gray-600 dark:text-gray-400 uppercase tracking-wide">
            Articles
          </span>
          <button
            onClick={handleToggle}
            className="flex items-center gap-1 text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 transition-colors"
          >
            {isExpanded ? (
              <>
                <ChevronUp className="w-4 h-4" />
                See Less
              </>
            ) : (
              <>
                <ChevronDown className="w-4 h-4" />
                See More
              </>
            )}
          </button>
        </div>

        {/* Theme Title */}
        <h3 className="font-semibold text-gray-900 dark:text-gray-100 line-clamp-2 mb-2">
          {story.headline}
        </h3>

        {/* Theme Description */}
        <p className={`text-sm text-gray-600 dark:text-gray-600 dark:text-gray-400 ${isExpanded ? '' : 'line-clamp-3'}`}>
          {story.summary}
        </p>

        {/* Expanded Content: Articles in Theme */}
        {isExpanded && (
          <div className="mt-4 pt-4 border-t border-gray-300 dark:border-gray-700 dark:border-gray-700">
            <h4 className="text-xs font-medium text-gray-700 dark:text-gray-300 dark:text-gray-600 dark:text-gray-400 uppercase tracking-wide mb-3">
              Articles in Theme
            </h4>

            <div className="space-y-3">
              {/* Primary Article */}
              <ArticleListItem
                title={story.primary_article.title}
                url={story.primary_article.url}
                source={story.primary_article.source.name}
                date={story.primary_article.publication_date}
              />

              {/* Related Articles */}
              {story.related_articles?.map((article, i) => (
                <ArticleListItem
                  key={i}
                  title={article.title}
                  url={article.url}
                  source={article.source}
                  date={article.publication_date}
                />
              ))}
            </div>
          </div>
        )}

        {/* Factuality Assessment (if available, shown when expanded) */}
        {isExpanded && story.factuality_assessment && (
          <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-900 rounded-lg border-l-4 border-blue-500">
            <p className="text-sm text-gray-600 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400">
              <span className="font-medium text-gray-700 dark:text-gray-600 dark:text-gray-600 dark:text-gray-600 dark:text-gray-400">Assessment: </span>
              {story.factuality_assessment}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface ArticleListItemProps {
  title: string;
  url?: string;
  source?: string;
  date?: string;
}

function ArticleListItem({ title, url, source, date }: ArticleListItemProps) {
  return (
    <div className="group flex items-start gap-3">
      {/* Date */}
      <div className="flex items-center gap-1 text-xs text-gray-700 dark:text-gray-300 dark:text-gray-600 dark:text-gray-400 shrink-0 w-24">
        <Calendar className="w-3.5 h-3.5" />
        <span>{formatDate(date)}</span>
      </div>

      {/* Title + Source */}
      <div className="flex-1 min-w-0">
        <a
          href={url || '#'}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-gray-900 dark:text-gray-100 hover:text-blue-600 dark:hover:text-blue-400 line-clamp-1 flex items-center gap-1"
        >
          {title}
          <ExternalLink className="w-3 h-3 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
        </a>
        {source && (
          <a
            href={url || '#'}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
          >
            {source}
          </a>
        )}
      </div>
    </div>
  );
}
