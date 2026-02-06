/**
 * ScienceWatch Analysis Tab
 * Deep analysis: co-occurrence heatmap, category breakdown
 */

import { useState, useEffect } from 'react';
import { Loader2 } from 'lucide-react';
import type {
  CooccurrenceMatrix,
  Cooccurrence,
  ScienceCategory,
} from '../../services/scienceFundingApi';
import { CATEGORY_COLORS, CATEGORY_SHORT_NAMES, getCooccurrence } from '../../services/scienceFundingApi';

interface ScienceAnalysisTabProps {
  cooccurrenceMatrix: CooccurrenceMatrix | null;
  categories: ScienceCategory[];
  loading: boolean;
  onLoad: () => void;
  topic: string;
  daysBack: number;
}

type AnalysisView = 'heatmap' | 'pairs' | 'breakdown';

export function ScienceAnalysisTab({
  cooccurrenceMatrix,
  categories,
  loading,
  onLoad,
  topic,
  daysBack,
}: ScienceAnalysisTabProps) {
  const [activeView, setActiveView] = useState<AnalysisView>('heatmap');
  const [cooccurrencePairs, setCooccurrencePairs] = useState<Cooccurrence[]>([]);
  const [loadingPairs, setLoadingPairs] = useState(false);

  // Load matrix on mount
  useEffect(() => {
    if (!cooccurrenceMatrix) {
      onLoad();
    }
  }, []);

  // Load pairs when that view is selected
  useEffect(() => {
    if (activeView === 'pairs' && cooccurrencePairs.length === 0) {
      setLoadingPairs(true);
      getCooccurrence(topic, daysBack, 20)
        .then(setCooccurrencePairs)
        .catch(console.error)
        .finally(() => setLoadingPairs(false));
    }
  }, [activeView, topic, daysBack]);

  // Find max value for heatmap color scaling
  const maxValue = cooccurrenceMatrix
    ? Math.max(...cooccurrenceMatrix.matrix.flat().filter((_, i) => i % (cooccurrenceMatrix.categories.length + 1) !== 0))
    : 0;

  // Get color for heatmap cell
  const getHeatmapColor = (value: number, isDiagonal: boolean) => {
    if (isDiagonal) {
      // Diagonal cells (self-count) - use emerald
      const intensity = Math.min(value / (maxValue * 1.5), 1);
      return `rgba(16, 185, 129, ${0.2 + intensity * 0.6})`;
    }
    // Off-diagonal (co-occurrence) - use teal
    const intensity = maxValue > 0 ? value / maxValue : 0;
    return `rgba(13, 148, 136, ${0.1 + intensity * 0.7})`;
  };

  return (
    <div className="space-y-6">
      {/* View Selector */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
            Category Analysis
          </h3>
          <div className="flex gap-1 bg-gray-100 dark:bg-gray-700 rounded-lg p-0.5">
            <button
              onClick={() => setActiveView('heatmap')}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                activeView === 'heatmap'
                  ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm'
                  : 'text-gray-600 dark:text-gray-300'
              }`}
            >
              Heatmap
            </button>
            <button
              onClick={() => setActiveView('pairs')}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                activeView === 'pairs'
                  ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm'
                  : 'text-gray-600 dark:text-gray-300'
              }`}
            >
              Top Pairs
            </button>
            <button
              onClick={() => setActiveView('breakdown')}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                activeView === 'breakdown'
                  ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm'
                  : 'text-gray-600 dark:text-gray-300'
              }`}
            >
              Breakdown
            </button>
          </div>
        </div>

        {/* Co-occurrence Heatmap */}
        {activeView === 'heatmap' && (
          <div>
            <p className="text-xs text-gray-500 dark:text-gray-300 mb-4">
              Category co-occurrence matrix (diagonal shows category count, off-diagonal shows co-occurrence)
            </p>
            {loading && !cooccurrenceMatrix ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-6 h-6 animate-spin text-emerald-500" />
                <span className="ml-2 text-gray-500 dark:text-gray-300">Loading heatmap...</span>
              </div>
            ) : cooccurrenceMatrix ? (
              <div className="overflow-x-auto">
                <div className="min-w-[700px]">
                  {/* Column headers */}
                  <div className="flex ml-[120px] mb-1">
                    {cooccurrenceMatrix.categories.map((cat, i) => (
                      <div
                        key={`header-${i}`}
                        className="w-[60px] text-[9px] text-gray-600 dark:text-gray-300 transform -rotate-45 origin-left whitespace-nowrap h-[60px] flex items-end"
                        title={cat}
                      >
                        {CATEGORY_SHORT_NAMES[cat] || cat.slice(0, 12)}
                      </div>
                    ))}
                  </div>
                  {/* Rows */}
                  {cooccurrenceMatrix.matrix.map((row, i) => (
                    <div key={`row-${i}`} className="flex items-center">
                      {/* Row label */}
                      <div
                        className="w-[120px] text-[10px] text-gray-600 dark:text-gray-300 text-right pr-2 truncate"
                        title={cooccurrenceMatrix.categories[i]}
                      >
                        {CATEGORY_SHORT_NAMES[cooccurrenceMatrix.categories[i]] || cooccurrenceMatrix.categories[i]}
                      </div>
                      {/* Cells */}
                      {row.map((value, j) => (
                        <div
                          key={`cell-${i}-${j}`}
                          className="w-[60px] h-[36px] flex items-center justify-center text-[10px] font-medium border border-gray-200 dark:border-gray-700"
                          style={{
                            backgroundColor: getHeatmapColor(value, i === j),
                            color: value > maxValue * 0.5 ? '#fff' : '#374151',
                          }}
                          title={`${cooccurrenceMatrix.categories[i]} + ${cooccurrenceMatrix.categories[j]}: ${value}`}
                        >
                          {value > 0 ? value : ''}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
                {/* Legend */}
                <div className="flex items-center gap-4 mt-4 text-xs text-gray-500 dark:text-gray-300">
                  <div className="flex items-center gap-1">
                    <div className="w-4 h-4 rounded" style={{ backgroundColor: 'rgba(16, 185, 129, 0.6)' }} />
                    <span>Category count (diagonal)</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="w-4 h-4 rounded" style={{ backgroundColor: 'rgba(13, 148, 136, 0.6)' }} />
                    <span>Co-occurrence (off-diagonal)</span>
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-center py-8 text-gray-500 dark:text-gray-300">No data available</p>
            )}
          </div>
        )}

        {/* Top Co-occurrence Pairs */}
        {activeView === 'pairs' && (
          <div>
            <p className="text-xs text-gray-500 dark:text-gray-300 mb-4">
              Top category pairs that frequently appear together
            </p>
            {loadingPairs ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-6 h-6 animate-spin text-emerald-500" />
                <span className="ml-2 text-gray-500 dark:text-gray-300">Loading pairs...</span>
              </div>
            ) : cooccurrencePairs.length > 0 ? (
              <div className="space-y-2">
                {cooccurrencePairs.map((pair, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-750 rounded-lg"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-500 w-6">{i + 1}.</span>
                      <div className="flex items-center gap-1">
                        <span
                          className="w-2 h-2 rounded-full"
                          style={{ backgroundColor: CATEGORY_COLORS[pair.category1] || '#6B7280' }}
                        />
                        <span className="text-sm text-gray-700 dark:text-gray-300">
                          {CATEGORY_SHORT_NAMES[pair.category1] || pair.category1}
                        </span>
                      </div>
                      <span className="text-gray-500">+</span>
                      <div className="flex items-center gap-1">
                        <span
                          className="w-2 h-2 rounded-full"
                          style={{ backgroundColor: CATEGORY_COLORS[pair.category2] || '#6B7280' }}
                        />
                        <span className="text-sm text-gray-700 dark:text-gray-300">
                          {CATEGORY_SHORT_NAMES[pair.category2] || pair.category2}
                        </span>
                      </div>
                    </div>
                    <div className="text-right">
                      <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {pair.count}
                      </span>
                      <span className="text-xs text-gray-500 ml-2">({pair.percentage}%)</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-center py-8 text-gray-500 dark:text-gray-300">No pairs data available</p>
            )}
          </div>
        )}

        {/* Category Breakdown */}
        {activeView === 'breakdown' && (
          <div>
            <p className="text-xs text-gray-500 dark:text-gray-300 mb-4">
              Detailed category distribution with trends
            </p>
            <div className="space-y-3">
              {categories.map((cat) => (
                <div
                  key={cat.category}
                  className="p-3 bg-gray-50 dark:bg-gray-750 rounded-lg"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: CATEGORY_COLORS[cat.category] || '#6B7280' }}
                      />
                      <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {cat.category}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                        {cat.article_count}
                      </span>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${
                        cat.recent_trend === 'up'
                          ? 'bg-green-100 text-green-700 dark:bg-green-900/20 dark:text-green-400'
                          : cat.recent_trend === 'down'
                          ? 'bg-red-100 text-red-700 dark:bg-red-900/20 dark:text-red-400'
                          : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
                      }`}>
                        {cat.recent_trend === 'up' ? '\u2191' : cat.recent_trend === 'down' ? '\u2193' : '\u2192'}
                      </span>
                    </div>
                  </div>
                  {/* Progress bar */}
                  <div className="h-2 bg-gray-200 dark:bg-gray-600 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${cat.percentage}%`,
                        backgroundColor: CATEGORY_COLORS[cat.category] || '#6B7280',
                      }}
                    />
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-300 mt-1">
                    {cat.percentage}% of total articles
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
