import { useMemo } from 'react';
import { Icon } from '@aunoo/ui';
import './visuals.css';

/*
 * A small line of a theme's overall score across past detection runs, as the old TopicSparkline.
 * Green when the latest run is more than 5 points above the first, red when more than 5 below.
 */

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

type Trend = 'rising' | 'declining' | 'stable';
const TONE: Record<Trend, string> = { rising: 'et-tone-up', declining: 'et-tone-down', stable: 'et-tone-flat' };
const ICON = { rising: 'ArrowUp', declining: 'ArrowDown', stable: 'Minus' } as const;

export function TopicSparkline({ history, width = 80, height = 24, className, showTrend = true }: TopicSparklineProps) {
  const shape = useMemo(() => {
    if (!history || history.length < 2) return null;
    const sorted = [...history].sort((a, b) => new Date(a.run_date).getTime() - new Date(b.run_date).getTime());
    const scores = sorted.map((h) => Number(h.composite_score) || 0);
    const min = Math.min(...scores);
    const max = Math.max(...scores);
    const range = max - min || 1;
    const pad = 2;
    const w = width - pad * 2;
    const h = height - pad * 2;
    const pts = scores.map((s, i) => [pad + (i / (scores.length - 1)) * w, pad + h - ((s - min) / range) * h] as const);
    const line = `M ${pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' L ')}`;
    const diff = scores[scores.length - 1] - scores[0];
    const trend: Trend = diff > 5 ? 'rising' : diff < -5 ? 'declining' : 'stable';
    return { line, area: `${line} L ${width - pad},${height - pad} L ${pad},${height - pad} Z`, last: pts[pts.length - 1], latest: scores[scores.length - 1], first: scores[0], trend, n: scores.length };
  }, [history, width, height]);

  if (!shape) {
    return (
      <span className={['et-muted', className].filter(Boolean).join(' ')}>
        <Icon name="Minus" size="sm" /> No history
      </span>
    );
  }
  const tone = TONE[shape.trend];
  return (
    <span className={['et-spark', className].filter(Boolean).join(' ')}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Overall score over ${shape.n} runs: ${Math.round(shape.first)} to ${Math.round(shape.latest)}, ${shape.trend}`}>
        <path className={`et-spark__area ${tone}`} d={shape.area} />
        <path className={`et-spark__line ${tone}`} d={shape.line} />
        <circle className={tone} cx={shape.last[0]} cy={shape.last[1]} r={2} />
      </svg>
      {showTrend && (
        <span className={`et-spark__value ${tone}`}>
          <Icon name={ICON[shape.trend]} size="sm" />
          {Math.round(shape.latest)}
        </span>
      )}
    </span>
  );
}

/** Larger sparkline for an expanded view */
export function TopicSparklineLarge({ history, className }: { history: HistoryPoint[]; className?: string }) {
  return <TopicSparkline history={history} width={150} height={40} className={className} showTrend />;
}

export default TopicSparkline;
