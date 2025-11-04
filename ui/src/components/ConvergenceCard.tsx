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
}: ConvergenceCardProps) {
  const colors = colorClasses[color as keyof typeof colorClasses] || colorClasses.purple;
  const [isExpanded, setIsExpanded] = useState(false);

  // Calculate the position of the consensus bar (it should span most of the timeline)
  const totalYears = timelineEndYear - timelineStartYear;
  const consensusStart = timelineStartYear + Math.floor(totalYears * 0.1); // Start at 10%
  const consensusEnd = timelineEndYear - Math.floor(totalYears * 0.1); // End at 90%

  // Calculate dot positions
  const optimisticPosition = ((optimisticOutlier.year - timelineStartYear) / totalYears) * 100;
  const pessimisticPosition = ((pessimisticOutlier.year - timelineStartYear) / totalYears) * 100;

  return (
    <div className={`${colors.bg} ${colors.border} border rounded-xl p-6 mb-4 cursor-pointer hover:shadow-md transition-shadow`} onClick={() => setIsExpanded(!isExpanded)}>
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <h3 className="text-lg font-bold text-gray-900 mb-1">{name}</h3>
          <p className="text-sm text-gray-600">{description}</p>
        </div>
        <span className={`${colors.badge} px-3 py-1 rounded-full text-xs font-medium ml-4 shrink-0`}>
          {consensusPercentage}% Consensus
        </span>
      </div>

      {/* Timeline Visualization */}
      <div className="mb-6 relative">
        {/* Year labels */}
        <div className="flex justify-between text-xs text-gray-600 mb-2">
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
              left: '10%',
              right: '10%',
            }}
          >
            <div className="absolute -top-2 left-0 right-0 text-center">
              <span className="text-xs font-medium text-gray-700 bg-white px-2 py-0.5 rounded">
                Consensus
              </span>
            </div>
          </div>

          {/* Optimistic outlier dot (green) */}
          <div
            className="absolute top-1 w-4 h-4 bg-green-500 rounded-full border-2 border-white shadow-md"
            style={{ left: `${optimisticPosition}%`, transform: 'translateX(-50%)' }}
          ></div>

          {/* Pessimistic outlier dot (red) */}
          <div
            className="absolute top-1 w-4 h-4 bg-red-500 rounded-full border-2 border-white shadow-md"
            style={{ left: `${pessimisticPosition}%`, transform: 'translateX(-50%)' }}
          ></div>

          {/* End marker (green checkmark position) */}
          <div className="absolute top-1 right-0 w-4 h-4 bg-green-500 rounded-full border-2 border-white shadow-md transform translate-x-1/2"></div>
        </div>
      </div>

      {/* Details Grid - Collapsible */}
      {isExpanded && (
        <div className="mt-4 pt-4 border-t border-gray-200">
          <div className="grid grid-cols-3 gap-4 mb-6">
            {/* Optimistic Outlier */}
            <div className="flex gap-2">
              <div className="w-3 h-3 bg-green-500 rounded-full mt-1 shrink-0"></div>
              <div>
                <div className="text-xs font-semibold text-gray-900 mb-0.5">
                  Optimistic Outlier ({optimisticOutlier.year})
                </div>
                <div className="text-xs text-gray-600 mb-0.5">{optimisticOutlier.description}</div>
                <div className="text-xs text-gray-500">{optimisticOutlier.source_percentage}% of sources</div>
              </div>
            </div>

            {/* Pessimistic Outlier */}
            <div className="flex gap-2">
              <div className="w-3 h-3 bg-red-500 rounded-full mt-1 shrink-0"></div>
              <div>
                <div className="text-xs font-semibold text-gray-900 mb-0.5">
                  Pessimistic Outlier ({pessimisticOutlier.year})
                </div>
                <div className="text-xs text-gray-600 mb-0.5">{pessimisticOutlier.description}</div>
                <div className="text-xs text-gray-500">{pessimisticOutlier.source_percentage}% of sources</div>
              </div>
            </div>

            {/* Strategic Implication */}
            <div className="flex gap-2">
              <div className="w-5 h-5 rounded-full bg-white border-2 border-gray-300 flex items-center justify-center shrink-0">
                <Info className="w-3 h-3 text-gray-600" />
              </div>
              <div>
                <div className="text-xs font-semibold text-gray-900 mb-0.5">Strategic Implication</div>
                <div className="text-xs text-gray-600">{strategicImplication}</div>
              </div>
            </div>
          </div>

          {/* Key Supporting Articles */}
          {keyArticles.length > 0 && (
            <div>
              <h6 className="text-sm font-bold text-gray-900 mb-3">Key Supporting Articles</h6>
              <div className="space-y-2">
                {keyArticles.map((article, index) => {
                  const sentimentColor = article.sentiment === 'positive' ? 'bg-green-100 text-green-700' :
                                        article.sentiment === 'critical' ? 'bg-red-100 text-red-700' :
                                        'bg-gray-100 text-gray-700';

                  return (
                    <div key={index} className="p-3 bg-white rounded-lg border border-gray-200" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <a
                          href={article.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm font-semibold text-gray-900 hover:text-blue-600 flex-1"
                        >
                          {article.title}
                        </a>
                        {article.sentiment && (
                          <span className={`px-2 py-0.5 rounded text-xs font-medium shrink-0 ${sentimentColor}`}>
                            {article.sentiment}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-gray-600 mb-1">{article.summary}</p>
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
        </div>
      )}

      {/* Expand/Collapse Indicator */}
      <div className="flex justify-center mt-4">
        {isExpanded ? (
          <ChevronUp className="w-5 h-5 text-gray-400" />
        ) : (
          <ChevronDown className="w-5 h-5 text-gray-400" />
        )}
      </div>
    </div>
  );
}
