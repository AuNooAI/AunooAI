/**
 * Policy Tracker Timeline Tab
 * Temporal analysis: day of week, daily intensity, rolling averages
 */

import { useState, useEffect } from 'react';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ComposedChart,
  Area,
} from 'recharts';
import { Loader2 } from 'lucide-react';
import type { DayOfWeekData, DailyIntensityData, TemporalData } from '../../services/policyTrackerApi';

interface PolicyTimelineTabProps {
  dayOfWeek: DayOfWeekData[];
  dailyIntensity: DailyIntensityData[];
  temporalData: TemporalData[];
  loading: boolean;
  onLoad: () => void;
}

type TimelineView = 'daily' | 'dayOfWeek' | 'monthly';

export function PolicyTimelineTab({
  dayOfWeek,
  dailyIntensity,
  temporalData,
  loading,
  onLoad,
}: PolicyTimelineTabProps) {
  const [activeView, setActiveView] = useState<TimelineView>('daily');

  // Load data on mount
  useEffect(() => {
    if (dailyIntensity.length === 0 && dayOfWeek.length === 0) {
      onLoad();
    }
  }, []);

  // Sample daily intensity data for display (last 90 days)
  const sampledDailyData = dailyIntensity.slice(-90);

  if (loading && dailyIntensity.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-8">
        <div className="flex items-center justify-center">
          <Loader2 className="w-6 h-6 animate-spin text-pink-500" />
          <span className="ml-2 text-gray-500 dark:text-gray-400">Loading timeline data...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* View Selector */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
            Temporal Analysis
          </h3>
          <div className="flex gap-1 bg-gray-100 dark:bg-gray-700 rounded-lg p-0.5">
            <button
              onClick={() => setActiveView('daily')}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                activeView === 'daily'
                  ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm'
                  : 'text-gray-600 dark:text-gray-400'
              }`}
            >
              Daily Intensity
            </button>
            <button
              onClick={() => setActiveView('dayOfWeek')}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                activeView === 'dayOfWeek'
                  ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm'
                  : 'text-gray-600 dark:text-gray-400'
              }`}
            >
              Day of Week
            </button>
            <button
              onClick={() => setActiveView('monthly')}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                activeView === 'monthly'
                  ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm'
                  : 'text-gray-600 dark:text-gray-400'
              }`}
            >
              Monthly Totals
            </button>
          </div>
        </div>

        {/* Daily Intensity with Rolling Average */}
        {activeView === 'daily' && (
          <div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
              Daily article count with 7-day rolling average (last 90 days)
            </p>
            <ResponsiveContainer width="100%" height={350}>
              <ComposedChart
                data={sampledDailyData}
                margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                <XAxis
                  dataKey="date"
                  stroke="#9CA3AF"
                  fontSize={10}
                  tickFormatter={(value) => {
                    const date = new Date(value);
                    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                  }}
                  interval={6}
                />
                <YAxis stroke="#9CA3AF" fontSize={12} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1F2937',
                    border: 'none',
                    borderRadius: '8px',
                    color: '#F9FAFB',
                  }}
                  labelFormatter={(value) => new Date(value).toLocaleDateString('en-US', {
                    weekday: 'short',
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric'
                  })}
                />
                <Legend />
                <Bar dataKey="count" fill="#EC4899" name="Daily Count" opacity={0.6} />
                <Line
                  type="monotone"
                  dataKey="rolling_avg_7day"
                  stroke="#3B82F6"
                  strokeWidth={2}
                  dot={false}
                  name="7-Day Average"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Day of Week Distribution */}
        {activeView === 'dayOfWeek' && (
          <div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
              Article distribution by day of week
            </p>
            <ResponsiveContainer width="100%" height={350}>
              <BarChart
                data={dayOfWeek}
                margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                <XAxis dataKey="day" stroke="#9CA3AF" fontSize={12} />
                <YAxis stroke="#9CA3AF" fontSize={12} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1F2937',
                    border: 'none',
                    borderRadius: '8px',
                    color: '#F9FAFB',
                  }}
                  formatter={(value: number, name: string) => [
                    `${value} articles (${dayOfWeek.find(d => d.article_count === value)?.percentage || 0}%)`,
                    'Count'
                  ]}
                />
                <Bar dataKey="article_count" fill="#EC4899" name="Articles" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Monthly Totals */}
        {activeView === 'monthly' && (
          <div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
              Monthly article totals over time
            </p>
            <ResponsiveContainer width="100%" height={350}>
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
                  stroke="#EC4899"
                  strokeWidth={2}
                  dot={{ fill: '#EC4899', strokeWidth: 2 }}
                  activeDot={{ r: 6 }}
                  name="Total Articles"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Stats Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Peak Day</p>
          <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {dayOfWeek.length > 0
              ? dayOfWeek.reduce((max, d) => d.article_count > max.article_count ? d : max).day
              : 'N/A'}
          </p>
          <p className="text-xs text-gray-400 mt-1">
            {dayOfWeek.length > 0
              ? `${dayOfWeek.reduce((max, d) => d.article_count > max.article_count ? d : max).article_count} articles`
              : ''}
          </p>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Avg Daily</p>
          <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {dailyIntensity.length > 0
              ? (dailyIntensity.reduce((sum, d) => sum + d.count, 0) / dailyIntensity.length).toFixed(1)
              : 'N/A'}
          </p>
          <p className="text-xs text-gray-400 mt-1">articles per day</p>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Peak Daily</p>
          <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {dailyIntensity.length > 0
              ? Math.max(...dailyIntensity.map(d => d.count))
              : 'N/A'}
          </p>
          <p className="text-xs text-gray-400 mt-1">
            {dailyIntensity.length > 0
              ? new Date(dailyIntensity.reduce((max, d) => d.count > max.count ? d : max).date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
              : ''}
          </p>
        </div>
      </div>
    </div>
  );
}
