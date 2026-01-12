/**
 * TrajectoryTimeline - Visual detection history across scans
 * Shows when a topic was detected vs missed with streak indicators
 */

import { useMemo } from 'react';
import { TrendingUp, TrendingDown, Minus, Zap } from 'lucide-react';

interface TrajectoryTimelineProps {
  firstDetection: string; // ISO date
  lastDetection: string; // ISO date
  detectionCount: number; // Total detections
  consecutiveDetections: number; // Current streak
  missedRuns: number; // Gaps in detection
  trajectory: string; // rising/stable/declining/volatile
  className?: string;
}

// Colors for detection states
const colors = {
  detected: '#22c55e', // Green
  missed: '#e5e7eb', // Light gray
  missedDark: '#374151', // Dark gray for dark mode
  rising: '#22c55e',
  declining: '#ef4444',
  stable: '#6b7280',
  volatile: '#f59e0b',
};

export function TrajectoryTimeline({
  firstDetection,
  lastDetection,
  detectionCount,
  consecutiveDetections,
  missedRuns,
  trajectory,
  className = '',
}: TrajectoryTimelineProps) {
  // Calculate total runs (detections + missed)
  const totalRuns = detectionCount + missedRuns;

  // Generate segments representing detection pattern
  const segments = useMemo(() => {
    if (totalRuns <= 0) return [];

    // Create pattern: we know total detections and missed runs
    // For visualization, we'll show the pattern with recent consecutive at the end
    const result: { type: 'detected' | 'missed'; isRecent: boolean }[] = [];

    // Calculate older runs (before current streak)
    const olderDetections = detectionCount - consecutiveDetections;
    const olderRuns = olderDetections + missedRuns;

    // Distribute older detections and misses
    if (olderRuns > 0) {
      // Simple approach: alternate or distribute based on ratio
      const detectRatio = olderRuns > 0 ? olderDetections / olderRuns : 0;
      for (let i = 0; i < olderRuns; i++) {
        // Distribute detections roughly evenly
        const shouldDetect = (i + 1) / olderRuns <= detectRatio ||
          (olderRuns === missedRuns && i % 2 === 0 && olderDetections > 0);
        result.push({
          type: Math.random() < detectRatio && olderDetections > result.filter(r => r.type === 'detected').length
            ? 'detected'
            : 'missed',
          isRecent: false,
        });
      }
      // Fix to ensure correct counts
      let detectedCount = result.filter(r => r.type === 'detected').length;
      for (let i = 0; i < result.length && detectedCount !== olderDetections; i++) {
        if (detectedCount < olderDetections && result[i].type === 'missed') {
          result[i].type = 'detected';
          detectedCount++;
        } else if (detectedCount > olderDetections && result[i].type === 'detected') {
          result[i].type = 'missed';
          detectedCount--;
        }
      }
    }

    // Add consecutive streak at the end (all detected)
    for (let i = 0; i < consecutiveDetections; i++) {
      result.push({
        type: 'detected',
        isRecent: i >= consecutiveDetections - 2, // Last 2 are "recent"
      });
    }

    return result;
  }, [detectionCount, consecutiveDetections, missedRuns, totalRuns]);

  // Get trajectory icon and color
  const trajectoryConfig = useMemo(() => {
    switch (trajectory) {
      case 'rising':
        return { icon: TrendingUp, color: colors.rising, label: 'Rising' };
      case 'declining':
        return { icon: TrendingDown, color: colors.declining, label: 'Declining' };
      case 'volatile':
        return { icon: Zap, color: colors.volatile, label: 'Volatile' };
      default:
        return { icon: Minus, color: colors.stable, label: 'Stable' };
    }
  }, [trajectory]);

  const TrajectoryIcon = trajectoryConfig.icon;

  // Format date for tooltip
  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return dateStr;
    }
  };

  // Don't render if no data
  if (totalRuns === 0 || detectionCount === 0) {
    return null;
  }

  const segmentWidth = Math.min(12, Math.max(4, 160 / totalRuns));
  const segmentGap = 2;

  return (
    <div className={`flex items-center gap-3 ${className}`}>
      {/* Timeline bar */}
      <div className="flex-1">
        {/* Date range label */}
        <div className="flex justify-between text-[10px] text-gray-600 dark:text-gray-400 mb-1">
          <span>{formatDate(firstDetection)}</span>
          <span>{formatDate(lastDetection)}</span>
        </div>

        {/* Segments */}
        <div className="flex items-center gap-px">
          {segments.map((segment, i) => (
            <div
              key={i}
              className={`h-2.5 rounded-sm transition-all ${
                segment.type === 'detected'
                  ? segment.isRecent
                    ? 'bg-green-500'
                    : 'bg-green-400/70 dark:bg-green-500/60'
                  : 'bg-gray-200 dark:bg-gray-700'
              }`}
              style={{
                width: segmentWidth,
                minWidth: 4,
              }}
              title={segment.type === 'detected' ? 'Detected' : 'Not detected'}
            />
          ))}
        </div>

        {/* Stats row */}
        <div className="flex items-center gap-2 mt-1 text-[10px] text-gray-500 dark:text-gray-400">
          <span>{detectionCount} detections</span>
          {consecutiveDetections > 1 && (
            <span className="text-green-600 dark:text-green-400 font-medium">
              {consecutiveDetections} streak
            </span>
          )}
          {missedRuns > 0 && (
            <span className="text-gray-600 dark:text-gray-400">
              {missedRuns} gaps
            </span>
          )}
        </div>
      </div>

      {/* Trajectory indicator */}
      <div
        className="flex flex-col items-center px-2 py-1 rounded bg-gray-50 dark:bg-gray-800/50"
        style={{ minWidth: 60 }}
      >
        <TrajectoryIcon
          className="w-4 h-4"
          style={{ color: trajectoryConfig.color }}
        />
        <span
          className="text-[10px] font-medium mt-0.5"
          style={{ color: trajectoryConfig.color }}
        >
          {trajectoryConfig.label}
        </span>
      </div>
    </div>
  );
}

/**
 * Compact version for card headers
 */
export function TrajectoryTimelineCompact({
  detectionCount,
  consecutiveDetections,
  trajectory,
  className = '',
}: Pick<TrajectoryTimelineProps, 'detectionCount' | 'consecutiveDetections' | 'trajectory' | 'className'>) {
  const trajectoryConfig = useMemo(() => {
    switch (trajectory) {
      case 'rising':
        return { icon: TrendingUp, color: colors.rising };
      case 'declining':
        return { icon: TrendingDown, color: colors.declining };
      case 'volatile':
        return { icon: Zap, color: colors.volatile };
      default:
        return { icon: Minus, color: colors.stable };
    }
  }, [trajectory]);

  const TrajectoryIcon = trajectoryConfig.icon;

  return (
    <div className={`flex items-center gap-2 text-xs ${className}`}>
      <span className="text-gray-500 dark:text-gray-400">
        {detectionCount}x
      </span>
      {consecutiveDetections > 1 && (
        <span className="text-green-600 dark:text-green-400 font-medium flex items-center gap-0.5">
          <Zap className="w-3 h-3" />
          {consecutiveDetections}
        </span>
      )}
      <TrajectoryIcon
        className="w-3.5 h-3.5"
        style={{ color: trajectoryConfig.color }}
      />
    </div>
  );
}

export default TrajectoryTimeline;
