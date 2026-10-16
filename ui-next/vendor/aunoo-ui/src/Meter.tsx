import './Meter.css';

export interface MeterProps {
  /** Accessible name, e.g. "Memory used". */
  label: string;
  /** Current amount, between `min` and `max`. */
  value: number;
  min?: number;
  max?: number;
  /** Pre-formatted reading shown next to the bar and read by screen readers, e.g. "74.1%". */
  valueText?: string;
  /** Fill colour. The reading text still states the value. */
  tone?: 'neutral' | 'success' | 'warning' | 'error';
  /** Task progress (e.g. generating) instead of a measured amount — announced as a progress bar. */
  progress?: boolean;
  /** Hide the visible reading (still announced). */
  hideValue?: boolean;
  className?: string;
}

/** Horizontal gauge for a measured amount (memory, disk, quota), or task progress with `progress`. */
export function Meter({ label, value, min = 0, max = 100, valueText, hideValue = false, tone = 'neutral', progress = false, className }: MeterProps) {
  const clamped = Math.min(Math.max(value, min), max);
  const ratio = max > min ? (clamped - min) / (max - min) : 0;
  return (
    <div className={['meter', tone !== 'neutral' && `meter--${tone}`, className].filter(Boolean).join(' ')}>
      <div
        className="meter__track"
        role={progress ? 'progressbar' : 'meter'}
        aria-label={label}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={clamped}
        aria-valuetext={valueText}
      >
        <div className="meter__fill" style={{ inlineSize: `${ratio * 100}%` }} />
      </div>
      {valueText && !hideValue && (
        <span className="meter__value" aria-hidden="true">{valueText}</span>
      )}
    </div>
  );
}
