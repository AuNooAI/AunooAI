/**
 * GeopoliticalInsightsTab Component
 * Displays LLM-generated strategic intelligence narratives
 */

import { useState, useEffect, useCallback } from 'react';
import { Sparkles, Loader2, AlertCircle, Clock, FileText, ChevronDown, ChevronUp } from 'lucide-react';
import type { OverviewStats, Hotspot } from '../../services/geopoliticalHotspotsApi';

interface Narrative {
  id: number;
  narrative_text: string;
  executive_summary: string | null;
  regional_analysis: string | null;
  emerging_threats: string | null;
  outlook: string | null;
  hotspot_count: number;
  article_count: number;
  top_regions: string[] | null;
  top_categories: string[] | null;
  risk_breakdown: Record<string, number> | null;
  model_used: string | null;
  topic: string | null;
  generated_at: string | null;
}

interface NarrativeSummary {
  id: number;
  executive_summary: string | null;
  hotspot_count: number;
  article_count: number;
  model_used: string | null;
  topic: string | null;
  generated_at: string | null;
}

interface GeopoliticalInsightsTabProps {
  stats: OverviewStats | null;
  hotspots: Hotspot[];
  loading: boolean;
  model?: string;
}

export function GeopoliticalInsightsTab({
  stats,
  hotspots,
  loading,
  model = 'gpt-4o-mini',
}: GeopoliticalInsightsTabProps) {
  const [generating, setGenerating] = useState(false);
  const [narrative, setNarrative] = useState<Narrative | null>(null);
  const [history, setHistory] = useState<NarrativeSummary[]>([]);
  const [loadingNarrative, setLoadingNarrative] = useState(true);
  const [showHistory, setShowHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch latest narrative on mount
  useEffect(() => {
    fetchLatestNarrative();
    fetchNarrativeHistory();
  }, []);

  const fetchLatestNarrative = async () => {
    setLoadingNarrative(true);
    try {
      const response = await fetch('/api/geopolitical-hotspots/narrative');
      if (response.ok) {
        const data = await response.json();
        setNarrative(data);
      }
    } catch (err) {
      console.error('Failed to fetch narrative:', err);
    } finally {
      setLoadingNarrative(false);
    }
  };

  const fetchNarrativeHistory = async () => {
    try {
      const response = await fetch('/api/geopolitical-hotspots/narratives?limit=5');
      if (response.ok) {
        const data = await response.json();
        setHistory(data);
      }
    } catch (err) {
      console.error('Failed to fetch narrative history:', err);
    }
  };

  const generateNarrative = useCallback(async () => {
    setGenerating(true);
    setError(null);

    try {
      const response = await fetch('/api/geopolitical-hotspots/generate-narrative', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model }),
      });

      const result = await response.json();

      if (response.ok) {
        // Fetch the updated narrative
        await fetchLatestNarrative();
        await fetchNarrativeHistory();
      } else {
        setError(result.detail || 'Failed to generate narrative');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate narrative');
    } finally {
      setGenerating(false);
    }
  }, [model]);

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'Unknown';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (loading || loadingNarrative) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3 text-gray-500 dark:text-gray-400">
          <Loader2 className="w-5 h-5 animate-spin" />
          Loading insights...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-pink-500" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Strategic Intelligence Briefing
          </h3>
        </div>
        <div className="flex items-center gap-2">
          {narrative && (
            <span className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {formatDate(narrative.generated_at)}
            </span>
          )}
          <button
            onClick={generateNarrative}
            disabled={generating || !stats || stats.total_hotspots === 0}
            className="flex items-center gap-2 px-3 py-1.5 text-sm bg-pink-500 text-white rounded-lg hover:bg-pink-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {generating ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                Generate New
              </>
            )}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 rounded-lg text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* No Narrative State */}
      {!narrative && !generating && (
        <div className="flex flex-col items-center justify-center h-64 text-center">
          <FileText className="w-12 h-12 text-gray-400 dark:text-gray-600 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
            No Briefing Available
          </h3>
          <p className="text-gray-500 dark:text-gray-400 mt-1 max-w-md">
            {stats && stats.total_hotspots > 0
              ? 'Click "Generate New" to create a strategic intelligence briefing based on current hotspot data.'
              : 'Process some articles first to create hotspots, then generate a briefing.'}
          </p>
        </div>
      )}

      {/* Narrative Content */}
      {narrative && (
        <>
          {/* Executive Summary */}
          {narrative.executive_summary && (
            <div className="bg-gradient-to-r from-pink-50 to-purple-50 dark:from-pink-900/20 dark:to-purple-900/20 rounded-lg border border-pink-200 dark:border-pink-800 p-6">
              <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">
                Executive Summary
              </h4>
              <p className="text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">
                {narrative.executive_summary}
              </p>
            </div>
          )}

          {/* Stats Bar */}
          <div className="flex items-center gap-6 text-sm text-gray-600 dark:text-gray-400">
            <span>
              <strong className="text-gray-900 dark:text-gray-100">{narrative.hotspot_count}</strong> hotspots analyzed
            </span>
            <span>
              <strong className="text-gray-900 dark:text-gray-100">{narrative.article_count}</strong> total articles
            </span>
            {narrative.model_used && (
              <span>
                Model: <strong className="text-gray-900 dark:text-gray-100">{narrative.model_used}</strong>
              </span>
            )}
          </div>

          {/* Regional Analysis */}
          {narrative.regional_analysis && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">
                Regional Analysis
              </h4>
              <div className="text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">
                {narrative.regional_analysis}
              </div>
            </div>
          )}

          {/* Emerging Threats */}
          {narrative.emerging_threats && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">
                Emerging Threats
              </h4>
              <div className="text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">
                {narrative.emerging_threats}
              </div>
            </div>
          )}

          {/* Strategic Outlook */}
          {narrative.outlook && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">
                Strategic Outlook
              </h4>
              <div className="text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">
                {narrative.outlook}
              </div>
            </div>
          )}

          {/* Full Narrative (fallback if sections not parsed) */}
          {!narrative.executive_summary && !narrative.regional_analysis && narrative.narrative_text && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <div className="prose dark:prose-invert max-w-none text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">
                {narrative.narrative_text}
              </div>
            </div>
          )}

          {/* Priority Hotspots */}
          {stats && stats.top_hotspots.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">
                Priority Attention Areas
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {stats.top_hotspots.slice(0, 6).map((hotspot) => (
                  <div
                    key={hotspot.id}
                    className="p-4 rounded-lg border border-gray-200 dark:border-gray-700 hover:shadow-md transition-shadow"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <h5 className="font-medium text-gray-900 dark:text-gray-100">
                        {hotspot.location_name}
                      </h5>
                      <span
                        className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                          hotspot.risk_level === 'critical'
                            ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                            : hotspot.risk_level === 'high'
                              ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300'
                              : hotspot.risk_level === 'medium'
                                ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300'
                                : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                        }`}
                      >
                        {hotspot.risk_level.toUpperCase()}
                      </span>
                    </div>
                    {hotspot.country_name && (
                      <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
                        {hotspot.country_name}
                      </p>
                    )}
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-gray-600 dark:text-gray-400">
                        {hotspot.article_count} articles
                      </span>
                      {hotspot.trend && (
                        <span
                          className={
                            hotspot.trend === 'escalating'
                              ? 'text-red-500'
                              : hotspot.trend === 'de-escalating'
                                ? 'text-green-500'
                                : 'text-gray-500'
                          }
                        >
                          {hotspot.trend === 'escalating'
                            ? '↑ Escalating'
                            : hotspot.trend === 'de-escalating'
                              ? '↓ De-escalating'
                              : '→ Stable'}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Narrative History */}
          {history.length > 1 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
              <button
                onClick={() => setShowHistory(!showHistory)}
                className="w-full p-4 flex items-center justify-between text-left hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
              >
                <span className="font-medium text-gray-900 dark:text-gray-100">
                  Briefing History ({history.length})
                </span>
                {showHistory ? (
                  <ChevronUp className="w-5 h-5 text-gray-500" />
                ) : (
                  <ChevronDown className="w-5 h-5 text-gray-500" />
                )}
              </button>

              {showHistory && (
                <div className="border-t border-gray-200 dark:border-gray-700 divide-y divide-gray-200 dark:divide-gray-700">
                  {history.map((item) => (
                    <div
                      key={item.id}
                      className={`p-4 ${item.id === narrative.id ? 'bg-pink-50 dark:bg-pink-900/20' : ''}`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                          {formatDate(item.generated_at)}
                        </span>
                        {item.id === narrative.id && (
                          <span className="text-xs text-pink-600 dark:text-pink-400">Current</span>
                        )}
                      </div>
                      <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
                        {item.executive_summary || 'No summary available'}
                      </p>
                      <div className="flex items-center gap-4 mt-2 text-xs text-gray-500 dark:text-gray-400">
                        <span>{item.hotspot_count} hotspots</span>
                        <span>{item.model_used}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
