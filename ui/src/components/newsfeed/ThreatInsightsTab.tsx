/**
 * ThreatInsightsTab Component
 * LLM-generated threat intelligence narratives
 */

import { useState, useEffect, useCallback } from 'react';
import { Sparkles, RefreshCw, Clock, Download, AlertTriangle, TrendingUp, Shield, Lightbulb } from 'lucide-react';
import {
  getNarratives,
  generateNarrative,
  type ThreatNarrative,
} from '../../services/threatIntelligenceApi';

interface ThreatInsightsTabProps {
  loading: boolean;
}

export function ThreatInsightsTab({ loading: parentLoading }: ThreatInsightsTabProps) {
  const [narratives, setNarratives] = useState<ThreatNarrative[]>([]);
  const [selectedNarrative, setSelectedNarrative] = useState<ThreatNarrative | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);

  const fetchNarratives = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getNarratives(1, 20);
      setNarratives(result.data);
      if (result.data.length > 0 && !selectedNarrative) {
        setSelectedNarrative(result.data[0]);
      }
    } catch (error) {
      console.error('Error fetching narratives:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchNarratives();
  }, [fetchNarratives]);

  const handleGenerateNarrative = async () => {
    setGenerating(true);
    try {
      const narrative = await generateNarrative('weekly');
      setNarratives((prev) => [narrative, ...prev]);
      setSelectedNarrative(narrative);
    } catch (error) {
      console.error('Error generating narrative:', error);
    } finally {
      setGenerating(false);
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const parseNarrativeContent = (content: string) => {
    const sections: { title: string; content: string; icon: any }[] = [];

    // Try to parse as structured sections
    const sectionPatterns = [
      { pattern: /## Executive Summary\n([\s\S]*?)(?=##|$)/i, title: 'Executive Summary', icon: Sparkles },
      { pattern: /## Threat Landscape Analysis\n([\s\S]*?)(?=##|$)/i, title: 'Threat Landscape', icon: TrendingUp },
      { pattern: /## Emerging Threats\n([\s\S]*?)(?=##|$)/i, title: 'Emerging Threats', icon: AlertTriangle },
      { pattern: /## Defensive Recommendations\n([\s\S]*?)(?=##|$)/i, title: 'Recommendations', icon: Shield },
      { pattern: /## Key Insights\n([\s\S]*?)(?=##|$)/i, title: 'Key Insights', icon: Lightbulb },
    ];

    for (const { pattern, title, icon } of sectionPatterns) {
      const match = content.match(pattern);
      if (match && match[1].trim()) {
        sections.push({ title, content: match[1].trim(), icon });
      }
    }

    // If no sections found, treat entire content as one section
    if (sections.length === 0) {
      sections.push({ title: 'Intelligence Briefing', content, icon: Sparkles });
    }

    return sections;
  };

  const downloadNarrative = (narrative: ThreatNarrative) => {
    const blob = new Blob([narrative.content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `threat-briefing-${narrative.period_type}-${new Date(narrative.period_start).toISOString().split('T')[0]}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (loading || parentLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-red-500"></div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
      {/* Narrative List */}
      <div className="lg:col-span-1 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            Intelligence Briefings
          </h3>
          <button
            onClick={handleGenerateNarrative}
            disabled={generating}
            className="flex items-center gap-1 px-2 py-1 text-xs bg-red-500 text-white rounded hover:bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {generating ? (
              <>
                <RefreshCw className="w-3 h-3 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Sparkles className="w-3 h-3" />
                Generate New
              </>
            )}
          </button>
        </div>

        <div className="space-y-2 max-h-[600px] overflow-y-auto">
          {narratives.length === 0 ? (
            <div className="text-center py-8">
              <Sparkles className="w-10 h-10 text-gray-300 dark:text-gray-600 mx-auto mb-2" />
              <p className="text-sm text-gray-500 dark:text-gray-400">No briefings generated yet</p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                Click "Generate New" to create a threat intelligence briefing
              </p>
            </div>
          ) : (
            narratives.map((narrative) => (
              <button
                key={narrative.id}
                onClick={() => setSelectedNarrative(narrative)}
                className={`w-full text-left p-3 rounded-lg border transition-all ${
                  selectedNarrative?.id === narrative.id
                    ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
                    : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-red-300 dark:hover:border-red-700'
                }`}
              >
                <div className="flex items-start gap-2">
                  <Sparkles
                    className={`w-4 h-4 mt-0.5 flex-shrink-0 ${
                      selectedNarrative?.id === narrative.id
                        ? 'text-red-500'
                        : 'text-gray-400'
                    }`}
                  />
                  <div className="min-w-0">
                    <div className="font-medium text-sm text-gray-900 dark:text-gray-100 capitalize">
                      {narrative.period_type} Briefing
                    </div>
                    <div className="flex items-center gap-1 mt-1 text-xs text-gray-500 dark:text-gray-400">
                      <Clock className="w-3 h-3" />
                      {formatDate(narrative.created_at)}
                    </div>
                    <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      {narrative.threat_count} threats • {narrative.actor_count} actors
                    </div>
                  </div>
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Narrative Content */}
      <div className="lg:col-span-3">
        {selectedNarrative ? (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 capitalize">
                  {selectedNarrative.period_type} Threat Intelligence Briefing
                </h2>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                  Period: {new Date(selectedNarrative.period_start).toLocaleDateString()} -{' '}
                  {new Date(selectedNarrative.period_end).toLocaleDateString()}
                </p>
              </div>
              <button
                onClick={() => downloadNarrative(selectedNarrative)}
                className="flex items-center gap-1 px-3 py-1.5 text-sm border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
              >
                <Download className="w-4 h-4" />
                Export
              </button>
            </div>

            {/* Stats Bar */}
            <div className="grid grid-cols-3 gap-4 p-4 bg-gray-50 dark:bg-gray-700/50 border-b border-gray-200 dark:border-gray-700">
              <div className="text-center">
                <div className="text-xl font-bold text-red-600">{selectedNarrative.threat_count}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Threats Analyzed</div>
              </div>
              <div className="text-center">
                <div className="text-xl font-bold text-orange-600">{selectedNarrative.actor_count}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Actors Tracked</div>
              </div>
              <div className="text-center">
                <div className="text-xl font-bold text-blue-600">{selectedNarrative.article_count}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">Sources Processed</div>
              </div>
            </div>

            {/* Content Sections */}
            <div className="p-6 space-y-6">
              {parseNarrativeContent(selectedNarrative.content).map((section, index) => (
                <div key={index} className="space-y-3">
                  <div className="flex items-center gap-2">
                    <section.icon className="w-5 h-5 text-red-500" />
                    <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                      {section.title}
                    </h3>
                  </div>
                  <div className="prose prose-sm dark:prose-invert max-w-none">
                    <div className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed">
                      {section.content.split('\n').map((paragraph, pIndex) => {
                        // Handle bullet points
                        if (paragraph.trim().startsWith('- ') || paragraph.trim().startsWith('* ')) {
                          return (
                            <div key={pIndex} className="flex items-start gap-2 ml-4 my-1">
                              <span className="text-red-500 mt-1">•</span>
                              <span>{paragraph.trim().substring(2)}</span>
                            </div>
                          );
                        }
                        // Handle numbered lists
                        if (/^\d+\.\s/.test(paragraph.trim())) {
                          const [num, ...rest] = paragraph.trim().split('. ');
                          return (
                            <div key={pIndex} className="flex items-start gap-2 ml-4 my-1">
                              <span className="text-red-500 font-medium">{num}.</span>
                              <span>{rest.join('. ')}</span>
                            </div>
                          );
                        }
                        // Regular paragraphs
                        if (paragraph.trim()) {
                          return (
                            <p key={pIndex} className="my-2">
                              {paragraph}
                            </p>
                          );
                        }
                        return null;
                      })}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Footer */}
            <div className="px-6 py-4 bg-gray-50 dark:bg-gray-700/50 border-t border-gray-200 dark:border-gray-700 rounded-b-lg">
              <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                <span>Generated by AI-powered threat analysis</span>
                <span>Created: {formatDate(selectedNarrative.created_at)}</span>
              </div>
            </div>
          </div>
        ) : (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-12 text-center">
            <Sparkles className="w-16 h-16 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">
              AI-Powered Threat Intelligence
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md mx-auto">
              Generate comprehensive threat intelligence briefings using advanced AI analysis.
              Each briefing synthesizes current threat data into actionable insights.
            </p>
            <button
              onClick={handleGenerateNarrative}
              disabled={generating}
              className="mt-6 flex items-center gap-2 px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors mx-auto"
            >
              {generating ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Generating Briefing...
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  Generate Intelligence Briefing
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
