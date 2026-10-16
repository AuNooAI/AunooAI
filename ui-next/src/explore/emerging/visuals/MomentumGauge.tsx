import { useMemo } from 'react';
import './visuals.css';

/*
 * A half-dial for a theme's velocity, as the old MomentumGauge: red (slowing), amber (stable) and
 * green (accelerating) zones, with the needle at the velocity score (0–100) when there is one,
 * otherwise at the middle of the zone the velocity label names.
 */

interface MomentumGaugeProps {
  velocity: 'accelerating' | 'stable' | 'decelerating';
  /** 0–100, from trend_score.velocity */
  velocityScore?: number;
  /** Kept for the old interface; not drawn */
  growthRate?: number;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  className?: string;
}

const SIZES = {
  sm: { width: 60, height: 36, stroke: 6, font: 9, needle: 20 },
  md: { width: 80, height: 48, stroke: 8, font: 11, needle: 28 },
  lg: { width: 100, height: 60, stroke: 10, font: 13, needle: 35 },
};
const LABEL = {
  accelerating: { text: 'Accelerating', tone: 'et-tone-up' },
  decelerating: { text: 'Slowing', tone: 'et-tone-down' },
  stable: { text: 'Stable', tone: 'et-tone-warn' },
};

export function MomentumGauge({ velocity, velocityScore, size = 'md', showLabel = true, className }: MomentumGaugeProps) {
  const c = SIZES[size];
  const cx = c.width / 2;
  const cy = c.height - 4;
  const r = c.width / 2 - c.stroke / 2 - 2;
  const score = useMemo(() => {
    if (velocityScore !== undefined && velocityScore !== null && velocityScore >= 0 && velocityScore <= 100) return velocityScore;
    return velocity === 'decelerating' ? 16.5 : velocity === 'accelerating' ? 83.5 : 50;
  }, [velocity, velocityScore]);
  const angle = ((180 - (score / 100) * 180) * Math.PI) / 180;
  const arc = (from: number, to: number) => {
    const a = (from * Math.PI) / 180;
    const b = (to * Math.PI) / 180;
    return `M ${cx + r * Math.cos(a)} ${cy - r * Math.sin(a)} A ${r} ${r} 0 0 1 ${cx + r * Math.cos(b)} ${cy - r * Math.sin(b)}`;
  };
  const label = LABEL[velocity] ?? LABEL.stable;
  const scoreText = velocityScore !== undefined && velocityScore !== null ? `, velocity score ${Math.round(velocityScore)}` : '';
  return (
    <span className={['et-gauge', className].filter(Boolean).join(' ')}>
      <svg width={c.width} height={c.height} viewBox={`0 0 ${c.width} ${c.height}`} role="img" aria-label={`${label.text}${scoreText}`}>
        <path className="et-gauge__track" d={arc(180, 0)} strokeWidth={c.stroke} />
        <path className="et-gauge__zone et-tone-down" d={arc(180, 120)} strokeWidth={c.stroke} />
        <path className="et-gauge__zone et-tone-warn" d={arc(120, 60)} strokeWidth={c.stroke} />
        <path className="et-gauge__zone et-tone-up" d={arc(60, 0)} strokeWidth={c.stroke} />
        <line className="et-gauge__needle" x1={cx} y1={cy} x2={cx + Math.cos(angle) * c.needle} y2={cy - Math.sin(angle) * c.needle} />
        <circle className="et-gauge__hub" cx={cx} cy={cy} r={3} />
        {velocityScore !== undefined && velocityScore !== null && (
          <text className="et-gauge__score" x={cx} y={cy - c.needle - 6} textAnchor="middle" fontSize={c.font - 2}>{Math.round(velocityScore)}</text>
        )}
      </svg>
      {showLabel && <span className={`et-gauge__label ${label.tone}`}>{label.text}</span>}
    </span>
  );
}

/** Small version without the label */
export function MomentumGaugeMini({ velocity, velocityScore, className }: Omit<MomentumGaugeProps, 'size' | 'showLabel'>) {
  return <MomentumGauge velocity={velocity} velocityScore={velocityScore} size="sm" showLabel={false} className={className} />;
}

export default MomentumGauge;
