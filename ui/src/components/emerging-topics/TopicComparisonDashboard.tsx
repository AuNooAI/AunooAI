/**
 * Emerging Topics Overview Dashboard
 * Contains: Timeline Chart, Category Radar, Scatter plot, and Score distribution
 */

import { useMemo, useState } from 'react';
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
  CartesianGrid,
} from 'recharts';
import { ChevronDown, ChevronUp, BarChart3, TrendingUp, Calendar, PieChart } from 'lucide-react';
import { TopicsTimelineChart } from './TopicsTimelineChart';
import { CategoryRadarChart } from './CategoryRadarChart';

interface TrendScore {
  volume: number;
  velocity: number;
  diversity: number;
  novelty: number;
  composite: number;
  urgency?: 'low' | 'medium' | 'high';
}

interface EmergingTopic {
  id: number;
  topic_label: string;
  topic_description?: string;
  detection_date: string;
  first_detection_date?: string;
  last_detection_date?: string;
  article_count: number;
  velocity: 'accelerating' | 'stable' | 'decelerating';
  trajectory?: string;
  trend_score?: TrendScore;
  confidence_score?: number;
  key_themes?: string[];
}

interface TopicComparisonDashboardProps {
  topics: EmergingTopic[];
  className?: string;
  onTopicClick?: (topic: EmergingTopic) => void;
}

// Velocity colors
const velocityColors: Record<string, string> = {
  accelerating: '#10b981', // Green
  stable: '#6b7280',       // Gray
  decelerating: '#f59e0b', // Amber
};

// Score bucket colors (gradient from low to high)
const bucketColors = [
  '#ef4444', // 0-20: Red
  '#f97316', // 20-40: Orange
  '#eab308', // 40-60: Yellow
  '#22c55e', // 60-80: Green
  '#10b981', // 80-100: Emerald
];

