/**
 * Policy Category Analysis Tab Component
 * AI-powered insights for individual policy categories
 */

import { useState, useCallback } from 'react';
import { Sparkles, Loader2, RefreshCw, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import {
  generateCategoryInsight,
  type CategoryInsightResponse,
  type PolicyCategory,
  CATEGORY_COLORS,
  CATEGORY_DESCRIPTIONS,
} from '../../services/policyTrackerApi';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  TooltipProvider,
} from '../../components/ui/tooltip';

interface PolicyCategoryAnalysisTabProps {
  categories: PolicyCategory[];
  topic: string;
  daysBack: number;
}

export function PolicyCategoryAnalysisTab({ categories, topic, daysBack }: PolicyCategoryAnalysisTabProps) {
  const [categoryInsights, setCategoryInsights] = useState<Record<string, CategoryInsightResponse>>({});
  const [loadingCategoryInsight, setLoadingCategoryInsight] = useState<string | null>(null);
  const [selectedInsightCategory, setSelectedInsightCategory] = useState<string>('');

  // Generate category insight
  const handleGenerateCategoryInsight = useCallback(
    async (category: string) => {
      setLoadingCategoryInsight(category);
      try {
        const result = await generateCategoryInsight({ category, topic, days_back: daysBack });
        setCategoryInsights((prev) => ({ ...prev, [category]: result }));
      } catch (error) {
        console.error('Failed to generate category insight:', error);
      } finally {
        setLoadingCategoryInsight(null);
      }
    },
    [topic, daysBack]
  );

  // Handle category dropdown selection
  const handleCategorySelect = useCallback((category: string) => {
    setSelectedInsightCategory(category);
  }, []);

  // Get trend icon component
  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case 'up':
        return <TrendingUp className="w-4 h-4 text-green-500" />;
      case 'down':
        return <TrendingDown className="w-4 h-4 text-red-500" />;
      default:
        return <Minus className="w-4 h-4 text-gray-400" />;
    }
  };

  return (
    <TooltipProvider>
      <div className="space-y-6">
        {/* Category Analysis Header */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center gap-2 mb-4">
            <Sparkles className="w-5 h-5 text-violet-500" />
            <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
              Category Analysis
            </h3>
          </div>

          <p className="text-xs text-gray-600 dark:text-gray-400 mb-4">
            Select a policy category to generate AI-powered analysis and insights. Each analysis examines trends,
            key themes, and connections to other policy areas.
          </p>

          {/* Category Dropdown and Generate Button */}
          <div className="space-y-4">
            <div className="flex gap-2">
              <select
                value={selectedInsightCategory}
                onChange={(e) => handleCategorySelect(e.target.value)}
                disabled={loadingCategoryInsight !== null}
                className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-violet-500 focus:border-violet-500 disabled:opacity-50"
              >
                <option value="">Select a category...</option>
                {categories.map((cat) => (
                  <option key={cat.category} value={cat.category}>
                    {cat.category} ({cat.article_count} articles, {cat.percentage}%)
                  </option>
                ))}
              </select>
              {selectedInsightCategory && (
                <button
                  onClick={() => handleGenerateCategoryInsight(selectedInsightCategory)}
                  disabled={loadingCategoryInsight === selectedInsightCategory}
                  className="flex items-center gap-2 px-4 py-2 text-sm bg-violet-500 text-white rounded-lg hover:bg-violet-600 disabled:opacity-50 transition-colors"
                >
                  {loadingCategoryInsight === selectedInsightCategory ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Generating...
                    </>
                  ) : categoryInsights[selectedInsightCategory] ? (
                    <>
                      <RefreshCw className="w-4 h-4" />
                      Regenerate
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4" />
                      Generate
                    </>
                  )}
                </button>
              )}
            </div>

            {/* Loading state */}
            {loadingCategoryInsight && (
              <div className="flex items-center gap-2 p-4 bg-violet-50 dark:bg-violet-900/20 rounded-lg">
                <Loader2 className="w-4 h-4 animate-spin text-violet-500" />
                <span className="text-sm text-violet-700 dark:text-violet-300">
                  Generating insight for {loadingCategoryInsight}...
                </span>
              </div>
            )}

            {/* Selected category insight display */}
            {selectedInsightCategory && categoryInsights[selectedInsightCategory] && !loadingCategoryInsight && (
              <div className="p-5 bg-gradient-to-br from-gray-50 to-violet-50/30 dark:from-gray-800 dark:to-violet-900/10 rounded-xl shadow-inner border border-gray-100 dark:border-gray-700">
                <div className="flex items-center gap-3 mb-4">
                  <span
                    className="w-4 h-4 rounded-full flex-shrink-0"
                    style={{ backgroundColor: CATEGORY_COLORS[selectedInsightCategory] || '#6B7280' }}
                  />
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <h4 className="text-base font-semibold text-gray-900 dark:text-gray-100 cursor-help">
                        {selectedInsightCategory}
                      </h4>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p className="max-w-xs">{CATEGORY_DESCRIPTIONS[selectedInsightCategory] || selectedInsightCategory}</p>
                    </TooltipContent>
                  </Tooltip>
                  <div className="flex items-center gap-1.5">
                    {getTrendIcon(categoryInsights[selectedInsightCategory].trend)}
                    <span
                      className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                        categoryInsights[selectedInsightCategory].trend === 'up'
                          ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                          : categoryInsights[selectedInsightCategory].trend === 'down'
                          ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                          : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
                      }`}
                    >
                      {categoryInsights[selectedInsightCategory].trend === 'up'
                        ? 'Trending Up'
                        : categoryInsights[selectedInsightCategory].trend === 'down'
                        ? 'Trending Down'
                        : 'Stable'}
                    </span>
                  </div>
                </div>
                <div className="prose prose-sm dark:prose-invert max-w-none">
                  <p className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap leading-7">
                    {categoryInsights[selectedInsightCategory].insight}
                  </p>
                </div>
              </div>
            )}

            {/* Hint when no category selected */}
            {!selectedInsightCategory && !loadingCategoryInsight && (
              <div className="p-6 bg-gray-50 dark:bg-gray-750 rounded-lg border border-dashed border-gray-300 dark:border-gray-600 text-center">
                <Sparkles className="w-8 h-8 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Select a category from the dropdown above to generate insights
                </p>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
                  Analysis includes trend data, key themes, and cross-category connections
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Category Quick Stats Grid */}
        {categories.length > 0 && (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
            <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-4">
              Category Distribution
            </h4>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
              {categories.slice(0, 10).map((cat) => (
                <button
                  key={cat.category}
                  onClick={() => {
                    setSelectedInsightCategory(cat.category);
                    // Scroll to top of component
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                  }}
                  className={`p-3 rounded-lg border transition-all hover:shadow-md ${
                    selectedInsightCategory === cat.category
                      ? 'border-violet-400 dark:border-violet-500 bg-violet-50 dark:bg-violet-900/20'
                      : 'border-gray-200 dark:border-gray-700 hover:border-violet-300 dark:hover:border-violet-600'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                      style={{ backgroundColor: CATEGORY_COLORS[cat.category] || '#6B7280' }}
                    />
                    <span className="text-xs font-medium text-gray-700 dark:text-gray-300 truncate">
                      {cat.category}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                      {cat.article_count}
                    </span>
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {cat.percentage}%
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </TooltipProvider>
  );
}
