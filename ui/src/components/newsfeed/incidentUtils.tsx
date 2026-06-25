/**
 * Shared utilities for incident display components
 */

import React from 'react';
import { MessageSquare } from 'lucide-react';
import { type Incident, type IncidentArticleMetadata } from '../../services/narrativeExplorerApi';
import { extractSignalTags } from './AgentSignalBadge';

/**
 * Extract all signal tags from an incident's article metadata
 */
export function getIncidentSignalTags(incident: Incident): string[] {
  const allTags: string[] = [];
  if (incident.article_metadata) {
    for (const meta of incident.article_metadata) {
      if (meta.tags) {
        allTags.push(...meta.tags);
      }
    }
  }
  return extractSignalTags(allTags);
}

/**
 * Format a date string for display
 */
export function formatDisplayDate(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return dateStr;

    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = diffMs / (1000 * 60 * 60);
    const diffDays = diffMs / (1000 * 60 * 60 * 24);

    if (diffHours < 1) {
      const mins = Math.floor(diffMs / (1000 * 60));
      return `${mins}m ago`;
    } else if (diffHours < 24) {
      return `${Math.floor(diffHours)}h ago`;
    } else if (diffDays < 7) {
      return `${Math.floor(diffDays)}d ago`;
    } else {
      return date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
    }
  } catch {
    return dateStr;
  }
}

/**
 * Format a timestamp for analyst notes display
 */
export function formatNoteDate(timestamp: string): string {
  try {
    const date = new Date(timestamp);
    return date.toLocaleString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return timestamp;
  }
}

/**
 * Notes count badge component
 */
interface NotesBadgeProps {
  count: number;
}

export function NotesBadge({ count }: NotesBadgeProps) {
  if (count === 0) return null;

  return (
    <span className="flex-shrink-0 inline-flex items-center gap-1 text-[10px] bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 px-1.5 py-0.5 rounded">
      <MessageSquare className="w-3 h-3" />
      {count}
    </span>
  );
}

/**
 * Timeline Ruler - visual timeline display for incidents
 */
interface TimelineRulerProps {
  dates: number[];
}

export function TimelineRuler({ dates }: TimelineRulerProps) {
  if (dates.length === 0) return null;

  const minDate = Math.min(...dates);
  const maxDate = Math.max(...dates);
  const range = maxDate - minDate || 1;

  const formatRulerDate = (ts: number) => {
    const d = new Date(ts);
    return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
  };

  return (
    <div className="mt-2">
      <div className="relative h-2 bg-gray-200 dark:bg-gray-700 rounded-full">
        {dates.map((ts, i) => {
          const pos = ((ts - minDate) / range) * 100;
          return (
            <div
              key={i}
              className="absolute w-2 h-2 bg-pink-500 rounded-full transform -translate-x-1/2"
              style={{ left: `${Math.max(5, Math.min(95, pos))}%` }}
              title={new Date(ts).toLocaleDateString()}
            />
          );
        })}
      </div>
      <div className="flex justify-between text-[10px] text-gray-500 dark:text-gray-400 mt-1">
        <span>{formatRulerDate(minDate)}</span>
        <span>{formatRulerDate(maxDate)}</span>
      </div>
    </div>
  );
}

/**
 * Article Link component for displaying source articles
 */
interface ArticleLinkProps {
  uri: string;
  title?: string;
  source?: string;
  date?: string;
  factualReporting?: string;
  mbfcRating?: string;
  bias?: string;
  onClick?: (article: { uri: string; title?: string }) => void;
}

export function ArticleLink({
  uri,
  title,
  source,
  date,
  factualReporting,
  mbfcRating,
  bias,
  onClick,
}: ArticleLinkProps) {
  const displayTitle = title || uri.split('/').pop() || 'Article';
  const displaySource = source || new URL(uri).hostname.replace('www.', '');

  const handleClick = (e: React.MouseEvent) => {
    if (onClick) {
      e.preventDefault();
      onClick({ uri, title: displayTitle });
    }
  };

  // Quality indicator color
  const getQualityColor = () => {
    if (factualReporting) {
      const fr = factualReporting.toLowerCase();
      if (fr.includes('high') || fr.includes('very high')) return 'text-green-600 dark:text-green-400';
      if (fr.includes('mixed') || fr.includes('mostly')) return 'text-yellow-600 dark:text-yellow-400';
      if (fr.includes('low')) return 'text-red-600 dark:text-red-400';
    }
    return 'text-gray-500 dark:text-gray-400';
  };

  return (
    <div className="flex items-start gap-2 py-1.5 px-2 rounded hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
      <div className="flex-1 min-w-0">
        <a
          href={uri}
          onClick={handleClick}
          className="text-sm text-pink-600 dark:text-pink-400 hover:underline line-clamp-1"
          target="_blank"
          rel="noopener noreferrer"
        >
          {displayTitle}
        </a>
        <div className="flex items-center gap-2 text-[10px] text-gray-500 dark:text-gray-400">
          <span>{displaySource}</span>
          {date && <span>{formatDisplayDate(date)}</span>}
          {factualReporting && (
            <span className={getQualityColor()} title={`Factual Reporting: ${factualReporting}`}>
              {factualReporting}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Merge saved incident data into an AI-generated incident
 */
export function mergeIncidentWithSavedData(
  incident: Incident,
  savedMap: Map<string, Incident>
): Incident {
  const incidentName = incident.name || incident.title;
  const savedData = incidentName ? savedMap.get(incidentName) : null;

  if (!savedData) return incident;

  return {
    ...incident,
    analyst_notes: savedData.analyst_notes,
    _saved_id: savedData._saved_id,
    _saved_at: savedData._saved_at,
  };
}

/**
 * Get analyst name from localStorage with error handling
 */
export function getStoredAnalystName(): string {
  try {
    return localStorage.getItem('aunoo_analyst_name') || '';
  } catch {
    return '';
  }
}

/**
 * Save analyst name to localStorage with error handling
 */
export function setStoredAnalystName(name: string): void {
  try {
    localStorage.setItem('aunoo_analyst_name', name);
  } catch {
    // Ignore localStorage errors
  }
}
