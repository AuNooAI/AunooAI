/**
 * TopicScoreRadar - Radar chart showing 5-dimensional trend scores
 * Displays Volume, Velocity, Diversity, Novelty, and Composite scores
 */

import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';

interface TrendScore {
  volume: number;
  velocity: number;
  diversity: number;
  novelty: number;
  composite: number;
}

interface TopicScoreRadarProps {
  trendScore: TrendScore;
  size?: number;
  showLabels?: boolean;
  className?: string;
}

export function TopicScoreRadar({
  trendScore,
  size = 180,
  showLabels = true,
  className = '',
}: TopicScoreRadarProps) {
  // Transform trend score into radar chart data format
  const data = [
    { metric: 'Volume', value: Math.round(trendScore.volume), fullMark: 100 },
    { metric: 'Velocity', value: Math.round(trendScore.velocity), fullMark: 100 },
    { metric: 'Diversity', value: Math.round(trendScore.diversity), fullMark: 100 },
    { metric: 'Novelty', value: Math.round(trendScore.novelty), fullMark: 100 },
    { metric: 'Overall', value: Math.round(trendScore.composite), fullMark: 100 },
  ];

  // Calculate average score for color intensity
  const avgScore = (trendScore.volume + trendScore.velocity + trendScore.diversity + trendScore.novelty + trendScore.composite) / 5;

  // Color based on score - higher scores get more vibrant colors
  const getColor = () => {
    if (avgScore >= 70) return { stroke: '#10b981', fill: 'rgba(16, 185, 129, 0.25)' }; // Green
    if (avgScore >= 50) return { stroke: '#3b82f6', fill: 'rgba(59, 130, 246, 0.25)' }; // Blue
    if (avgScore >= 30) return { stroke: '#f59e0b', fill: 'rgba(245, 158, 11, 0.25)' }; // Amber
    return { stroke: '#6b7280', fill: 'rgba(107, 114, 128, 0.2)' }; // Gray
  };

  const colors = getColor();

  return (
    <div className={`${className}`} style={{ width: size, height: size }}>
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart cx="50%" cy="50%" outerRadius="70%" data={data}>
          <PolarGrid
            stroke="currentColor"
            strokeOpacity={0.2}
            className="text-gray-600 dark:text-gray-300"
          />
          <PolarAngleAxis
            dataKey="metric"
            tick={showLabels ? {
              fill: 'currentColor',
              fontSize: 10,
              className: 'text-gray-600 dark:text-gray-300',
            } : false}
            tickLine={false}
          />
          <PolarRadiusAxis
            angle={90}
            domain={[0, 100]}
            tick={false}
            axisLine={false}
          />
          <Radar
            name="Score"
            dataKey="value"
            stroke={colors.stroke}
            fill={colors.fill}
            strokeWidth={2}
            dot={{
              r: 3,
              fill: colors.stroke,
              strokeWidth: 0,
            }}
            activeDot={{
              r: 5,
              fill: colors.stroke,
              strokeWidth: 2,
              stroke: '#fff',
            }}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (active && payload && payload.length) {
                const data = payload[0].payload;
                return (
                  <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg px-3 py-2 text-sm">
                    <div className="font-medium text-gray-900 dark:text-gray-100">
                      {data.metric}
                    </div>
                    <div className="text-gray-600 dark:text-gray-300">
                      Score: <span className="font-semibold">{data.value}</span>/100
                    </div>
                  </div>
                );
              }
              return null;
            }}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

/**
 * Compact version for card headers
 */
export function TopicScoreRadarMini({
  trendScore,
  className = '',
}: {
  trendScore: TrendScore;
  className?: string;
}) {
  return (
    <TopicScoreRadar
      trendScore={trendScore}
      size={100}
      showLabels={false}
      className={className}
    />
  );
}

export default TopicScoreRadar;
