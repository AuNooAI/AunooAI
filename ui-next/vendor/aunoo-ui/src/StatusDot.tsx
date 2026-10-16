import './StatusDot.css';

export interface StatusDotProps {
  /** live = green (active, connected) · accent = pink (trial, updated) · pending = amber (awaiting) */
  tone?: 'live' | 'accent' | 'pending';
  /** Screen-reader text when there's no visible label next to the dot. */
  label?: string;
  className?: string;
}

/** Small status dot. Decorative next to a text label; pass `label` when the dot stands alone. */
export function StatusDot({ tone = 'live', label, className }: StatusDotProps) {
  return (
    <span className={['status-dot', `status-dot--${tone}`, className].filter(Boolean).join(' ')} aria-hidden={label ? undefined : true}>
      {label && <span className="visually-hidden">{label}</span>}
    </span>
  );
}
