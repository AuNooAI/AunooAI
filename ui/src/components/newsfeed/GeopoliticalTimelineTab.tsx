/**
 * GeopoliticalTimelineTab Component
 * Temporal trends and timeline charts for geopolitical hotspots
 */

import { useEffect } from 'react';
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import type { TimelineDataPoint } from '../../services/geopoliticalHotspotsApi';

interface GeopoliticalTimelineTabProps {
  timeline: TimelineDataPoint[];
  loading: boolean;
  onLoad: () => void;
}

export function GeopoliticalTimelineTab({
  timeline,
  loading,
  onLoad,
}: GeopoliticalTimelineTabProps) {
  // Load data on mount
  useEffect(() => {
    if (timeline.length === 0) {
      onLoad();
    }
  }, [timeline.length, onLoad]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-pulse text-gray-500 dark:text-gray-400">Loading timeline...</div>
      </div>
    );
  }

  // Format date for display
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  // Prepare data for charts
  const chartData = timeline.map((point) => ({
    ...point,
    date: formatDate(point.date),
    fullDate: point.date,
  }));

  return (
    <div className="space-y-6">
      {/* Activity Over Time */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Article Activity Over Time
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="colorArticles" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#EC4899" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#EC4899" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12, fill: '#6B7280' }}
              axisLine={{ stroke: '#E5E7EB' }}
            />
            <YAxis
              tick={{ fontSize: 12, fill: '#6B7280' }}
              axisLine={{ stroke: '#E5E7EB' }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'rgba(31, 41, 55, 0.9)',
                border: 'none',
                borderRadius: '0.5rem',
                color: '#F9FAFB',
              }}
              labelFormatter={(label) => `Date: ${label}`}
            />
            <Area
              type="monotone"
              dataKey="article_count"
              name="Articles"
              stroke="#EC4899"
              strokeWidth={2}
              fill="url(#colorArticles)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Intensity Trend */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Average Intensity Trend
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12, fill: '#6B7280' }}
              axisLine={{ stroke: '#E5E7EB' }}
            />
            <YAxis
              domain={[0, 100]}
              tick={{ fontSize: 12, fill: '#6B7280' }}
              axisLine={{ stroke: '#E5E7EB' }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'rgba(31, 41, 55, 0.9)',
                border: 'none',
                borderRadius: '0.5rem',
                color: '#F9FAFB',
              }}
              formatter={(value: number) => [`${value.toFixed(1)}%`, 'Intensity']}
            />
            <Legend />
            <Line
              type="monotone"
              dataKey="avg_intensity"
              name="Avg Intensity"
              stroke="#F97316"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Active Hotspots Over Time */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Active Hotspots Over Time
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="colorHotspots" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#3B82F6" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12, fill: '#6B7280' }}
              axisLine={{ stroke: '#E5E7EB' }}
            />
            <YAxis
              tick={{ fontSize: 12, fill: '#6B7280' }}
              axisLine={{ stroke: '#E5E7EB' }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'rgba(31, 41, 55, 0.9)',
                border: 'none',
                borderRadius: '0.5rem',
                color: '#F9FAFB',
              }}
            />
            <Area
              type="monotone"
              dataKey="hotspot_count"
              name="Active Hotspots"
              stroke="#3B82F6"
              strokeWidth={2}
              fill="url(#colorHotspots)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Summary Stats */}
      {chartData.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <SummaryCard
            label="Total Articles"
            value={chartData.reduce((sum, d) => sum + d.article_count, 0)}
          />
          <SummaryCard
            label="Peak Articles (Day)"
            value={Math.max(...chartData.map((d) => d.article_count))}
          />
          <SummaryCard
            label="Avg Intensity"
            value={`${(
              chartData.reduce((sum, d) => sum + d.avg_intensity, 0) / chartData.length
            ).toFixed(1)}%`}
          />
          <SummaryCard
            label="Peak Intensity"
            value={`${Math.max(...chartData.map((d) => d.avg_intensity)).toFixed(1)}%`}
          />
        </div>
      )}
    </div>
  );
}

interface SummaryCardProps {
  label: string;
  value: string | number;
}

function SummaryCard({ label, value }: SummaryCardProps) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{value}</div>
      <div className="text-sm text-gray-500 dark:text-gray-400">{label}</div>
    </div>
  );
}
