/**
 * Detailed Report Modal - Display rich analysis for briefing articles
 * Shows key facts, notable quotes, context, implications, and talking points
 */

import { createPortal } from 'react-dom';
import {
  X,
  FileText,
  Quote,
  Lightbulb,
  MessageSquare,
  BookOpen,
  Target,
  ExternalLink,
} from 'lucide-react';
import { type TopStory } from '../../services/newsFeedApi';

// Inline URL extraction to avoid dependency on newsFeedApi export
function extractArticleUrl(data: Record<string, unknown> | null | undefined): string {
  if (!data) return '';
  // Try various URL field names
  const url = data.url || data.uri || data.link ||
    (data.primary_article as Record<string, unknown>)?.url ||
    (data.primary_article as Record<string, unknown>)?.uri || '';
  return String(url);
}

interface DetailedReport {
  key_facts?: string[];
  notable_quotes?: string[];
  background_context?: string;
  implications?: string;
  talking_points?: string[];
  full_content_excerpt?: string;
  error?: string;
}

interface DetailedReportModalProps {
  open: boolean;
  onClose: () => void;
  story: TopStory | null;
}

export function DetailedReportModal({ open, onClose, story }: DetailedReportModalProps) {
  if (!open || !story) return null;

  const storyData = story as any;
  const detailedReport: DetailedReport | undefined = storyData.detailed_report;
  const title = storyData.title || storyData.headline || 'Untitled';
  const source = storyData.source || storyData.primary_article?.source?.name || '';
  const url = extractArticleUrl(storyData);
  const executiveTakeaway = storyData.executive_takeaway || '';
  const strategicRelevance = storyData.strategic_relevance || '';

  // If no detailed report or has error, show fallback content
  const hasDetailedReport = detailedReport && !detailedReport.error;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-3xl w-full mx-4 max-h-[90vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between p-5 border-b border-gray-200 dark:border-gray-700">
          <div className="flex-1 pr-4">
            <div className="flex items-center gap-2 mb-2">
              <FileText className="w-5 h-5 text-emerald-500" />
              <span className="text-sm font-medium text-emerald-600 dark:text-emerald-400 uppercase tracking-wide">
                Detailed Analysis
              </span>
            </div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 leading-tight">
              {title}
            </h2>
            {source && (
              <a
                href={url || '#'}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 mt-2 text-sm text-blue-600 dark:text-blue-400 hover:underline"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                {source}
              </a>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {/* Executive Summary Block */}
          {(executiveTakeaway || strategicRelevance) && (
            <div className="p-4 bg-pink-50 dark:bg-pink-900/20 rounded-lg border-l-4 border-pink-500">
              {executiveTakeaway && (
                <div className="mb-3">
                  <h3 className="text-xs font-semibold text-pink-700 dark:text-pink-400 uppercase tracking-wide mb-1">
                    Why This Matters
                  </h3>
                  <p className="text-gray-700 dark:text-gray-300">{executiveTakeaway}</p>
                </div>
              )}
              {strategicRelevance && (
                <div>
                  <h3 className="text-xs font-semibold text-pink-700 dark:text-pink-400 uppercase tracking-wide mb-1">
                    Strategic Relevance
                  </h3>
                  <p className="text-gray-700 dark:text-gray-300">{strategicRelevance}</p>
                </div>
              )}
            </div>
          )}

          {hasDetailedReport ? (
            <>
              {/* Key Facts */}
              {detailedReport?.key_facts && detailedReport.key_facts.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <Lightbulb className="w-4 h-4 text-amber-500" />
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                      Key Facts
                    </h3>
                  </div>
                  <ul className="space-y-2">
                    {detailedReport.key_facts.map((fact, i) => (
                      <li
                        key={i}
                        className="flex items-start gap-2 text-gray-700 dark:text-gray-300"
                      >
                        <span className="text-amber-500 mt-0.5 font-bold">&bull;</span>
                        <span>{fact}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Notable Quotes */}
              {detailedReport?.notable_quotes && detailedReport.notable_quotes.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <Quote className="w-4 h-4 text-purple-500" />
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                      Notable Quotes
                    </h3>
                  </div>
                  <div className="space-y-3">
                    {detailedReport.notable_quotes.map((quote, i) => (
                      <blockquote
                        key={i}
                        className="pl-4 border-l-2 border-purple-300 dark:border-purple-600 italic text-gray-600 dark:text-gray-400"
                      >
                        {quote}
                      </blockquote>
                    ))}
                  </div>
                </div>
              )}

              {/* Background Context */}
              {detailedReport?.background_context && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <BookOpen className="w-4 h-4 text-blue-500" />
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                      Background Context
                    </h3>
                  </div>
                  <p className="text-gray-700 dark:text-gray-300 leading-relaxed">
                    {detailedReport.background_context}
                  </p>
                </div>
              )}

              {/* Implications */}
              {detailedReport?.implications && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <Target className="w-4 h-4 text-red-500" />
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                      Implications
                    </h3>
                  </div>
                  <p className="text-gray-700 dark:text-gray-300 leading-relaxed">
                    {detailedReport.implications}
                  </p>
                </div>
              )}

              {/* Talking Points */}
              {detailedReport?.talking_points && detailedReport.talking_points.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <MessageSquare className="w-4 h-4 text-teal-500" />
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                      Talking Points
                    </h3>
                  </div>
                  <ul className="space-y-2">
                    {detailedReport.talking_points.map((point, i) => (
                      <li
                        key={i}
                        className="flex items-start gap-2 text-gray-700 dark:text-gray-300"
                      >
                        <span className="text-teal-500 mt-0.5 font-bold">{i + 1}.</span>
                        <span>{point}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Full Content Excerpt (collapsed by default) */}
              {detailedReport?.full_content_excerpt && (
                <details className="mt-4">
                  <summary className="cursor-pointer text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300">
                    View article excerpt...
                  </summary>
                  <div className="mt-3 p-4 bg-gray-50 dark:bg-gray-900 rounded-lg text-sm text-gray-600 dark:text-gray-400 max-h-48 overflow-y-auto">
                    <pre className="whitespace-pre-wrap font-sans">
                      {detailedReport.full_content_excerpt}
                    </pre>
                  </div>
                </details>
              )}
            </>
          ) : (
            <div className="text-center py-8">
              <FileText className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
              <p className="text-gray-500 dark:text-gray-400 mb-2">
                {detailedReport?.error
                  ? 'Unable to generate detailed analysis for this article.'
                  : 'No detailed analysis available yet.'}
              </p>
              {detailedReport?.error ? (
                <p className="text-xs text-gray-400 dark:text-gray-500">
                  Error: {detailedReport.error}
                </p>
              ) : (
                <div className="mt-4 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-left max-w-md mx-auto">
                  <p className="text-sm text-blue-700 dark:text-blue-300 mb-2">
                    <strong>To generate detailed analysis:</strong>
                  </p>
                  <ol className="text-sm text-blue-600 dark:text-blue-400 list-decimal list-inside space-y-1">
                    <li>Switch to a different persona (e.g., CTO)</li>
                    <li>Switch back to your preferred persona</li>
                    <li>The briefing will regenerate with full article analysis</li>
                  </ol>
                  <p className="text-xs text-blue-500 dark:text-blue-500 mt-3">
                    This fetches the full article content and extracts key facts, quotes, and talking points.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-gray-200 dark:border-gray-700">
          {url && (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="px-4 py-2 text-sm font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 transition-colors"
            >
              Read Original Article
            </a>
          )}
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-white bg-gray-800 dark:bg-gray-600 rounded-lg hover:bg-gray-700 dark:hover:bg-gray-500 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
