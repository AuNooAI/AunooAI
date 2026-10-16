import { StatusDot } from './StatusDot';
import './ActivityRow.css';

export interface ActivityRowProps {
  /** Tool name ("search_news") or item name ("Arctic Shipping"). Truncates. */
  primary: React.ReactNode;
  /** Source or state, e.g. "Claude Desktop", "Awaiting price". */
  secondary?: React.ReactNode;
  /** Pre-formatted relative time, e.g. "2m ago". */
  timestamp?: string;
  /** Machine-readable ISO time for `<time dateTime>`. */
  dateTime?: string;
  /** live = served/connected · pending = awaiting · accent */
  dotTone?: 'live' | 'accent' | 'pending';
  /** Screen-reader text for the dot when `secondary` doesn't already say the status. */
  dotLabel?: string;
  /** Geist Mono primary text (machine names). */
  mono?: boolean;
  as?: 'div' | 'li';
  className?: string;
}

/**
 * One line in an activity list: dot, primary text, secondary text, timestamp.
 * `mono` sets the primary text in Geist Mono (tool calls). Render inside a `<ul>` with `as="li"`.
 */
export function ActivityRow({
  primary,
  secondary,
  timestamp,
  dateTime,
  dotTone = 'live',
  dotLabel,
  mono = false,
  as: Comp = 'div',
  className,
}: ActivityRowProps) {
  return (
    <Comp className={['activity-row', mono && 'activity-row--mono', className].filter(Boolean).join(' ')}>
      <StatusDot tone={dotTone} label={dotLabel} />
      <span className="activity-row__primary">{primary}</span>
      {secondary && <span className="activity-row__secondary">{secondary}</span>}
      {timestamp && (
        <time className="activity-row__time" dateTime={dateTime}>
          {timestamp}
        </time>
      )}
    </Comp>
  );
}