export function TopicComparisonDashboard({
  topics,
  className = '',
  onTopicClick,
}: TopicComparisonDashboardProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  // Transform data for scatter plot
  const scatterData = useMemo(() => {
    return topics.map((t) => ({
      id: t.id,
      name: t.topic_label,
      x: t.trend_score?.composite || (t.confidence_score || 0) * 100,
      y: t.article_count,
      velocity: t.velocity || 'stable',
      color: velocityColors[t.velocity || 'stable'],
    }));
  }, [topics]);

  // Transform data for histogram (score distribution)
  const histogramData = useMemo(() => {
    const buckets = [
      { range: '0-20', min: 0, max: 20, count: 0 },
      { range: '20-40', min: 20, max: 40, count: 0 },
      { range: '40-60', min: 40, max: 60, count: 0 },
      { range: '60-80', min: 60, max: 80, count: 0 },
      { range: '80-100', min: 80, max: 100, count: 0 },
    ];

    topics.forEach((t) => {
      const score = t.trend_score?.composite || (t.confidence_score || 0) * 100;
      const bucketIndex = Math.min(Math.floor(score / 20), 4);
      buckets[bucketIndex].count++;
    });

    return buckets;
  }, [topics]);

  // Velocity distribution
  const velocityDist = useMemo(() => {
    const dist = { accelerating: 0, stable: 0, decelerating: 0 };
    topics.forEach((t) => {
      const v = t.velocity || 'stable';
      if (v in dist) dist[v as keyof typeof dist]++;
    });
    return [
      { name: 'Accelerating', value: dist.accelerating, color: velocityColors.accelerating },
      { name: 'Stable', value: dist.stable, color: velocityColors.stable },
      { name: 'Decelerating', value: dist.decelerating, color: velocityColors.decelerating },
    ].filter(d => d.value > 0);
  }, [topics]);

  // Don't render if not enough topics
  if (topics.length < 2) {
    return null;
  }

  return (
    <div className={`bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg mb-4 ${className}`}>
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-800/50 rounded-t-lg transition-colors"
      >
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-pink-500" />
          <span className="font-medium text-gray-900 dark:text-gray-100">
            Emerging Topics Overview
          </span>
          <span className="text-sm text-gray-500 dark:text-gray-400">
            ({topics.length} topics)
          </span>
        </div>
        {isExpanded ? (
          <ChevronUp className="w-5 h-5 text-gray-400" />
        ) : (
          <ChevronDown className="w-5 h-5 text-gray-400" />
        )}
      </button>

      {/* Content */}
      {isExpanded && (
        <div className="px-4 pb-4 border-t border-gray-100 dark:border-gray-800">
          {/* Row 1: Timeline Chart and Category Radar */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-4">
            <div className="lg:col-span-2">
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                <Calendar className="w-4 h-4" />
                Topics Timeline (7 Days)
              </h4>
              <TopicsTimelineChart
                topics={topics}
                daysToShow={7}
                onTopicClick={onTopicClick}
                className="border-0 p-0 bg-transparent"
              />
            </div>
            <div>
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                <PieChart className="w-4 h-4" />
                Category Distribution
              </h4>
              <CategoryRadarChart
                topics={topics}
                size={220}
                showLegend={false}
                className="border-0 p-0 bg-transparent"
              />
            </div>
          </div>

          {/* Row 2: Scatter Plot and Histogram */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6 pt-4 border-t border-gray-100 dark:border-gray-800">
            {/* Scatter Plot: Score vs Article Count */}
            <div>
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                <TrendingUp className="w-4 h-4" />
                Score vs Article Count
              </h4>
              <div className="h-56 bg-gray-50 dark:bg-gray-800/50 rounded-lg p-2">
                <ResponsiveContainer width="100%" height="100%">
                  <ScatterChart margin={{ top: 10, right: 10, bottom: 30, left: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.1} />
                    <XAxis
                      type="number"
                      dataKey="x"
                      name="Score"
                      domain={[0, 100]}
                      tick={{ fontSize: 11, fill: 'currentColor' }}
                      tickLine={false}
                      axisLine={{ stroke: 'currentColor', strokeOpacity: 0.2 }}
                      label={{ value: 'Composite Score', position: 'bottom', offset: 15, fontSize: 11, fill: 'currentColor' }}
                    />
                    <YAxis
                      type="number"
                      dataKey="y"
                      name="Articles"
                      tick={{ fontSize: 11, fill: 'currentColor' }}
                      tickLine={false}
                      axisLine={{ stroke: 'currentColor', strokeOpacity: 0.2 }}
                      label={{ value: 'Articles', angle: -90, position: 'insideLeft', fontSize: 11, fill: 'currentColor' }}
                    />
                    <ZAxis range={[60, 200]} />
                    <Tooltip
                      cursor={{ strokeDasharray: '3 3' }}
                      content={({ active, payload }) => {
                        if (active && payload && payload.length) {
                          const data = payload[0].payload;
                          return (
                            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-2 text-sm">
                              <div className="font-medium text-gray-900 dark:text-gray-100 max-w-[200px] truncate">
                                {data.name}
                              </div>
                              <div className="text-gray-600 dark:text-gray-400">
                                Score: {Math.round(data.x)} · Articles: {data.y}
                              </div>
                              <div className="text-xs" style={{ color: data.color }}>
                                {data.velocity}
                              </div>
                            </div>
                          );
                        }
                        return null;
                      }}
                    />
                    <Scatter data={scatterData}>
                      {scatterData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} fillOpacity={0.7} />
                      ))}
                    </Scatter>
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Score Distribution Histogram */}
            <div>
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                <BarChart3 className="w-4 h-4" />
                Score Distribution
              </h4>
              <div className="h-56 bg-gray-50 dark:bg-gray-800/50 rounded-lg p-2">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={histogramData} margin={{ top: 10, right: 10, bottom: 30, left: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.1} />
                    <XAxis
                      dataKey="range"
                      tick={{ fontSize: 11, fill: 'currentColor' }}
                      tickLine={false}
                      axisLine={{ stroke: 'currentColor', strokeOpacity: 0.2 }}
                      label={{ value: 'Score Range', position: 'bottom', offset: 15, fontSize: 11, fill: 'currentColor' }}
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: 'currentColor' }}
                      tickLine={false}
                      axisLine={{ stroke: 'currentColor', strokeOpacity: 0.2 }}
                      label={{ value: 'Topics', angle: -90, position: 'insideLeft', fontSize: 11, fill: 'currentColor' }}
                    />
                    <Tooltip
                      cursor={{ fill: 'currentColor', fillOpacity: 0.05 }}
                      content={({ active, payload }) => {
                        if (active && payload && payload.length) {
                          const data = payload[0].payload;
                          return (
                            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-2 text-sm">
                              <div className="font-medium text-gray-900 dark:text-gray-100">
                                Score {data.range}
                              </div>
                              <div className="text-gray-600 dark:text-gray-400">
                                {data.count} topic{data.count !== 1 ? 's' : ''}
                              </div>
                            </div>
                          );
                        }
                        return null;
                      }}
                    />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                      {histogramData.map((_, index) => (
                        <Cell key={`cell-${index}`} fill={bucketColors[index]} fillOpacity={0.8} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Velocity distribution mini-bar */}
          {velocityDist.length > 0 && (
            <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
              <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase mb-2">
                Velocity Distribution
              </h4>
              <div className="flex items-center gap-4">
                {velocityDist.map((d) => (
                  <div key={d.name} className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: d.color }}
                    />
                    <span className="text-sm text-gray-600 dark:text-gray-400">
                      {d.name}: <span className="font-medium">{d.value}</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default TopicComparisonDashboard;
