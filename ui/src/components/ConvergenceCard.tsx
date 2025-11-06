/**
 * Convergence Card Component for Trends Convergence Tab
 */

import { useState } from 'react';
import { Info, ChevronDown, ChevronUp } from 'lucide-react';

interface Article {
  title: string;
  url: string;
  summary: string;
  sentiment?: string;
}

interface ActionItem {
  priority: 'High' | 'Medium' | 'Low';
  action: string;
  timeframe: string;
  owner: string;
  dependencies: string[];
  success_metrics: string[];
}

interface TimeframeAnalysis {
  immediate: string;
  short_term: string;
  mid_term: string;
  key_milestones: {
    year: number;
    milestone: string;
    significance: string;
  }[];
}

interface ConvergenceCardProps {
  name: string;
  description: string;
  consensusPercentage: number;
  timelineStartYear: number;
  timelineEndYear: number;
  optimisticOutlier: {
    year: number;
    description: string;
    source_percentage: number;
  };
  pessimisticOutlier: {
    year: number;
    description: string;
    source_percentage: number;
  };
  strategicImplication: string;
  keyArticles?: Article[];
  color: string; // Color for the timeline bar: purple, orange, blue, green, pink, indigo
  consensusType?: string; // e.g., "Positive Growth", "Mixed Consensus", "Regulatory Response"
  sentimentDistribution?: {
    positive: number;
    neutral: number;
    critical: number;
  };
  timelineConsensus?: string; // e.g., "Short-term (2025-2027)"
  articlesAnalyzed?: number; // Number of articles analyzed
  actionItems?: ActionItem[]; // Action items for this convergence
  timeframeAnalysis?: TimeframeAnalysis; // Timeframe-specific analysis
}

const colorClasses = {
  purple: {
    bg: 'bg-purple-50',
    border: 'border-purple-200',
    bar: 'bg-purple-500',
    badge: 'bg-pink-100 text-pink-700',
  },
  orange: {
    bg: 'bg-orange-50',
    border: 'border-orange-200',
    bar: 'bg-orange-500',
    badge: 'bg-pink-100 text-pink-700',
  },
  blue: {
    bg: 'bg-blue-50',
    border: 'border-blue-200',
    bar: 'bg-blue-500',
    badge: 'bg-pink-100 text-pink-700',
  },
  green: {
    bg: 'bg-green-50',
    border: 'border-green-200',
    bar: 'bg-green-500',
    badge: 'bg-pink-100 text-pink-700',
  },
  pink: {
    bg: 'bg-pink-50',
    border: 'border-pink-200',
    bar: 'bg-pink-500',
    badge: 'bg-pink-100 text-pink-700',
  },
  indigo: {
    bg: 'bg-indigo-50',
    border: 'border-indigo-200',
    bar: 'bg-indigo-500',
    badge: 'bg-pink-100 text-pink-700',
  },
};

