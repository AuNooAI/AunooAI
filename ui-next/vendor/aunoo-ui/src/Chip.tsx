import './Chip.css';

export interface ChipProps {
  /** accent = pink status/paid tag · neutral = soft grey inclusion · muted = grey tag ·
   *  success / warning / info / error = status and signal tags (proposed tokens) */
  tone?: 'accent' | 'neutral' | 'muted' | 'success' | 'warning' | 'info' | 'error';
  /** outline = hairline border in the tone's colour, no fill (e.g. goal chips) */
  variant?: 'fill' | 'outline';
  /** md 26px chip · sm compact tag */
  size?: 'sm' | 'md';
  /** Optional leading icon, e.g. `<Icon name="Check" size="sm" />` */
  icon?: React.ReactNode;
  /** `() => void` — renders the chip as a button (e.g. click a tag to filter by it). */
  onClick?: () => void;
  /** Accessible name when the chip is a button, if the visible text isn't enough (e.g. "Filter by category: Other"). */
  label?: string;
  className?: string;
  children: React.ReactNode;
}

/** Static, non-interactive label: status ("Added", "In trial"), inclusions ("3 MCP tools") or tags ("Free", "$3/mo"). */
export function Chip({ tone = 'neutral', variant = 'fill', size = 'md', icon, onClick, label, className, children }: ChipProps) {
  const classes = ['chip', `chip--${tone}`, `chip--${size}`, variant === 'outline' && 'chip--outline', onClick && 'chip--button', className].filter(Boolean).join(' ');
  if (onClick) {
    return (
      <button type="button" className={classes} aria-label={label} onClick={onClick}>
        {icon}
        {children}
      </button>
    );
  }
  return (
    <span className={classes}>
      {icon}
      {children}
    </span>
  );
}
