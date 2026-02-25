/**
 * ThreatCategoriesTab Component
 * Category distribution and breakdown
 */

import { useState, useEffect } from 'react';
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
} from 'recharts';
import { Shield, ChevronRight } from 'lucide-react';
import {
  getCategoryTrends,
  type ThreatCategory,
  type CategoryData,
  THREAT_CATEGORY_LABELS,
  SEVERITY_COLORS,
} from '../../services/threatIntelligenceApi';

interface ThreatCategoriesTabProps {
  categories: CategoryData[];
  loading: boolean;
  onLoad: () => void;
  onCategoryFilter: (category: string) => void;
}

const CATEGORY_COLORS: Record<string, string> = {
  malware: '#DC2626',
  ransomware: '#F97316',
  apt: '#EF4444',
  phishing: '#F59E0B',
  vulnerability: '#EAB308',
  data_breach: '#84CC16',
  botnet: '#22C55E',
  ddos: '#10B981',
  supply_chain: '#14B8A6',
  credential_theft: '#06B6D4',
  cryptojacking: '#0EA5E9',
  insider_threat: '#3B82F6',
  iot_ot: '#6366F1',
  mobile: '#8B5CF6',
};

export function ThreatCategoriesTab({ categories, loading, onLoad, onCategoryFilter }: ThreatCategoriesTabProps) {
  const [selectedCategory, setSelectedCategory] = useState<ThreatCategory | null>(null);
  const [trendData, setTrendData] = useState<any[]>([]);
  const [loadingTrends, setLoadingTrends] = useState(false);

  // Load categories on mount
  useEffect(() => {
    if (categories.length === 0 && !loading) {
      onLoad();
    }
  }, [categories.length, loading, onLoad]);

  // Sort categories by count
  const sortedCategories = [...(categories || [])].sort((a, b) => b.count - a.count);

  useEffect(() => {
    const fetchTrends = async () => {
      if (!selectedCategory) return;

      setLoadingTrends(true);
      try {
        const result = await getCategoryTrends(selectedCategory, 30);
        setTrendData(result);
      } catch (error) {
        console.error('Error fetching category trends:', error);
      } finally {
        setLoadingTrends(false);
      }
    };

    fetchTrends();
  }, [selectedCategory]);

  const pieData = sortedCategories.map((cat) => ({
    name: THREAT_CATEGORY_LABELS[cat.category as ThreatCategory] || cat.category,
    value: cat.count,
    category: cat.category,
  }));

  const getSeverityColor = (score: number) => {
    if (score >= 80) return SEVERITY_COLORS.critical;
    if (score >= 60) return SEVERITY_COLORS.high;
    if (score >= 40) return SEVERITY_COLORS.medium;
    if (score >= 20) return SEVERITY_COLORS.low;
    return SEVERITY_COLORS.info;
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  if (loading && sortedCategories.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-red-500"></div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Distribution Chart */}
      <div className="lg:col-span-1 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Threat Type Distribution
        </h3>
        <div className="h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={100}
                paddingAngle={2}
                dataKey="value"
                onClick={(data) => setSelectedCategory(data.category)}
              >
                {pieData.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={CATEGORY_COLORS[entry.category] || '#6B7280'}
                    stroke={selectedCategory === entry.category ? '#fff' : 'transparent'}
                    strokeWidth={selectedCategory === entry.category ? 3 : 0}
                    style={{ cursor: 'pointer' }}
                  />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1F2937',
                  border: 'none',
                  borderRadius: '0.5rem',
                  color: '#F9FAFB',
                }}
                formatter={(value: number, name: string) => [value, name]}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-4 max-h-[200px] overflow-y-auto space-y-1">
          {pieData.slice(0, 8).map((item) => (
            <button
              key={item.category}
              onClick={() => setSelectedCategory(item.category)}
              className={`w-full flex items-center justify-between px-2 py-1.5 rounded text-sm transition-colors ${
                selectedCategory === item.category
                  ? 'bg-red-50 dark:bg-red-900/20'
                  : 'hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
            >
              <div className="flex items-center gap-2">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: CATEGORY_COLORS[item.category] || '#6B7280' }}
                />
                <span className="text-gray-700 dark:text-gray-300 truncate">{item.name}</span>
              </div>
              <span className="text-gray-500 dark:text-gray-400 font-medium">{item.value}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Category List */}
      <div className="lg:col-span-1 space-y-3">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Categories by Volume
        </h3>
        <div className="space-y-2 max-h-[600px] overflow-y-auto">
          {sortedCategories.map((cat) => (
            <button
              key={cat.category}
              onClick={() => setSelectedCategory(cat.category as ThreatCategory)}
              className={`w-full text-left p-3 rounded-lg border transition-all ${
                selectedCategory === cat.category
                  ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
                  : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-red-300 dark:hover:border-red-700'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div
                    className="w-10 h-10 rounded-lg flex items-center justify-center"
                    style={{ backgroundColor: `${CATEGORY_COLORS[cat.category] || '#6B7280'}20` }}
                  >
                    <Shield
                      className="w-5 h-5"
                      style={{ color: CATEGORY_COLORS[cat.category] || '#6B7280' }}
                    />
                  </div>
                  <div>
                    <div className="font-medium text-gray-900 dark:text-gray-100">
                      {THREAT_CATEGORY_LABELS[cat.category as ThreatCategory] || cat.category}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      {cat.count} threats · {cat.total_articles} articles
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <div
                      className="text-sm font-medium"
                      style={{ color: getSeverityColor(cat.avg_severity) }}
                    >
                      {cat.avg_severity.toFixed(0)}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">avg severity</div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-gray-400" />
                </div>
              </div>

              {/* Mini severity bar */}
              <div className="mt-2 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${cat.avg_severity}%`,
                    backgroundColor: getSeverityColor(cat.avg_severity),
                  }}
                />
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Category Details */}
      <div className="lg:col-span-1">
        {selectedCategory ? (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sticky top-4">
            <div className="flex items-center gap-3 mb-4">
              <div
                className="w-12 h-12 rounded-lg flex items-center justify-center"
                style={{ backgroundColor: `${CATEGORY_COLORS[selectedCategory] || '#6B7280'}20` }}
              >
                <Shield
                  className="w-6 h-6"
                  style={{ color: CATEGORY_COLORS[selectedCategory] || '#6B7280' }}
                />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  {THREAT_CATEGORY_LABELS[selectedCategory] || selectedCategory}
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {sortedCategories.find((s) => s.category === selectedCategory)?.count || 0} threats
                </p>
              </div>
            </div>

            {/* Stats Cards */}
            {(() => {
              const categoryData = sortedCategories.find((s) => s.category === selectedCategory);
              if (!categoryData) return null;
              return (
                <div className="grid grid-cols-2 gap-3 mb-4">
                  {/* Average Severity */}
                  <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
                    <div className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">
                      Avg Severity
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className="text-2xl font-bold"
                        style={{ color: getSeverityColor(categoryData.avg_severity) }}
                      >
                        {categoryData.avg_severity.toFixed(0)}
                      </span>
                      <span
                        className="px-1.5 py-0.5 text-xs font-medium rounded text-white"
                        style={{ backgroundColor: getSeverityColor(categoryData.avg_severity) }}
                      >
                        {categoryData.avg_severity >= 80
                          ? 'CRITICAL'
                          : categoryData.avg_severity >= 60
                          ? 'HIGH'
                          : categoryData.avg_severity >= 40
                          ? 'MEDIUM'
                          : categoryData.avg_severity >= 20
                          ? 'LOW'
                          : 'INFO'}
                      </span>
                    </div>
                  </div>

                  {/* Total Articles */}
                  <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
                    <div className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">
                      Total Articles
                    </div>
                    <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                      {categoryData.total_articles?.toLocaleString() || 0}
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* Severity Distribution Bar */}
            {(() => {
              const categoryData = sortedCategories.find((s) => s.category === selectedCategory);
              if (!categoryData) return null;
              const avgSev = categoryData.avg_severity;
              return (
                <div className="mb-4">
                  <div className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">
                    Severity Scale
                  </div>
                  <div className="relative h-3 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                    {/* Gradient background */}
                    <div
                      className="absolute inset-0"
                      style={{
                        background: `linear-gradient(to right,
                          ${SEVERITY_COLORS.info} 0%,
                          ${SEVERITY_COLORS.low} 20%,
                          ${SEVERITY_COLORS.medium} 40%,
                          ${SEVERITY_COLORS.high} 60%,
                          ${SEVERITY_COLORS.critical} 80%)`
                      }}
                    />
                    {/* Indicator marker */}
                    <div
                      className="absolute top-1/2 -translate-y-1/2 w-3 h-5 bg-white dark:bg-gray-900 border-2 rounded shadow-sm transition-all"
                      style={{
                        left: `${Math.min(avgSev, 100)}%`,
                        transform: `translateX(-50%) translateY(-50%)`,
                        borderColor: getSeverityColor(avgSev),
                      }}
                    />
                  </div>
                  <div className="flex justify-between mt-1 text-[10px] text-gray-400 dark:text-gray-500">
                    <span>INFO</span>
                    <span>LOW</span>
                    <span>MED</span>
                    <span>HIGH</span>
                    <span>CRIT</span>
                  </div>
                </div>
              );
            })()}

            {/* Trend Chart */}
            {loadingTrends ? (
              <div className="flex items-center justify-center h-[200px]">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-red-500"></div>
              </div>
            ) : trendData.length > 0 ? (
              <div className="h-[200px] mb-4">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={trendData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                    <XAxis
                      dataKey="date"
                      tickFormatter={formatDate}
                      tick={{ fill: '#9CA3AF', fontSize: 10 }}
                      axisLine={{ stroke: '#4B5563' }}
                    />
                    <YAxis
                      tick={{ fill: '#9CA3AF', fontSize: 10 }}
                      axisLine={{ stroke: '#4B5563' }}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#1F2937',
                        border: 'none',
                        borderRadius: '0.5rem',
                        color: '#F9FAFB',
                      }}
                      labelFormatter={formatDate}
                    />
                    <Bar
                      dataKey="count"
                      name="Threats"
                      fill={CATEGORY_COLORS[selectedCategory] || '#6B7280'}
                      radius={[4, 4, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : null}

            {/* View Threats Button */}
            <button
              onClick={() => onCategoryFilter(selectedCategory)}
              className="w-full mt-4 px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors text-sm font-medium"
            >
              View All {THREAT_CATEGORY_LABELS[selectedCategory] || selectedCategory} Threats
            </button>
          </div>
        ) : (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-8 text-center">
            <Shield className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Select a category to view details
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
