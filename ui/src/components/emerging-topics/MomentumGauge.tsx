/**
 * MomentumGauge - Speedometer-style velocity indicator
 * Shows growth momentum with color-coded zones (red/yellow/green)
 */

import { useMemo } from 'react';

interface MomentumGaugeProps {
  velocity: 'accelerating' | 'stable' | 'decelerating';
  velocityScore?: number; // 0-100 from trend_score.velocity
  growthRate?: number; // percentage
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  className?: string;
}

// Size configurations
const sizeConfig = {
  sm: { width: 60, height: 36, strokeWidth: 6, fontSize: 9, needleLength: 20 },
  md: { width: 80, height: 48, strokeWidth: 8, fontSize: 11, needleLength: 28 },
  lg: { width: 100, height: 60, strokeWidth: 10, fontSize: 13, needleLength: 35 },
};

// Colors for zones
const colors = {
  decelerate: '#ef4444', // Red
  stable: '#eab308', // Yellow
  accelerate: '#22c55e', // Green
  needle: '#1f2937', // Dark gray
  needleDark: '#f3f4f6', // Light gray for dark mode
};

export function MomentumGauge({
  velocity,
  velocityScore,
  size = 'md',
  showLabel = true,
  className = '',
}: MomentumGaugeProps) {
  const config = sizeConfig[size];
  const cx = config.width / 2;
  const cy = config.height - 4;
  const radius = config.width / 2 - config.strokeWidth / 2 - 2;

  // Calculate the effective score (0-100)
  const effectiveScore = useMemo(() => {
    if (velocityScore !== undefined && velocityScore >= 0 && velocityScore <= 100) {
      return velocityScore;
    }
    // Fall back to categorical mapping
    switch (velocity) {
      case 'decelerating':
        return 16.5; // Center of red zone
      case 'stable':
        return 50; // Center of yellow zone
      case 'accelerating':
        return 83.5; // Center of green zone
      default:
        return 50;
    }
  }, [velocity, velocityScore]);

  // Calculate needle angle (180 = left, 0 = right)
  // Score 0 = 180deg (left), Score 100 = 0deg (right)
  const needleAngle = 180 - (effectiveScore / 100) * 180;
  const needleRadians = (needleAngle * Math.PI) / 180;
  const needleX = cx + Math.cos(needleRadians) * config.needleLength;
  const needleY = cy - Math.sin(needleRadians) * config.needleLength;

  // Arc path helper
  const describeArc = (startAngle: number, endAngle: number) => {
    const startRad = (startAngle * Math.PI) / 180;
    const endRad = (endAngle * Math.PI) / 180;
    const x1 = cx + radius * Math.cos(startRad);
    const y1 = cy - radius * Math.sin(startRad);
    const x2 = cx + radius * Math.cos(endRad);
    const y2 = cy - radius * Math.sin(endRad);
    const largeArc = endAngle - startAngle > 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 0 ${x2} ${y2}`;
  };

  // Get label text and color
  const labelConfig = useMemo(() => {
    switch (velocity) {
      case 'accelerating':
        return { text: 'Accelerating', color: colors.accelerate };
      case 'decelerating':
        return { text: 'Slowing', color: colors.decelerate };
      default:
        return { text: 'Stable', color: colors.stable };
    }
  }, [velocity]);

  return (
    <div className={`flex flex-col items-center ${className}`}>
      <svg
        width={config.width}
        height={config.height}
        viewBox={`0 0 ${config.width} ${config.height}`}
        className="overflow-visible"
      >
        {/* Background arc (gray) */}
        <path
          d={describeArc(180, 0)}
          fill="none"
          stroke="currentColor"
          strokeOpacity={0.1}
          strokeWidth={config.strokeWidth}
          strokeLinecap="round"
        />

        {/* Red zone (0-33, left side, 180-120 deg) */}
        <path
          d={describeArc(180, 120)}
          fill="none"
          stroke={colors.decelerate}
          strokeWidth={config.strokeWidth}
          strokeLinecap="round"
          strokeOpacity={0.8}
        />

        {/* Yellow zone (33-66, middle, 120-60 deg) */}
        <path
          d={describeArc(120, 60)}
          fill="none"
          stroke={colors.stable}
          strokeWidth={config.strokeWidth}
          strokeOpacity={0.8}
        />

        {/* Green zone (66-100, right side, 60-0 deg) */}
        <path
          d={describeArc(60, 0)}
          fill="none"
          stroke={colors.accelerate}
          strokeWidth={config.strokeWidth}
          strokeLinecap="round"
          strokeOpacity={0.8}
        />

        {/* Needle */}
        <line
          x1={cx}
          y1={cy}
          x2={needleX}
          y2={needleY}
          className="stroke-gray-800 dark:stroke-gray-200"
          strokeWidth={2}
          strokeLinecap="round"
          style={{
            transition: 'all 0.5s ease-out',
          }}
        />

        {/* Needle center dot */}
        <circle
          cx={cx}
          cy={cy}
          r={3}
          className="fill-gray-800 dark:fill-gray-200"
        />

        {/* Score value */}
        {velocityScore !== undefined && (
          <text
            x={cx}
            y={cy - config.needleLength - 6}
            textAnchor="middle"
            className="fill-gray-700 dark:fill-gray-300"
            fontSize={config.fontSize - 2}
            fontWeight="600"
          >
            {Math.round(velocityScore)}
          </text>
        )}
      </svg>

      {/* Label */}
      {showLabel && (
        <div
          className="text-xs font-medium mt-0.5"
          style={{ color: labelConfig.color }}
        >
          {labelConfig.text}
        </div>
      )}
    </div>
  );
}

/**
 * Mini version without label for tight spaces
 */
export function MomentumGaugeMini({
  velocity,
  velocityScore,
  className = '',
}: Omit<MomentumGaugeProps, 'size' | 'showLabel'>) {
  return (
    <MomentumGauge
      velocity={velocity}
      velocityScore={velocityScore}
      size="sm"
      showLabel={false}
      className={className}
    />
  );
}

export default MomentumGauge;
