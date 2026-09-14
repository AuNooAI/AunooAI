import React from 'react';
import type { NewsArticle } from '../../services/newsFeedApi';

/**
 * The headline as collected, shown under its English translation. Renders
 * nothing for articles that were English to begin with.
 */
export const OriginalTitle: React.FC<{ article: Pick<NewsArticle, 'title' | 'original_title'>; className?: string }> = ({ article, className = '' }) => {
  if (!article.original_title || article.original_title === article.title) return null;
  return (
    <p className={`text-xs text-gray-500 dark:text-gray-400 line-clamp-1 ${className}`} lang="" title={article.original_title}>
      {article.original_title}
    </p>
  );
};

/**
 * The post or description as collected, behind a "Show original" toggle under
 * its English translation. Renders nothing for text that was English already.
 */
export const OriginalSummary: React.FC<{ article: Pick<NewsArticle, 'summary' | 'original_summary'>; className?: string }> = ({ article, className = '' }) => {
  const [open, setOpen] = React.useState(false);
  if (!article.original_summary || article.original_summary === article.summary) return null;
  return (
    <div className={className}>
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
      >
        {open ? 'Hide original' : 'Show original'}
      </button>
      {open && (
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-400 whitespace-pre-line" lang="">
          {article.original_summary}
        </p>
      )}
    </div>
  );
};
