/**
 * GeopoliticalTimelineTab Component
 * Enhanced temporal trends with rolling averages, day of week distribution, and summary stats
 */

import { useEffect, useState, useCallback } from 'react';
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  ComposedChart,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
} from 'recharts';
import { Calendar, TrendingUp, Activity, Clock } from 'lucide-react';
import { ChartDownloadButton } from './ChartDownloadButton';
import {
  getTimelineData,
  getDailyCounts,
  getDayOfWeekDistribution,
  type TimelineDataPoint,
  type DailyCount,
  type DayOfWeekData,
} from '../../services/geopoliticalHotspotsApi';

interface GeopoliticalTimelineTabProps {
  timeline: TimelineDataPoint[];
  loading: boolean;
  onLoad: () => void;
}

export function GeopoliticalTimelineTab({
  timeline,
  loading: initialLoading,
  onLoad,
}: GeopoliticalTimelineTabProps) {
  const [dailyCounts, setDailyCounts] = useState<DailyCount[]>([]);
  const [dayOfWeekData, setDayOfWeekData] = useState<DayOfWeekData[]>([]);
  const [loadingDaily, setLoadingDaily] = useState(true);
  const [loadingDayOfWeek, setLoadingDayOfWeek] = useState(true);

  // Load data on mount
  useEffect(() => {
    if (timeline.length === 0) {
      onLoad();
    }
    fetchDailyCounts();
    fetchDayOfWeekData();
  }, [timeline.length, onLoad]);

  const fetchDailyCounts = async () => {
    setLoadingDaily(true);
    try {
      const data = await getDailyCounts(undefined, 30);
      setDailyCounts(data);
    } catch (err) {
      console.error('Error fetching daily counts:', err);
    } finally {
      setLoadingDaily(false);
    }
  };

  const fetchDayOfWeekData = async () => {
    setLoadingDayOfWeek(true);
    try {
      const data = await getDayOfWeekDistribution(undefined, 30);
      setDayOfWeekData(data);
    } catch (err) {
      console.error('Error fetching day of week data:', err);
    } finally {
      setLoadingDayOfWeek(false);
    }
  };

  // Don't block on enhanced data loading - show original timeline first
  const loading = initialLoading;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-pulse text-gray-500 dark:text-gray-400">Loading timeline...</div>
      </div>
    );
  }

  // Check if we have any data at all
  if (timeline.length === 0 && dailyCounts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <Clock className="w-12 h-12 text-gray-400 dark:text-gray-600 mb-4" />
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">No Timeline Data</h3>
        <p className="text-gray-500 dark:text-gray-400 mt-1">
          Timeline data will appear after articles are processed and linked to hotspots.
        </p>
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

  // Prepare daily counts with rolling average
  const dailyChartData = dailyCounts.map((day) => ({
    ...day,
    date: formatDate(day.date),
    fullDate: day.date,
  }));

  // Calculate summary statistics
  const totalArticles = chartData.reduce((sum, d) => sum + d.article_count, 0);
  const peakDay = chartData.length > 0 ? Math.max(...chartData.map((d) => d.article_count)) : 0;
  const avgDaily = chartData.length > 0 ? Math.round(totalArticles / chartData.length) : 0;
  const avgIntensity =
    chartData.length > 0
      ? (chartData.reduce((sum, d) => sum + d.avg_intensity, 0) / chartData.length).toFixed(1)
      : '0';
  const peakIntensity = chartData.length > 0 ? Math.max(...chartData.map((d) => d.avg_intensity)).toFixed(1) : '0';

  // Find peak day date
  const peakDayEntry = chartData.find((d) => d.article_count === peakDay);
  const peakDayDate = peakDayEntry?.date || 'N/A';

  // Find busiest day of week
  const busiestDay = dayOfWeekData.length > 0
    ? dayOfWeekData.reduce((max, day) => (day.article_count > max.article_count ? day : max), dayOfWeekData[0])
    : null;

  return (
    <div className="space-y-6">
      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
        <SummaryCard
          icon={<Activity className="w-5 h-5" />}
          label="Total Articles"
          value={totalArticles.toLocaleString()}
          color="text-pink-500"
        />
        <SummaryCard
          icon={<TrendingUp className="w-5 h-5" />}
          label="Peak Day"
          value={peakDay.toString()}
          subtitle={peakDayDate}
          color="text-orange-500"
        />
        <SummaryCard
          icon={<Calendar className="w-5 h-5" />}
          label="Daily Average"
          value={avgDaily.toString()}
          color="text-blue-500"
        />
        <SummaryCard
          icon={<Activity className="w-5 h-5" />}
          label="Avg Intensity"
          value={`${avgIntensity}%`}
          subtitle={`Peak: ${peakIntensity}%`}
          color="text-purple-500"
        />
        {busiestDay && (
          <SummaryCard
            icon={<Clock className="w-5 h-5" />}
            label="Busiest Day"
            value={busiestDay.day}
            subtitle={`${busiestDay.article_count} articles`}
            color="text-emerald-500"
          />
        )}
      </div>

      {/* Daily Intensity with Rolling Average */}
      {dailyChartData.length > 0 && (
        <div id="chart-geo-daily-activity" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
              Daily Article Activity
            </h3>
            <ChartDownloadButton targetId="chart-geo-daily-activity" filename="daily-article-activity" />
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
            Bars show daily count, line shows 7-day rolling average
          </p>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={dailyChartData}>
              <defs>
                <linearGradient id="colorDaily" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#EC4899" stopOpacity={0.8} />
                  <stop offset="95%" stopColor="#EC4899" stopOpacity={0.3} />
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
                  backgroundColor: 'rgba(31, 41, 55, 0.95)',
                  border: 'none',
                  borderRadius: '0.5rem',
                  color: '#F9FAFB',
                }}
                formatter={(value: number, name: string) => {
                  if (name === 'rolling_avg') return [value.toFixed(1), '7-Day Avg'];
                  return [value, 'Articles'];
                }}
              />
              <Legend />
              <Bar
                dataKey="article_count"
                name="Daily Articles"
                fill="url(#colorDaily)"
                radius={[4, 4, 0, 0]}
              />
              <Line
                type="monotone"
                dataKey="rolling_avg"
                name="7-Day Rolling Avg"
                stroke="#F97316"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
              {/* Reference line for average */}
              <ReferenceLine
                y={avgDaily}
                stroke="#9CA3AF"
                strokeDasharray="5 5"
                label={{
                  value: `Avg: ${avgDaily}`,
                  position: 'right',
                  fill: '#6B7280',
                  fontSize: 10,
                }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Day of Week Distribution */}
      {dayOfWeekData.length > 0 && (
        <div id="chart-geo-day-of-week" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
              Day of Week Distribution
            </h3>
            <ChartDownloadButton targetId="chart-geo-day-of-week" filename="day-of-week-distribution" />
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
            Article count by day of the week over the selected period
          </p>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={dayOfWeekData}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis
                dataKey="day"
                tick={{ fontSize: 12, fill: '#6B7280' }}
                axisLine={{ stroke: '#E5E7EB' }}
              />
              <YAxis
                tick={{ fontSize: 12, fill: '#6B7280' }}
                axisLine={{ stroke: '#E5E7EB' }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'rgba(31, 41, 55, 0.95)',
                  border: 'none',
                  borderRadius: '0.5rem',
                  color: '#F9FAFB',
                }}
                formatter={(value: number) => [value, 'Articles']}
              />
              <Bar
                dataKey="article_count"
                name="Articles"
                fill="#3B82F6"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Activity Over Time (Original Chart) */}
      <div id="chart-geo-monthly-activity" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-gray-900 dark:text-gray-100">
            Article Activity Over Time
          </h3>
          <ChartDownloadButton targetId="chart-geo-monthly-activity" filename="article-activity-over-time" />
        </div>
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
      <div id="chart-geo-intensity-trend" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-gray-900 dark:text-gray-100">
            Average Intensity Trend
          </h3>
          <ChartDownloadButton targetId="chart-geo-intensity-trend" filename="intensity-trend" />
        </div>
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
      <div id="chart-geo-active-hotspots" className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-gray-900 dark:text-gray-100">
            Active Hotspots Over Time
          </h3>
          <ChartDownloadButton targetId="chart-geo-active-hotspots" filename="active-hotspots" />
        </div>
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
    </div>
  );
}

interface SummaryCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  subtitle?: string;
  color: string;
}

function SummaryCard({ icon, label, value, subtitle, color }: SummaryCardProps) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <div className={`${color} mb-2`}>{icon}</div>
      <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{value}</div>
      <div className="text-sm text-gray-600 dark:text-gray-400">{label}</div>
      {subtitle && <div className="text-xs text-gray-500 dark:text-gray-500 mt-0.5">{subtitle}</div>}
    </div>
  );
}
