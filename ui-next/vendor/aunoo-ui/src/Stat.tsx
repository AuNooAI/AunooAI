import './Stat.css';

export interface StatProps {
  /** What the figure is, e.g. "Total articles" or "San Francisco". */
  label: React.ReactNode;
  /** Pre-formatted figure, e.g. "242,129" or a `<time>`. */
  value: React.ReactNode;
  /** Line under the figure, e.g. "Oct 5". */
  meta?: React.ReactNode;
  /** Decorative icon on the right, e.g. `<Icon name="Newspaper" size="lg" />`. */
  icon?: React.ReactNode;
  /** display = key figure at 28px (§2.8 display) · compact = 14px, for dense grids */
  size?: 'display' | 'compact';
  /** Colour of the value (proposed status tokens). The label should still say what it means. */
  tone?: 'default' | 'success' | 'warning' | 'error' | 'info';
  /** Set the value in Geist Mono (times, ids). */
  mono?: boolean;
  /** Text values (e.g. a top category): wrap onto two lines, then ellipsis, instead of one long line. */
  wrapValue?: boolean;
  /** inset = areaBg block inside a Panel · panel = standalone translucent card on the area */
  surface?: 'inset' | 'panel';
  /** Small control after the label, e.g. an `<IconButton>` that clears what the figure counts. */
  action?: React.ReactNode;
  as?: 'div' | 'li';
  className?: string;
}

/** A labelled figure: key metric (display size) or a compact reading such as a world-clock time. */
export function Stat({
  label,
  value,
  meta,
  icon,
  size = 'display',
  mono = false,
  wrapValue = false,
  tone = 'default',
  surface = 'inset',
  action,
  as: Comp = 'div',
  className,
}: StatProps) {
  return (
    <Comp
      className={['stat', `stat--${size}`, `stat--${surface}`, mono && 'stat--mono', wrapValue && 'stat--wrap', tone !== 'default' && `stat--${tone}`, className]
        .filter(Boolean)
        .join(' ')}
    >
      <div className="stat__text">
        {action ? (
          <div className="stat__head">
            <div className="stat__label">{label}</div>
            {action}
          </div>
        ) : (
          <div className="stat__label">{label}</div>
        )}
        <div className="stat__value">{value}</div>
        {meta && <div className="stat__meta">{meta}</div>}
      </div>
      {icon && <div className="stat__icon">{icon}</div>}
    </Comp>
  );
}
