/**
 * ScienceWatch Charts Component
 * Displays visualizations using Recharts
 */

import { useState } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  Legend,
  AreaChart,
  Area,
} from 'recharts';
import type { ScienceCategory, TemporalData } from '../../services/scienceFundingApi';
import { ChartDownloadButton } from './ChartDownloadButton';
import { CATEGORY_COLORS, CATEGORY_SHORT_NAMES, CATEGORY_DESCRIPTIONS } from '../../services/scienceFundingApi';

interface ScienceFundingChartsProps {
  categories: ScienceCategory[];
  temporalData: TemporalData[];
  loading: boolean;
}

type ChartView = 'categories' | 'trend' | 'stacked';

export function ScienceFundingCharts({
  categories,
  temporalData,
  loading,
}: ScienceFundingChartsProps) {
  const [activeView, setActiveView] = useState<ChartView>('categories');

  // Transform temporal data for stacked chart
  const stackedData = temporalData.map((item) => ({
    month: item.month,
    ...item.by_category,
  }));

  // Get top 5 categories for the stacked chart
  const topCategories = [...categories]
    .sort((a, b) => b.article_count - a.article_count)
    .slice(0, 5)
    .map((c) => c.category);

  // Transform categories for bar chart
  const categoryBarData = categories.map((c) => ({
    name: CATEGORY_SHORT_NAMES[c.category] || c.category,
    fullName: c.category,
    description: CATEGORY_DESCRIPTIONS[c.category] || '',
    count: c.article_count,
    fill: CATEGORY_COLORS[c.category] || '#6B7280',
  }));

  if (loading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 mb-6">
        <div className="animate-pulse">
          <div className="h-6 w-32 bg-gray-200 dark:bg-gray-700 rounded mb-4" />
          <div className="h-64 bg-gray-200 dark:bg-gray-700 rounded" />
        </div>
      </div>
    );
  }

  return (
    <div id="chart-science-funding" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 mb-6">
      {/* Chart Tabs */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
            Science Funding Category Analysis
          </h3>
          <ChartDownloadButton targetId="chart-science-funding" filename="science-funding-analysis" />
        </div>
        <div className="flex gap-1 bg-gray-100 dark:bg-gray-700 rounded-lg p-0.5">
          <button
            onClick={() => setActiveView('categories')}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
              activeView === 'categories'
                ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm'
                : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100'
            }`}
          >
            Categories
          </button>
          <button
            onClick={() => setActiveView('trend')}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
              activeView === 'trend'
                ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm'
                : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100'
            }`}
          >
            Monthly Trend
          </button>
          <button
            onClick={() => setActiveView('stacked')}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
              activeView === 'stacked'
                ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm'
                : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100'
            }`}
          >
            Category Trends
          </button>
        </div>
      </div>

      {/* Category Bar Chart */}
      {activeView === 'categories' && (
        <ResponsiveContainer width="100%" height={300}>
          <BarChart
            data={categoryBarData}
            layout="vertical"
            margin={{ top: 5, right: 30, left: 100, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
            <XAxis type="number" stroke="#9CA3AF" fontSize={12} />
            <YAxis
              type="category"
              dataKey="name"
              stroke="#9CA3AF"
              fontSize={11}
              width={95}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1F2937',
                border: 'none',
                borderRadius: '8px',
                color: '#F9FAFB',
              }}
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  const data = payload[0].payload;
                  return (
                    <div className="p-2 bg-gray-800 rounded-lg border-none">
                      <p className="font-medium text-gray-100">{data.fullName}</p>
                      {data.description && (
                        <p className="text-xs text-gray-500 mt-1 max-w-xs">{data.description}</p>
                      )}
                      <p className="text-sm text-gray-200 mt-1">{data.count} articles</p>
                    </div>
                  );
                }
                return null;
              }}
            />
            <Bar dataKey="count" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}

      {/* Monthly Trend Line Chart */}
      {activeView === 'trend' && (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart
            data={temporalData}
            margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
            <XAxis dataKey="month" stroke="#9CA3AF" fontSize={12} />
            <YAxis stroke="#9CA3AF" fontSize={12} />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1F2937',
                border: 'none',
                borderRadius: '8px',
                color: '#F9FAFB',
              }}
            />
            <Line
              type="monotone"
              dataKey="total"
              stroke="#059669"
              strokeWidth={2}
              dot={{ fill: '#059669', strokeWidth: 2 }}
              activeDot={{ r: 6 }}
              name="Total Articles"
            />
          </LineChart>
        </ResponsiveContainer>
      )}

      {/* Stacked Area Chart for Top Categories */}
      {activeView === 'stacked' && (
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart
            data={stackedData}
            margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
            <XAxis dataKey="month" stroke="#9CA3AF" fontSize={12} />
            <YAxis stroke="#9CA3AF" fontSize={12} />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1F2937',
                border: 'none',
                borderRadius: '8px',
                color: '#F9FAFB',
              }}
            />
            <Legend
              wrapperStyle={{ fontSize: '11px' }}
              formatter={(value) => CATEGORY_SHORT_NAMES[value] || value}
            />
            {topCategories.map((category) => (
              <Area
                key={category}
                type="monotone"
                dataKey={category}
                stackId="1"
                stroke={CATEGORY_COLORS[category]}
                fill={CATEGORY_COLORS[category]}
                fillOpacity={0.6}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
