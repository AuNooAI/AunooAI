/**
 * TopicSparkline - Mini trend line showing historical composite scores
 * SVG-based for lightweight rendering on multiple cards
 */

import { useMemo } from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface HistoryPoint {
  run_date: string;
  composite_score: number;
}

interface TopicSparklineProps {
  history: HistoryPoint[];
  width?: number;
  height?: number;
  className?: string;
  showTrend?: boolean;
}

export function TopicSparkline({
  history,
  width = 80,
  height = 24,
  className = '',
  showTrend = true,
}: TopicSparklineProps) {
  const { path, trend, trendColor, minScore, maxScore, latestScore } = useMemo(() => {
    if (!history || history.length < 2) {
      return { path: '', trend: 'stable', trendColor: 'text-gray-400', minScore: 0, maxScore: 100, latestScore: 0 };
    }

    // Sort by date
    const sorted = [...history].sort(
      (a, b) => new Date(a.run_date).getTime() - new Date(b.run_date).getTime()
    );

    const scores = sorted.map((h) => h.composite_score);
    const min = Math.min(...scores);
    const max = Math.max(...scores);
    const range = max - min || 1;

    // Calculate path points
    const padding = 2;
    const chartWidth = width - padding * 2;
    const chartHeight = height - padding * 2;

    const points = scores.map((score, i) => {
      const x = padding + (i / (scores.length - 1)) * chartWidth;
      const y = padding + chartHeight - ((score - min) / range) * chartHeight;
      return `${x},${y}`;
    });

    const pathString = `M ${points.join(' L ')}`;

    // Calculate trend (compare last vs first)
    const first = scores[0];
    const last = scores[scores.length - 1];
    const diff = last - first;
    let trend: 'rising' | 'declining' | 'stable';
    let color: string;

    if (diff > 5) {
      trend = 'rising';
      color = 'text-green-500';
    } else if (diff < -5) {
      trend = 'declining';
      color = 'text-red-500';
    } else {
      trend = 'stable';
      color = 'text-gray-400';
    }

    return {
      path: pathString,
      trend,
      trendColor: color,
      minScore: min,
      maxScore: max,
      latestScore: last,
    };
  }, [history, width, height]);

  // Not enough data
  if (!history || history.length < 2) {
    return (
      <div className={`flex items-center gap-1 text-xs text-gray-400 ${className}`}>
        <Minus className="w-3 h-3" />
        <span>No history</span>
      </div>
    );
  }

  // Get stroke color based on trend
  const getStrokeColor = () => {
    switch (trend) {
      case 'rising':
        return '#22c55e'; // Green
      case 'declining':
        return '#ef4444'; // Red
      default:
        return '#6b7280'; // Gray
    }
  };

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {/* Sparkline SVG */}
      <svg
        width={width}
        height={height}
        className="overflow-visible"
        viewBox={`0 0 ${width} ${height}`}
      >
        {/* Background gradient area */}
        <defs>
          <linearGradient id={`sparkline-gradient-${trend}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={getStrokeColor()} stopOpacity="0.2" />
            <stop offset="100%" stopColor={getStrokeColor()} stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Area fill */}
        <path
          d={`${path} L ${width - 2},${height - 2} L 2,${height - 2} Z`}
          fill={`url(#sparkline-gradient-${trend})`}
        />

        {/* Line */}
        <path
          d={path}
          fill="none"
          stroke={getStrokeColor()}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Latest point dot */}
        {history.length > 0 && (
          <circle
            cx={width - 2}
            cy={2 + (height - 4) - ((latestScore - minScore) / (maxScore - minScore || 1)) * (height - 4)}
            r="2"
            fill={getStrokeColor()}
          />
        )}
      </svg>

      {/* Trend indicator */}
      {showTrend && (
        <div className={`flex items-center gap-0.5 ${trendColor}`}>
          {trend === 'rising' && <TrendingUp className="w-3 h-3" />}
          {trend === 'declining' && <TrendingDown className="w-3 h-3" />}
          {trend === 'stable' && <Minus className="w-3 h-3" />}
          <span className="text-xs font-medium">{Math.round(latestScore)}</span>
        </div>
      )}
    </div>
  );
}

/**
 * Larger sparkline for expanded view
 */
export function TopicSparklineLarge({
  history,
  className = '',
}: {
  history: HistoryPoint[];
  className?: string;
}) {
  return (
    <TopicSparkline
      history={history}
      width={150}
      height={40}
      className={className}
      showTrend={true}
    />
  );
}

/**
 * Hook to fetch batch history for multiple topics
 */
export function useBatchHistory(topicIds: number[]) {
  // This would typically fetch from /api/emerging-topics/batch-history
  // For now, returns empty - will be connected when backend is ready
  return {
    data: {} as Record<number, HistoryPoint[]>,
    loading: false,
    error: null,
  };
}

export default TopicSparkline;
