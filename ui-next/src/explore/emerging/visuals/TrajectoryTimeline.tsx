import { useMemo } from 'react';
import { Icon, type IconName } from '@aunoo/ui';
import './visuals.css';

/*
 * How often detection runs have found a theme, as the old TrajectoryTimeline. The server keeps only
 * counts (total detections, the current streak, missed runs), not which run found it. The old bar
 * drew a run-by-run pattern made up at random from those counts. This one draws only what is known:
 * the earlier detections, the misses, and the current streak, each as one block in that order.
 */

interface TrajectoryTimelineProps {
  firstDetection: string;
  lastDetection: string;
  detectionCount: number;
  consecutiveDetections: number;
  missedRuns: number;
  /** rising / stable / declining / volatile */
  trajectory: string;
  className?: string;
}

const TRAJECTORY: Record<string, { icon: IconName; tone: string; label: string }> = {
  rising: { icon: 'TrendUp', tone: 'et-tone-up', label: 'Rising' },
  declining: { icon: 'ArrowDown', tone: 'et-tone-down', label: 'Declining' },
  volatile: { icon: 'Lightning', tone: 'et-tone-warn', label: 'Volatile' },
  stable: { icon: 'Minus', tone: 'et-tone-flat', label: 'Stable' },
};

const fmt = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
};

export function TrajectoryTimeline({ firstDetection, lastDetection, detectionCount, consecutiveDetections, missedRuns, trajectory, className }: TrajectoryTimelineProps) {
  const counts = useMemo(() => {
    const detected = Math.max(0, detectionCount || 0);
    const streak = Math.min(detected, Math.max(0, consecutiveDetections || 0));
    const missed = Math.max(0, missedRuns || 0);
    return { detected, streak, earlier: detected - streak, missed, total: detected + missed };
  }, [detectionCount, consecutiveDetections, missedRuns]);

  if (counts.total === 0 || counts.detected === 0) return null;
  const t = TRAJECTORY[trajectory] ?? TRAJECTORY.stable;
  const pct = (n: number) => `${(n / counts.total) * 100}%`;
  return (
    <div className={['et-traj', className].filter(Boolean).join(' ')}>
      <div className="et-traj__main">
        <div className="et-traj__dates">
          <span>First found {fmt(firstDetection)}</span>
          <span>Last found {fmt(lastDetection)}</span>
        </div>
        <div className="et-traj__bar" role="img" aria-label={`${counts.detected} of ${counts.total} runs found this theme; the last ${counts.streak} in a row`}>
          {counts.earlier > 0 && <span className="et-traj__seg et-traj__seg--earlier" style={{ width: pct(counts.earlier) }} />}
          {counts.missed > 0 && <span className="et-traj__seg et-traj__seg--missed" style={{ width: pct(counts.missed) }} />}
          {counts.streak > 0 && <span className="et-traj__seg et-traj__seg--streak" style={{ width: pct(counts.streak) }} />}
        </div>
        <div className="et-traj__stats">
          <span>Found in {counts.detected} of {counts.total} runs</span>
          {counts.streak > 1 && <span className="et-tone-up">the last {counts.streak} in a row</span>}
          {counts.missed > 0 && <span>{counts.missed} missed</span>}
        </div>
      </div>
      <span className={`et-traj__badge ${t.tone}`}>
        <Icon name={t.icon} size="sm" />
        {t.label}
      </span>
    </div>
  );
}

/** Compact version for card headers: detections, streak and the trajectory icon */
export function TrajectoryTimelineCompact({ detectionCount, consecutiveDetections, trajectory, className }: Pick<TrajectoryTimelineProps, 'detectionCount' | 'consecutiveDetections' | 'trajectory' | 'className'>) {
  const t = TRAJECTORY[trajectory] ?? TRAJECTORY.stable;
  return (
    <span className={['et-muted', className].filter(Boolean).join(' ')} aria-label={`Found ${detectionCount} times, ${consecutiveDetections} in a row, ${t.label.toLowerCase()}`}>
      {detectionCount}×
      {consecutiveDetections > 1 && <span className="et-tone-up">{consecutiveDetections} in a row</span>}
      <span className={t.tone}><Icon name={t.icon} size="sm" /></span>
    </span>
  );
}

export default TrajectoryTimeline;
