/**
 * Shared utilities for news card components
 * Category colors, sentiment indicators, and common styling helpers
 */

/**
 * Get category badge color classes based on category name
 */
export function getCategoryBadgeColor(category?: string): string {
  if (!category) return 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300';

  const lower = category.toLowerCase();

  if (lower.includes('politic') || lower.includes('policy') || lower.includes('government')) {
    return 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300';
  }
  if (lower.includes('world') || lower.includes('international') || lower.includes('global')) {
    return 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300';
  }
  if (lower.includes('tech') || lower.includes('ai') || lower.includes('cyber') || lower.includes('software')) {
    return 'bg-teal-100 text-teal-700 dark:bg-teal-900 dark:text-teal-300';
  }
  if (lower.includes('business') || lower.includes('finance') || lower.includes('economy') || lower.includes('market')) {
    return 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300';
  }
  if (lower.includes('us ') || lower.includes('national') || lower.includes('domestic') || lower.includes('america')) {
    return 'bg-pink-100 text-pink-700 dark:bg-pink-900 dark:text-pink-300';
  }
  if (lower.includes('science') || lower.includes('research') || lower.includes('study')) {
    return 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300';
  }
  if (lower.includes('health') || lower.includes('medical') || lower.includes('healthcare')) {
    return 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300';
  }
  if (lower.includes('security') || lower.includes('defense') || lower.includes('military')) {
    return 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300';
  }

  return 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300';
}

/**
 * Get sentiment dot color class
 */
export function getSentimentDotColor(sentiment?: string): string {
  if (!sentiment) return 'bg-gray-400';

  const lower = sentiment.toLowerCase();

  if (lower === 'positive' || lower === 'bullish' || lower === 'hyperbolic' || lower === 'optimistic') {
    return 'bg-green-500';
  }
  if (lower === 'negative' || lower === 'bearish' || lower === 'critical' || lower === 'pessimistic' || lower === 'concerned') {
    return 'bg-red-500';
  }
  if (lower === 'neutral' || lower === 'cautious') {
    return 'bg-yellow-500';
  }

  return 'bg-gray-400';
}

/**
 * Get sentiment text badge style (for expanded views)
 */
export function getSentimentBadgeStyle(sentiment?: string): string {
  if (!sentiment) return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300';

  const lower = sentiment.toLowerCase();

  if (lower === 'positive' || lower === 'bullish' || lower === 'hyperbolic' || lower === 'optimistic') {
    return 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300';
  }
  if (lower === 'negative' || lower === 'bearish' || lower === 'critical' || lower === 'pessimistic' || lower === 'concerned') {
    return 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300';
  }
  if (lower === 'neutral' || lower === 'cautious') {
    return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300';
  }

  return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300';
}

/**
 * Get rating badge color (High/Medium/Low)
 */
export function getRatingBadgeColor(rating?: string): string {
  if (!rating) return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300';

  const lower = rating.toLowerCase();

  if (lower === 'high' || lower === 'very high' || lower === 'strong') {
    return 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300';
  }
  if (lower === 'medium' || lower === 'moderate' || lower === 'mostly factual') {
    return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300';
  }
  if (lower === 'low' || lower === 'very low' || lower === 'weak' || lower === 'mixed') {
    return 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300';
  }

  return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300';
}

/**
 * Format date for display
 */
export function formatDate(dateString?: string): string {
  if (!dateString) return '';

  try {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-GB', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric'
    }).replace(/\//g, '.');
  } catch {
    return dateString;
  }
}

/**
 * Format date as relative time (e.g., "2 hours ago", "3 days ago")
 */
export function formatRelativeTime(dateString?: string): string {
  if (!dateString) return '';

  try {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    // Fall back to formatted date for older articles
    return formatDate(dateString);
  } catch {
    return dateString;
  }
}

/**
 * Get time period label for grouping articles
 */
export function getTimePeriodLabel(dateString?: string): string {
  if (!dateString) return 'Unknown';

  try {
    const date = new Date(dateString);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today.getTime() - 86400000);
    const thisWeek = new Date(today.getTime() - 7 * 86400000);

    if (date >= today) return 'Today';
    if (date >= yesterday) return 'Yesterday';
    if (date >= thisWeek) return 'This Week';
    return 'Earlier';
  } catch {
    return 'Unknown';
  }
}

/**
 * Get type badge color (for incident cards)
 */
export function getTypeBadgeColor(type?: string): string {
  if (!type) return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300';

  const lower = type.toLowerCase();

  if (lower === 'event' || lower === 'announcement') {
    return 'bg-gray-200 text-gray-700 dark:bg-gray-600 dark:text-gray-200';
  }
  if (lower === 'incident' || lower === 'alert') {
    return 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300';
  }
  if (lower === 'trend' || lower === 'pattern') {
    return 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300';
  }

  return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300';
}

/**
 * Get severity badge color
 */
export function getSeverityBadgeColor(severity?: string): string {
  if (!severity) return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300';

  const lower = severity.toLowerCase();

  if (lower === 'critical' || lower === 'high') {
    return 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300';
  }
  if (lower === 'medium' || lower === 'moderate') {
    return 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300';
  }
  if (lower === 'low' || lower === 'minor') {
    return 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300';
  }

  return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300';
}
