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
