import { RadarChart, type ChartColor } from '@aunoo/ui';
import './visuals.css';

/*
 * The five trend scores (volume, velocity, diversity, novelty, overall) on a radar, as the old
 * TopicScoreRadar. The colour steps with the average score, so a strong theme reads as such.
 */

interface TrendScore {
  volume: number;
  velocity: number;
  diversity: number;
  novelty: number;
  composite: number;
}

interface TopicScoreRadarProps {
  trendScore: TrendScore;
  /** Width in pixels (the chart keeps its own proportions) */
  size?: number;
  /** Kept for the old interface; the design system's radar always names its axes */
  showLabels?: boolean;
  className?: string;
}

const AXES = ['Volume', 'Velocity', 'Diversity', 'Novelty', 'Overall'];

function colourFor(avg: number): ChartColor {
  if (avg >= 70) return 'positive';
  if (avg >= 50) return 1;
  if (avg >= 30) return 'caution';
  return 'neutral';
}

export function TopicScoreRadar(props: TopicScoreRadarProps) {
  const { trendScore: s, size = 180, className } = props;
  const values = [s.volume, s.velocity, s.diversity, s.novelty, s.composite].map((v) => Math.round(Number(v) || 0));
  const avg = values.reduce((a, b) => a + b, 0) / values.length;
  return (
    <div className={className} style={{ maxWidth: Math.max(size, 220) }}>
      <RadarChart
        title="Trend scores out of 100"
        axes={AXES}
        series={[{ id: 'score', label: 'Score', color: colourFor(avg), values }]}
        formatValue={(v) => `${Math.round(v)}/100`}
      />
    </div>
  );
}

/** Compact version for card headers */
export function TopicScoreRadarMini({ trendScore, className }: { trendScore: TrendScore; className?: string }) {
  return <TopicScoreRadar trendScore={trendScore} size={100} showLabels={false} className={className} />;
}

export default TopicScoreRadar;
