/**
 * GeopoliticalAnalysisTab Component
 * Advanced analysis with co-occurrence heatmap and theme evolution charts
 */

import { useState, useEffect, useMemo } from 'react';
import { BarChart2, Grid3X3, TrendingUp, Users, List, ArrowUpRight, ArrowDownRight, ArrowRight } from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import {
  getCategoryCooccurrence,
  getCategoriesData,
  getDailyCounts,
  type CategoryCooccurrence,
  type CategoryData,
  type DailyCount,
} from '../../services/geopoliticalHotspotsApi';

type AnalysisView = 'heatmap' | 'pairs' | 'breakdown';

interface GeopoliticalAnalysisTabProps {
  onCategoryFilter?: (category: string) => void;
}

// Category colors for visualization
const CATEGORY_COLORS: Record<string, string> = {
  conflict: '#DC2626',
  protest: '#F97316',
  disaster: '#EAB308',
  diplomatic: '#3B82F6',
  economic: '#8B5CF6',
  terrorism: '#EF4444',
  cyber: '#06B6D4',
  health: '#22C55E',
  environmental: '#10B981',
  military: '#DC2626',
  crime: '#F43F5E',
  piracy: '#0EA5E9',
  infrastructure: '#6366F1',
  commodities: '#A855F7',
};