export function ConvergenceCard({
  name,
  description,
  consensusPercentage,
  timelineStartYear,
  timelineEndYear,
  optimisticOutlier,
  pessimisticOutlier,
  strategicImplication,
  keyArticles = [],
  color,
  consensusType,
  sentimentDistribution,
  timelineConsensus,
  articlesAnalyzed,
  actionItems,
  timeframeAnalysis,
}: ConvergenceCardProps) {
  const colors = colorClasses[color as keyof typeof colorClasses] || colorClasses.purple;
  const [isExpanded, setIsExpanded] = useState(false);

  // Calculate the position of the consensus bar based on timeline consensus category
  // Using the same approach as skunkworkx for consistent positioning
  const totalYears = timelineEndYear - timelineStartYear;

  // Calculate consensus bar position based on timelineConsensus category
  let consensusStartPercent = 20;
  let consensusWidthPercent = 40;

  if (timelineConsensus) {
    if (timelineConsensus.includes('Immediate')) {
      consensusStartPercent = 2;
      consensusWidthPercent = 18;
    } else if (timelineConsensus.includes('Short-term')) {
      consensusStartPercent = 22;
      consensusWidthPercent = 26;
    } else if (timelineConsensus.includes('Mid-term')) {
      consensusStartPercent = 50;
      consensusWidthPercent = 24;
    } else if (timelineConsensus.includes('Long-term')) {
      consensusStartPercent = 76;
      consensusWidthPercent = 22;
    }
  }

  const consensusEndPercent = 100 - (consensusStartPercent + consensusWidthPercent);

  // Get the actual timeline label based on timelineConsensus or years
  const getTimelineLabel = () => {
    if (timelineConsensus) {
      return timelineConsensus.toUpperCase();
    }
    if (timelineStartYear <= 2025 && timelineEndYear <= 2027) {
      return 'SHORT-TERM (2025-2027)';
    } else if (timelineStartYear <= 2027 && timelineEndYear <= 2030) {
      return 'MID-TERM (2027-2030)';
    } else if (timelineStartYear >= 2030) {
      return 'LONG-TERM (2030-2035+)';
    } else if (timelineStartYear === 2025 && timelineEndYear === 2025) {
      return 'IMMEDIATE (2025)';
    }
    return `${timelineStartYear}-${timelineEndYear}`;
  };

  // Calculate dot positions
  const optimisticPosition = ((optimisticOutlier.year - timelineStartYear) / totalYears) * 100;
  const pessimisticPosition = ((pessimisticOutlier.year - timelineStartYear) / totalYears) * 100;

  const [hoveredElement, setHoveredElement] = useState<string | null>(null);

  return (
    <div className={`${colors.bg} ${colors.border} border rounded-xl p-6 mb-4 cursor-pointer hover:shadow-md transition-shadow`} onClick={() => setIsExpanded(!isExpanded)}>
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <h3 className="text-lg font-bold text-gray-950 mb-1">{name}</h3>
          <p className="text-sm text-gray-700">{description}</p>
        </div>
        <span className={`${colors.badge} px-3 py-1 rounded-full text-xs font-medium ml-4 shrink-0`}>
          {consensusPercentage}% Consensus
        </span>
      </div>

      {/* Timeline Visualization */}
      <div className="mb-6 relative">
        {/* Year labels */}
        <div className="flex justify-between text-xs text-gray-700 mb-2">
          <span>{timelineStartYear}</span>
          <span>{Math.floor((timelineStartYear + timelineEndYear) / 2)}</span>
          <span>{timelineEndYear}</span>
          <span>{timelineEndYear}+</span>
        </div>

        {/* Timeline bar container */}
        <div className="relative h-8">
          {/* Background bar */}
          <div className="absolute top-3 left-0 right-0 h-2 bg-gray-200 rounded-full"></div>

          {/* Consensus bar */}
          <div
            className={`absolute top-3 h-2 ${colors.bar} rounded-full`}
            style={{
              left: `${consensusStartPercent}%`,
              width: `${consensusWidthPercent}%`,
            }}
            title={`Consensus Timeline: ${getTimelineLabel()}\n${consensusPercentage}% of sources agree on this timeframe`}
          >
            <div className="absolute -top-2 left-0 right-0 text-center">
              <span className="text-xs font-medium text-gray-800 bg-white px-2 py-0.5 rounded shadow-sm">
                {consensusPercentage}% • {getTimelineLabel()}
              </span>
            </div>
          </div>

          {/* Optimistic outlier dot (green) */}
          <div
            className="absolute top-1 w-4 h-4 bg-green-500 rounded-full border-2 border-white shadow-md cursor-help hover:scale-125 transition-transform"
            style={{ left: `${optimisticPosition}%`, transform: 'translateX(-50%)' }}
            title={`Optimistic Outlier (${optimisticOutlier.year})\n${optimisticOutlier.description}\n${optimisticOutlier.source_percentage}% of sources`}
            onClick={(e) => e.stopPropagation()}
          ></div>

          {/* Pessimistic outlier dot (red) */}
          <div
            className="absolute top-1 w-4 h-4 bg-red-500 rounded-full border-2 border-white shadow-md cursor-help hover:scale-125 transition-transform"
            style={{ left: `${pessimisticPosition}%`, transform: 'translateX(-50%)' }}
            title={`Pessimistic Outlier (${pessimisticOutlier.year})\n${pessimisticOutlier.description}\n${pessimisticOutlier.source_percentage}% of sources`}
            onClick={(e) => e.stopPropagation()}
          ></div>

          {/* End marker (green checkmark position) */}
          <div className="absolute top-1 right-0 w-4 h-4 bg-green-500 rounded-full border-2 border-white shadow-md transform translate-x-1/2"></div>
        </div>
      </div>

      {/* Details Grid - Collapsible */}
      {isExpanded && (
        <div className="mt-4 pt-4 border-t border-gray-200">
          {/* Consensus Type and Metrics */}
          {(consensusType || sentimentDistribution || articlesAnalyzed) && (
            <div className="mb-6 p-4 bg-gray-50 rounded-lg">
              <div className="grid grid-cols-2 gap-6">
                {/* Left: Consensus Type */}
                {consensusType && (
                  <div>
                    <h6 className="text-xs font-bold text-gray-950 mb-2 uppercase">Consensus Type</h6>
                    <div className="text-sm font-semibold text-gray-800 mb-1">{consensusType}</div>
                    <div className="text-xs text-gray-600">
                      {consensusPercentage}% confidence level
                      {articlesAnalyzed && ` • Based on ${articlesAnalyzed} articles`}
                    </div>
                  </div>
                )}

                {/* Right: Sentiment Distribution */}
                {sentimentDistribution && (
                  <div>
                    <h6 className="text-xs font-bold text-gray-950 mb-2 uppercase">Sentiment Distribution</h6>
                    <div className="space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-gray-700">Positive:</span>
                        <span className="font-semibold text-green-600">{sentimentDistribution.positive}%</span>
                      </div>
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-gray-700">Neutral:</span>
                        <span className="font-semibold text-gray-600">{sentimentDistribution.neutral}%</span>
                      </div>
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-gray-700">Critical:</span>
                        <span className="font-semibold text-red-600">{sentimentDistribution.critical}%</span>
                      </div>
                    </div>
                    {/* Visual bar */}
                    <div className="mt-2 h-2 flex rounded-full overflow-hidden">
                      <div
                        className="bg-green-500"
                        style={{ width: `${sentimentDistribution.positive}%` }}
                      ></div>
                      <div
                        className="bg-gray-400"
                        style={{ width: `${sentimentDistribution.neutral}%` }}
                      ></div>
                      <div
                        className="bg-red-500"
                        style={{ width: `${sentimentDistribution.critical}%` }}
                      ></div>
                    </div>
                  </div>
                )}
              </div>

              {/* Timeline Consensus */}
              {timelineConsensus && (
                <div className="mt-4 pt-4 border-t border-gray-200">
                  <h6 className="text-xs font-bold text-gray-950 mb-1 uppercase">Timeline Consensus</h6>
                  <div className="text-sm text-gray-800">{timelineConsensus}</div>
                  <div className="text-xs text-gray-600 mt-1">
                    Majority of sources expect impacts within this timeframe
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="grid grid-cols-3 gap-4 mb-6">
            {/* Optimistic Outlier */}
            <div className="flex gap-2">
              <div className="w-3 h-3 bg-green-500 rounded-full mt-1 shrink-0"></div>
              <div>
                <div className="text-xs font-semibold text-gray-950 mb-0.5">
                  Optimistic Outlier ({optimisticOutlier.year})
                </div>
                <div className="text-xs text-gray-700 mb-0.5">{optimisticOutlier.description}</div>
                <div className="text-xs text-gray-600">{optimisticOutlier.source_percentage}% of sources</div>
              </div>
            </div>

            {/* Pessimistic Outlier */}
            <div className="flex gap-2">
              <div className="w-3 h-3 bg-red-500 rounded-full mt-1 shrink-0"></div>
              <div>
                <div className="text-xs font-semibold text-gray-950 mb-0.5">
                  Pessimistic Outlier ({pessimisticOutlier.year})
                </div>
                <div className="text-xs text-gray-700 mb-0.5">{pessimisticOutlier.description}</div>
                <div className="text-xs text-gray-600">{pessimisticOutlier.source_percentage}% of sources</div>
              </div>
            </div>

            {/* Strategic Implication */}
            <div className="flex gap-2">
              <div className="w-5 h-5 rounded-full bg-white border-2 border-gray-300 flex items-center justify-center shrink-0">
                <Info className="w-3 h-3 text-gray-700" />
              </div>
              <div>
                <div className="text-xs font-semibold text-gray-950 mb-0.5">Strategic Implication</div>
                <div className="text-xs text-gray-700">{strategicImplication}</div>
              </div>
            </div>
          </div>

          {/* Key Supporting Articles */}
          {keyArticles.length > 0 && (
            <div>
              <h6 className="text-sm font-bold text-gray-950 mb-3">Key Supporting Articles</h6>
              <div className="space-y-2">
                {keyArticles.map((article, index) => {
                  const sentimentColor = article.sentiment === 'positive' ? 'bg-green-100 text-green-700' :
                                        article.sentiment === 'critical' ? 'bg-red-100 text-red-700' :
                                        'bg-gray-100 text-gray-800';

                  return (
                    <div key={index} className="p-3 bg-white rounded-lg border border-gray-200" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <a
                          href={article.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm font-semibold text-gray-950 hover:text-blue-600 flex-1"
                        >
                          {article.title}
                        </a>
                        {article.sentiment && (
                          <span className={`px-2 py-0.5 rounded text-xs font-medium shrink-0 ${sentimentColor}`}>
                            {article.sentiment}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-gray-700 mb-1">{article.summary}</p>
                      <a
                        href={article.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1"
                      >
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                        </svg>
                        External Link
                      </a>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Action Items Section */}
          {actionItems && actionItems.length > 0 && (
            <div className="mt-6 pt-6 border-t border-gray-200">
              <h6 className="text-sm font-bold text-gray-950 mb-3">🎯 Action Items</h6>
              <div className="space-y-3">
                {actionItems.map((item, idx) => {
                  const priorityColor = item.priority === 'High' ? 'bg-red-100 text-red-700 border-red-200' :
                                        item.priority === 'Medium' ? 'bg-yellow-100 text-yellow-700 border-yellow-200' :
                                        'bg-green-100 text-green-700 border-green-200';

                  return (
                    <div key={idx} className={`p-3 ${priorityColor} rounded-lg border`}>
                      <div className="flex items-start gap-2 mb-2">
                        <span className={`px-2 py-0.5 rounded text-xs font-bold ${priorityColor}`}>
                          {item.priority}
                        </span>
                        <span className="text-xs font-medium text-gray-700">{item.timeframe}</span>
                      </div>
                      <div className="text-sm font-semibold text-gray-900 mb-2">{item.action}</div>
                      <div className="flex flex-wrap gap-2 text-xs text-gray-700">
                        <div><strong>Owner:</strong> {item.owner}</div>
                        {item.success_metrics && item.success_metrics.length > 0 && (
                          <div><strong>Metrics:</strong> {item.success_metrics.join(', ')}</div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Timeframe Analysis Section */}
          {timeframeAnalysis && (
            <div className="mt-6 pt-6 border-t border-gray-200">
              <h6 className="text-sm font-bold text-gray-950 mb-3">📅 Timeframe Analysis</h6>
              <div className="space-y-3">
                <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                  <div className="text-xs font-bold text-blue-900 mb-1">⚡ IMMEDIATE (0-6 months)</div>
                  <div className="text-sm text-gray-800">{timeframeAnalysis.immediate}</div>
                </div>
                <div className="p-3 bg-purple-50 border border-purple-200 rounded-lg">
                  <div className="text-xs font-bold text-purple-900 mb-1">📈 SHORT-TERM (6-18 months)</div>
                  <div className="text-sm text-gray-800">{timeframeAnalysis.short_term}</div>
                </div>
                <div className="p-3 bg-indigo-50 border border-indigo-200 rounded-lg">
                  <div className="text-xs font-bold text-indigo-900 mb-1">🔮 MID-TERM (18-36 months)</div>
                  <div className="text-sm text-gray-800">{timeframeAnalysis.mid_term}</div>
                </div>

                {timeframeAnalysis.key_milestones && timeframeAnalysis.key_milestones.length > 0 && (
                  <div className="mt-3 p-3 bg-gray-50 border border-gray-200 rounded-lg">
                    <div className="text-xs font-bold text-gray-900 mb-2">🎯 Key Milestones</div>
                    <div className="space-y-2">
                      {timeframeAnalysis.key_milestones.map((milestone, idx) => (
                        <div key={idx} className="flex gap-3">
                          <div className="w-12 text-xs font-bold text-gray-700 shrink-0">{milestone.year}</div>
                          <div className="flex-1">
                            <div className="text-sm font-medium text-gray-900">{milestone.milestone}</div>
                            <div className="text-xs text-gray-600 mt-1">{milestone.significance}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Expand/Collapse Indicator */}
      <div className="flex justify-center mt-4">
        {isExpanded ? (
          <ChevronUp className="w-5 h-5 text-gray-500" />
        ) : (
          <ChevronDown className="w-5 h-5 text-gray-500" />
        )}
      </div>
    </div>
  );
}
