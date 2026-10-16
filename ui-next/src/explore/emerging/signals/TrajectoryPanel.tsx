import { Panel, Text } from '@aunoo/ui';
import type { EmergingTopic } from './types';
import { formatDate } from './utils';
import './signals.css';

/*
 * Which of the recent days each theme was detected on, as the old TrajectoryPanel. The server
 * records only a theme's first and last detection dates and run counts, not every run. The old grid
 * filled the days in between as "detected", and alternated hits and misses when misses outnumbered
 * the streak: both made up. This one marks the first and last detection days as found, the days
 * between as "inside the detection window" (found on some of them, we can't say which), and the
 * rest as not detected.
 */

interface TrajectoryPanelProps {
  topics: EmergingTopic[];
  /** ISO dates for the columns, newest last (10 at most) */
  runDates: string[];
  onSelectTopic: (topic: EmergingTopic) => void;
}

type Cell = 'found' | 'window' | 'none';
const day = (iso: string | null) => (iso ? iso.slice(0, 10) : null);

function cells(topic: EmergingTopic, dates: string[]): Cell[] {
  const first = day(topic.first_detection_date ?? topic.first_detected_at);
  const last = day(topic.last_detection_date) ?? first;
  return dates.map((d) => {
    const k = d.slice(0, 10);
    if (!first || !last) return 'none';
    if (k === first || k === last) return 'found';
    return k > first && k < last ? 'window' : 'none';
  });
}

const CELL_TEXT: Record<Cell, string> = { found: 'detected', window: 'inside the detection window', none: 'not detected' };

export function TrajectoryPanel({ topics, runDates, onSelectTopic }: TrajectoryPanelProps) {
  const dates = runDates.slice(-10);
  const rows = topics.slice(0, 8);
  return (
    <Panel title="Detection trajectory" headingLevel={3} description="The top themes over the last few days.">
      {rows.length === 0 ? <Text variant="caption">No themes to show.</Text> : (
        <div className="sig-scroll">
          <table className="sig-traj">
            <caption className="visually-hidden">Detection by day for the top themes</caption>
            <thead>
              <tr>
                <th scope="col">Theme</th>
                {dates.map((d) => <th key={d} scope="col">{formatDate(d)}</th>)}
                <th scope="col">In a row</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => {
                const cs = cells(t, dates);
                return (
                  <tr key={t.id}>
                    <th scope="row">
                      <button type="button" className="text-link sig-traj__name" title={t.name} onClick={() => onSelectTopic(t)}>{t.name}</button>
                    </th>
                    {cs.map((c, i) => (
                      <td key={dates[i]}><span className={`sig-cell sig-cell--${c}`} role="img" aria-label={`${formatDate(dates[i])}: ${CELL_TEXT[c]}`} title={`${formatDate(dates[i])}: ${CELL_TEXT[c]}`} /></td>
                    ))}
                    <td>{t.consecutive_detections ?? 0}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <div className="sig-legend">
        <span><span className="sig-cell sig-cell--found" />First or last detection</span>
        <span><span className="sig-cell sig-cell--window" />Between them (some of these days)</span>
        <span><span className="sig-cell sig-cell--none" />Not detected</span>
      </div>
    </Panel>
  );
}