export function GeopoliticalAnalysisTab({ onCategoryFilter }: GeopoliticalAnalysisTabProps) {
  const [activeView, setActiveView] = useState<AnalysisView>('heatmap');
  const [cooccurrence, setCooccurrence] = useState<CategoryCooccurrence | null>(null);
  const [categories, setCategories] = useState<CategoryData[]>([]);
  const [dailyCounts, setDailyCounts] = useState<DailyCount[]>([]);
  const [loadingCooccurrence, setLoadingCooccurrence] = useState(true);
  const [loadingCategories, setLoadingCategories] = useState(true);
  const [loadingDailyCounts, setLoadingDailyCounts] = useState(true);
  const [selectedCell, setSelectedCell] = useState<{ cat1: string; cat2: string } | null>(null);

  useEffect(() => {
    fetchCooccurrence();
    fetchCategories();
    fetchDailyCounts();
  }, []);

  const fetchCooccurrence = async () => {
    setLoadingCooccurrence(true);
    try {
      const data = await getCategoryCooccurrence();
      setCooccurrence(data);
    } catch (err) {
      console.error('Error fetching co-occurrence:', err);
    } finally {
      setLoadingCooccurrence(false);
    }
  };

  const fetchCategories = async () => {
    setLoadingCategories(true);
    try {
      const data = await getCategoriesData();
      setCategories(data);
    } catch (err) {
      console.error('Error fetching categories:', err);
    } finally {
      setLoadingCategories(false);
    }
  };

  const fetchDailyCounts = async () => {
    setLoadingDailyCounts(true);
    try {
      const data = await getDailyCounts(undefined, 60);
      setDailyCounts(data);
    } catch (err) {
      console.error('Error fetching daily counts:', err);
    } finally {
      setLoadingDailyCounts(false);
    }
  };

  const loading = loadingCooccurrence || loadingCategories || loadingDailyCounts;

  // Calculate max value for heatmap scaling
  const maxCooccurrence = useMemo(() => {
    if (!cooccurrence || cooccurrence.pairs.length === 0) return 1;
    return Math.max(...cooccurrence.pairs.map((p) => p.count));
  }, [cooccurrence]);

  // Get color intensity based on value
  const getHeatColor = (value: number) => {
    const intensity = Math.min(value / maxCooccurrence, 1);
    // From light pink to deep pink
    const r = 236;
    const g = Math.round(72 + (1 - intensity) * 180);
    const b = Math.round(153 + (1 - intensity) * 100);
    return `rgb(${r}, ${g}, ${b})`;
  };

  // Prepare category intensity data for bar chart
  const intensityData = useMemo(() => {
    return categories
      .filter((c) => c.count > 0)
      .sort((a, b) => b.avg_intensity - a.avg_intensity)
      .slice(0, 10)
      .map((c) => ({
        category: c.category.charAt(0).toUpperCase() + c.category.slice(1),
        intensity: c.avg_intensity,
        count: c.count,
        articles: c.total_articles,
      }));
  }, [categories]);

  // Prepare data for top pairs
  const topPairs = useMemo(() => {
    if (!cooccurrence) return [];
    return cooccurrence.pairs.slice(0, 10).map((p, i) => ({
      rank: i + 1,
      category1: p.category1.charAt(0).toUpperCase() + p.category1.slice(1),
      category2: p.category2.charAt(0).toUpperCase() + p.category2.slice(1),
      count: p.count,
      percentage: ((p.count / maxCooccurrence) * 100).toFixed(0),
    }));
  }, [cooccurrence, maxCooccurrence]);

  // Prepare data for breakdown view with trend indicators
  const breakdownData = useMemo(() => {
    const totalCount = categories.reduce((sum, c) => sum + c.count, 0);
    const totalArticles = categories.reduce((sum, c) => sum + c.total_articles, 0);

    // Calculate simple trend based on intensity (higher intensity = escalating)
    return categories
      .filter((c) => c.count > 0)
      .sort((a, b) => b.count - a.count)
      .map((c) => {
        // Determine trend based on intensity score
        let trend: 'up' | 'down' | 'stable' = 'stable';
        if (c.avg_intensity >= 60) trend = 'up';
        else if (c.avg_intensity <= 30) trend = 'down';

        return {
          category: c.category,
          count: c.count,
          percentage: totalCount > 0 ? (c.count / totalCount) * 100 : 0,
          articles: c.total_articles,
          articlesPercentage: totalArticles > 0 ? (c.total_articles / totalArticles) * 100 : 0,
          avgIntensity: c.avg_intensity,
          trend,
        };
      });
  }, [categories]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-pulse text-gray-500 dark:text-gray-400">Loading analysis...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          icon={<BarChart2 className="w-5 h-5" />}
          label="Categories"
          value={categories.filter((c) => c.count > 0).length.toString()}
          color="text-pink-500"
        />
        <StatCard
          icon={<Grid3X3 className="w-5 h-5" />}
          label="Co-occurrence Pairs"
          value={cooccurrence?.pairs.length.toString() || '0'}
          color="text-blue-500"
        />
        <StatCard
          icon={<TrendingUp className="w-5 h-5" />}
          label="Avg Intensity"
          value={`${(categories.reduce((sum, c) => sum + c.avg_intensity * c.count, 0) / Math.max(categories.reduce((sum, c) => sum + c.count, 0), 1)).toFixed(1)}%`}
          color="text-orange-500"
        />
        <StatCard
          icon={<Users className="w-5 h-5" />}
          label="Total Hotspots"
          value={categories.reduce((sum, c) => sum + c.count, 0).toString()}
          color="text-emerald-500"
        />
      </div>

      {/* View Selector */}
      <div className="flex gap-1 bg-gray-100 dark:bg-gray-700 rounded-lg p-0.5 w-fit">
        <button
          onClick={() => setActiveView('heatmap')}
          className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
            activeView === 'heatmap'
              ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 shadow-sm'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
          }`}
        >
          <Grid3X3 className="w-4 h-4 inline-block mr-1.5 -mt-0.5" />
          Heatmap
        </button>
        <button
          onClick={() => setActiveView('pairs')}
          className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
            activeView === 'pairs'
              ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 shadow-sm'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
          }`}
        >
          <BarChart2 className="w-4 h-4 inline-block mr-1.5 -mt-0.5" />
          Top Pairs
        </button>
        <button
          onClick={() => setActiveView('breakdown')}
          className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
            activeView === 'breakdown'
              ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 shadow-sm'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
          }`}
        >
          <List className="w-4 h-4 inline-block mr-1.5 -mt-0.5" />
          Breakdown
        </button>
      </div>

      {/* Breakdown View */}
      {activeView === 'breakdown' && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
          <div className="p-4 border-b border-gray-200 dark:border-gray-700">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100">
              Category Breakdown
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              All threat categories with trend indicators. Click to filter articles.
            </p>
          </div>
          <div className="divide-y divide-gray-200 dark:divide-gray-700">
            {breakdownData.map((item) => (
              <button
                key={item.category}
                onClick={() => onCategoryFilter?.(item.category)}
                className="w-full p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors text-left"
              >
                <div className="flex items-center gap-4">
                  {/* Category color indicator */}
                  <div
                    className="w-3 h-3 rounded-full flex-shrink-0"
                    style={{ backgroundColor: CATEGORY_COLORS[item.category] || '#6B7280' }}
                  />

                  {/* Category name and trend */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900 dark:text-gray-100 capitalize">
                        {item.category}
                      </span>
                      {item.trend === 'up' && (
                        <span className="flex items-center text-red-500 text-xs">
                          <ArrowUpRight className="w-3 h-3" />
                        </span>
                      )}
                      {item.trend === 'down' && (
                        <span className="flex items-center text-green-500 text-xs">
                          <ArrowDownRight className="w-3 h-3" />
                        </span>
                      )}
                      {item.trend === 'stable' && (
                        <span className="flex items-center text-gray-400 text-xs">
                          <ArrowRight className="w-3 h-3" />
                        </span>
                      )}
                    </div>
                    {/* Progress bar */}
                    <div className="mt-2 w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                      <div
                        className="h-1.5 rounded-full transition-all"
                        style={{
                          width: `${item.percentage}%`,
                          backgroundColor: CATEGORY_COLORS[item.category] || '#6B7280',
                        }}
                      />
                    </div>
                  </div>

                  {/* Stats */}
                  <div className="text-right flex-shrink-0">
                    <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      {item.count} hotspots
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      {item.percentage.toFixed(1)}%
                    </div>
                  </div>

                  <div className="text-right flex-shrink-0 w-20">
                    <div className="text-sm text-gray-700 dark:text-gray-300">
                      {item.articles} articles
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      {item.avgIntensity.toFixed(0)}% intensity
                    </div>
                  </div>
                </div>
              </button>
            ))}
            {breakdownData.length === 0 && (
              <div className="p-6 text-center text-gray-500 dark:text-gray-400">
                No categories found
              </div>
            )}
          </div>
        </div>
      )}

      {/* Co-occurrence Heatmap */}
      {activeView === 'heatmap' && cooccurrence && cooccurrence.categories.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
            Category Co-occurrence Heatmap
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
            Shows how often threat categories appear together in related articles. Darker = more frequent.
          </p>
          <div className="overflow-x-auto">
            <div className="inline-block min-w-full">
              {/* Header row */}
              <div className="flex">
                <div className="w-24 h-8 flex-shrink-0" />
                {cooccurrence.categories.slice(0, 10).map((cat) => (
                  <div
                    key={cat}
                    className="w-20 h-8 flex items-center justify-center text-xs text-gray-600 dark:text-gray-400 font-medium"
                    style={{ writingMode: 'vertical-lr', transform: 'rotate(180deg)' }}
                  >
                    {cat.charAt(0).toUpperCase() + cat.slice(1).substring(0, 6)}
                  </div>
                ))}
              </div>
              {/* Grid rows */}
              {cooccurrence.categories.slice(0, 10).map((rowCat) => (
                <div key={rowCat} className="flex">
                  <div className="w-24 h-10 flex items-center text-xs text-gray-600 dark:text-gray-400 font-medium pr-2">
                    {rowCat.charAt(0).toUpperCase() + rowCat.slice(1)}
                  </div>
                  {cooccurrence.categories.slice(0, 10).map((colCat) => {
                    const value = cooccurrence.matrix[rowCat]?.[colCat] || 0;
                    const isSelected = selectedCell?.cat1 === rowCat && selectedCell?.cat2 === colCat;
                    return (
                      <div
                        key={colCat}
                        className={`w-20 h-10 flex items-center justify-center text-xs cursor-pointer transition-all ${
                          isSelected ? 'ring-2 ring-pink-500' : ''
                        }`}
                        style={{
                          backgroundColor: value > 0 ? getHeatColor(value) : 'transparent',
                          color: value > maxCooccurrence * 0.5 ? 'white' : 'inherit',
                        }}
                        onClick={() => {
                          if (value > 0) {
                            setSelectedCell({ cat1: rowCat, cat2: colCat });
                          }
                        }}
                        title={`${rowCat} + ${colCat}: ${value} co-occurrences`}
                      >
                        {value > 0 ? value : '-'}
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
          {/* Legend */}
          <div className="flex items-center justify-end gap-2 mt-4 text-xs text-gray-500 dark:text-gray-400">
            <span>Less</span>
            <div className="flex">
              {[0.2, 0.4, 0.6, 0.8, 1].map((intensity) => (
                <div
                  key={intensity}
                  className="w-6 h-4"
                  style={{ backgroundColor: getHeatColor(maxCooccurrence * intensity) }}
                />
              ))}
            </div>
            <span>More</span>
          </div>
        </div>
      )}

      {/* Category Intensity Chart - Heatmap View */}
      {activeView === 'heatmap' && intensityData.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
            Category by Average Intensity
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
            Categories ranked by their average threat intensity score
          </p>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={intensityData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 12 }} />
              <YAxis
                type="category"
                dataKey="category"
                tick={{ fontSize: 11 }}
                width={100}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'rgba(31, 41, 55, 0.95)',
                  border: 'none',
                  borderRadius: '0.5rem',
                  color: '#F9FAFB',
                }}
                formatter={(value: number, name: string, props: any) => {
                  if (name === 'intensity') {
                    return [
                      <span key="intensity">
                        {value.toFixed(1)}% intensity
                        <br />
                        {props.payload.count} hotspots • {props.payload.articles} articles
                      </span>,
                      '',
                    ];
                  }
                  return [value, name];
                }}
              />
              <Bar dataKey="intensity" radius={[0, 4, 4, 0]} cursor="pointer">
                {intensityData.map((entry, index) => {
                  const intensity = entry.intensity / 100;
                  const color =
                    intensity >= 0.7
                      ? '#DC2626'
                      : intensity >= 0.5
                        ? '#F97316'
                        : intensity >= 0.3
                          ? '#EAB308'
                          : '#22C55E';
                  return <Cell key={`cell-${index}`} fill={color} />;
                })}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Top Co-occurrence Pairs */}
      {activeView === 'pairs' && topPairs.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">
            Top Category Pairs
          </h3>
          <div className="space-y-2">
            {topPairs.map((pair) => (
              <div
                key={`${pair.category1}-${pair.category2}`}
                className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
              >
                <span className="text-sm font-bold text-gray-400 w-6">{pair.rank}</span>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 text-xs bg-pink-100 dark:bg-pink-900/30 text-pink-700 dark:text-pink-300 rounded">
                      {pair.category1}
                    </span>
                    <span className="text-gray-400">+</span>
                    <span className="px-2 py-0.5 text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded">
                      {pair.category2}
                    </span>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                    {pair.count}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">co-occurrences</div>
                </div>
                <div
                  className="w-16 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden"
                >
                  <div
                    className="h-full bg-gradient-to-r from-pink-500 to-purple-500 rounded-full"
                    style={{ width: `${pair.percentage}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Category Distribution by Articles - Pairs View */}
      {activeView === 'pairs' && categories.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
            Category Distribution by Article Count
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
            Total articles per threat category
          </p>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart
              data={categories
                .filter((c) => c.total_articles > 0)
                .sort((a, b) => b.total_articles - a.total_articles)
                .slice(0, 10)
                .map((c) => ({
                  category: c.category.charAt(0).toUpperCase() + c.category.slice(1),
                  articles: c.total_articles,
                  hotspots: c.count,
                }))}
              layout="vertical"
            >
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis type="number" tick={{ fontSize: 12 }} />
              <YAxis
                type="category"
                dataKey="category"
                tick={{ fontSize: 11 }}
                width={100}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'rgba(31, 41, 55, 0.95)',
                  border: 'none',
                  borderRadius: '0.5rem',
                  color: '#F9FAFB',
                }}
                formatter={(value: number, name: string, props: any) => [
                  `${value} ${name} (${props.payload.hotspots} hotspots)`,
                  '',
                ]}
              />
              <Bar
                dataKey="articles"
                name="articles"
                fill="#EC4899"
                radius={[0, 4, 4, 0]}
                cursor="pointer"
                onClick={(data) => {
                  if (onCategoryFilter) {
                    onCategoryFilter(data.category.toLowerCase());
                  }
                }}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Empty state if no data */}
      {(!cooccurrence || cooccurrence.pairs.length === 0) && categories.length === 0 && (
        <div className="flex flex-col items-center justify-center h-64 text-center">
          <Grid3X3 className="w-12 h-12 text-gray-400 dark:text-gray-600 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
            No Analysis Data Available
          </h3>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Process some articles to see category analysis and co-occurrence patterns
          </p>
        </div>
      )}
    </div>
  );
}

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  color: string;
}

function StatCard({ icon, label, value, color }: StatCardProps) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <div className={`${color} mb-2`}>{icon}</div>
      <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{value}</div>
      <div className="text-sm text-gray-600 dark:text-gray-400">{label}</div>
    </div>
  );
}
