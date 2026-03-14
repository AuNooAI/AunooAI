/**
 * ThreatInsightsTab Component
 * LLM-generated threat intelligence narratives
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { Sparkles, RefreshCw, Clock, Download, AlertTriangle, TrendingUp, Shield, Lightbulb, X, FileText, FileDown, ChevronDown } from 'lucide-react';
import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';
import {
  getNarratives,
  generateNarrative,
  deleteNarrative,
  type ThreatNarrative,
} from '../../services/threatIntelligenceApi';

interface ThreatInsightsTabProps {
  loading?: boolean;
  stats?: any;
  threats?: any[];
  model?: string;
}

export function ThreatInsightsTab({ loading: parentLoading, model = 'gpt-4o-mini' }: ThreatInsightsTabProps) {
  const [narratives, setNarratives] = useState<ThreatNarrative[]>([]);
  const [selectedNarrative, setSelectedNarrative] = useState<ThreatNarrative | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const [exporting, setExporting] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);

  const fetchNarratives = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getNarratives(1, 20);
      setNarratives(result.data);
      if (result.data.length > 0) {
        setSelectedNarrative(result.data[0]);
      }
    } catch (error) {
      console.error('Error fetching narratives:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch on mount
  useEffect(() => {
    fetchNarratives();
  }, [fetchNarratives]);

  // Close export menu when clicking outside
  useEffect(() => {
    const handleClickOutside = () => setShowExportMenu(false);
    if (showExportMenu) {
      document.addEventListener('click', handleClickOutside);
      return () => document.removeEventListener('click', handleClickOutside);
    }
  }, [showExportMenu]);

  const handleDeleteNarrative = async (narrativeId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this briefing?')) return;

    setDeleting(narrativeId);
    try {
      await deleteNarrative(narrativeId);
      setNarratives((prev) => prev.filter((n) => n.id !== narrativeId));
      if (selectedNarrative?.id === narrativeId) {
        const remaining = narratives.filter((n) => n.id !== narrativeId);
        setSelectedNarrative(remaining.length > 0 ? remaining[0] : null);
      }
    } catch (error) {
      console.error('Error deleting narrative:', error);
    } finally {
      setDeleting(null);
    }
  };

  const handleGenerateNarrative = async () => {
    setGenerating(true);
    try {
      const narrative = await generateNarrative('weekly', undefined, model);
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

    // Guard against undefined/null content
    if (!content) {
      return sections;
    }

    // Try to parse as structured sections (allow optional whitespace after header)
    const sectionPatterns = [
      { pattern: /## Executive Summary\s*\n([\s\S]*?)(?=##|$)/i, title: 'Executive Summary', icon: Sparkles },
      { pattern: /## Threat Landscape Analysis\s*\n([\s\S]*?)(?=##|$)/i, title: 'Threat Landscape', icon: TrendingUp },
      { pattern: /## Emerging Threats\s*\n([\s\S]*?)(?=##|$)/i, title: 'Emerging Threats', icon: AlertTriangle },
      { pattern: /## Defensive Recommendations\s*\n([\s\S]*?)(?=##|$)/i, title: 'Recommendations', icon: Shield },
      { pattern: /## Key Insights\s*\n([\s\S]*?)(?=##|$)/i, title: 'Key Insights', icon: Lightbulb },
      { pattern: /## Sources\s*\n([\s\S]*?)(?=##|$)/i, title: 'Sources', icon: FileText },
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
    setShowExportMenu(false);
  };

  const exportToPDF = async (narrative: ThreatNarrative) => {
    if (!contentRef.current) return;

    setExporting(true);
    setShowExportMenu(false);

    try {
      const canvas = await html2canvas(contentRef.current, {
        scale: 2,
        useCORS: true,
        logging: false,
        backgroundColor: '#ffffff',
      });

      const imgData = canvas.toDataURL('image/png');
      const pdf = new jsPDF({
        orientation: 'portrait',
        unit: 'mm',
        format: 'a4',
      });

      const pdfWidth = pdf.internal.pageSize.getWidth();
      const pdfHeight = pdf.internal.pageSize.getHeight();
      const imgWidth = canvas.width;
      const imgHeight = canvas.height;
      const ratio = Math.min(pdfWidth / imgWidth, pdfHeight / imgHeight);
      const imgX = (pdfWidth - imgWidth * ratio) / 2;
      const imgY = 10;

      // Calculate how many pages we need
      const scaledHeight = imgHeight * ratio * (pdfWidth / imgWidth);
      const pageHeight = pdfHeight - 20; // margins
      const totalPages = Math.ceil(scaledHeight / pageHeight);

      if (totalPages === 1) {
        pdf.addImage(imgData, 'PNG', imgX, imgY, imgWidth * ratio, imgHeight * ratio);
      } else {
        // Multi-page PDF
        let remainingHeight = imgHeight;
        let sourceY = 0;

        for (let page = 0; page < totalPages; page++) {
          if (page > 0) {
            pdf.addPage();
          }

          const sliceHeight = Math.min(remainingHeight, (pageHeight / ratio) * (imgWidth / pdfWidth));

          pdf.addImage(
            imgData,
            'PNG',
            0,
            imgY - (sourceY * ratio * (pdfWidth / imgWidth)),
            pdfWidth,
            imgHeight * ratio * (pdfWidth / imgWidth)
          );

          sourceY += sliceHeight;
          remainingHeight -= sliceHeight;
        }
      }

      const filename = `threat-briefing-${narrative.period_type}-${new Date(narrative.period_start).toISOString().split('T')[0]}.pdf`;
      pdf.save(filename);
    } catch (error) {
      console.error('Error generating PDF:', error);
    } finally {
      setExporting(false);
    }
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
              <div
                key={narrative.id}
                onClick={() => setSelectedNarrative(narrative)}
                className={`relative w-full text-left p-3 rounded-lg border transition-all cursor-pointer group ${
                  selectedNarrative?.id === narrative.id
                    ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
                    : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-red-300 dark:hover:border-red-700'
                }`}
              >
                <button
                  onClick={(e) => handleDeleteNarrative(narrative.id, e)}
                  disabled={deleting === narrative.id}
                  className="absolute top-2 right-2 p-1 text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-50"
                  title="Delete briefing"
                >
                  {deleting === narrative.id ? (
                    <RefreshCw className="w-3 h-3 animate-spin" />
                  ) : (
                    <X className="w-3 h-3" />
                  )}
                </button>
                <div className="flex items-start gap-2 pr-6">
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
              </div>
            ))
          )}
        </div>
      </div>

      {/* Narrative Content */}
      <div className="lg:col-span-3">
        {selectedNarrative ? (
          <div ref={contentRef} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 capitalize">
                  {selectedNarrative.period_type} Threat Intelligence Briefing
                </h2>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                  Period: {selectedNarrative.period_start ? new Date(selectedNarrative.period_start).toLocaleDateString() : 'N/A'} -{' '}
                  {selectedNarrative.period_end ? new Date(selectedNarrative.period_end).toLocaleDateString() : 'N/A'}
                </p>
              </div>
              <div className="relative">
                <button
                  onClick={() => setShowExportMenu(!showExportMenu)}
                  disabled={exporting}
                  className="flex items-center gap-1 px-3 py-1.5 text-sm border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors disabled:opacity-50"
                >
                  {exporting ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <Download className="w-4 h-4" />
                  )}
                  Export
                  <ChevronDown className="w-3 h-3" />
                </button>
                {showExportMenu && (
                  <div className="absolute right-0 mt-1 w-40 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-10">
                    <button
                      onClick={() => downloadNarrative(selectedNarrative)}
                      className="flex items-center gap-2 w-full px-3 py-2 text-sm text-left hover:bg-gray-50 dark:hover:bg-gray-700 rounded-t-lg"
                    >
                      <FileText className="w-4 h-4" />
                      Markdown (.md)
                    </button>
                    <button
                      onClick={() => exportToPDF(selectedNarrative)}
                      className="flex items-center gap-2 w-full px-3 py-2 text-sm text-left hover:bg-gray-50 dark:hover:bg-gray-700 rounded-b-lg"
                    >
                      <FileDown className="w-4 h-4" />
                      PDF (.pdf)
                    </button>
                  </div>
                )}
              </div>
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
                        // Function to parse markdown (links and bold) into rendered elements
                        const parseMarkdown = (text: string) => {
                          // Combined regex for links [text](url) and bold **text**
                          const markdownRegex = /\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*/g;
                          const parts: (string | JSX.Element)[] = [];
                          let lastIndex = 0;
                          let match;
                          let keyIndex = 0;

                          while ((match = markdownRegex.exec(text)) !== null) {
                            // Add text before the match
                            if (match.index > lastIndex) {
                              parts.push(text.substring(lastIndex, match.index));
                            }

                            if (match[1] && match[2]) {
                              // It's a link [text](url)
                              parts.push(
                                <a
                                  key={`link-${pIndex}-${keyIndex++}`}
                                  href={match[2]}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-blue-600 dark:text-blue-400 hover:underline"
                                >
                                  {match[1]}
                                </a>
                              );
                            } else if (match[3]) {
                              // It's bold **text**
                              parts.push(
                                <strong key={`bold-${pIndex}-${keyIndex++}`} className="font-semibold text-gray-900 dark:text-gray-100">
                                  {match[3]}
                                </strong>
                              );
                            }
                            lastIndex = match.index + match[0].length;
                          }
                          // Add remaining text
                          if (lastIndex < text.length) {
                            parts.push(text.substring(lastIndex));
                          }
                          return parts.length > 0 ? parts : text;
                        };

                        // Handle bullet points
                        if (paragraph.trim().startsWith('- ') || paragraph.trim().startsWith('* ')) {
                          return (
                            <div key={pIndex} className="flex items-start gap-2 ml-4 my-1">
                              <span className="text-red-500 mt-1">•</span>
                              <span>{parseMarkdown(paragraph.trim().substring(2))}</span>
                            </div>
                          );
                        }
                        // Handle numbered lists
                        if (/^\d+\.\s/.test(paragraph.trim())) {
                          const [num, ...rest] = paragraph.trim().split('. ');
                          return (
                            <div key={pIndex} className="flex items-start gap-2 ml-4 my-1">
                              <span className="text-red-500 font-medium">{num}.</span>
                              <span>{parseMarkdown(rest.join('. '))}</span>
                            </div>
                          );
                        }
                        // Regular paragraphs
                        if (paragraph.trim()) {
                          return (
                            <p key={pIndex} className="my-2">
                              {parseMarkdown(paragraph)}
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
// Build timestamp: 1769694502
