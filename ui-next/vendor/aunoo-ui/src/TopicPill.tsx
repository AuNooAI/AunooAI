import { Icon } from './Icon';
import './TopicPill.css';

export interface TopicPillProps {
  label: string;
  selected?: boolean;
  /** e.g. "$3/mo" for a topic that costs extra. */
  priceTag?: string;
  /** Plain label, no toggle. */
  readOnly?: boolean;
  /** raised = translucent white fill, for pills on an inset areaBg block. */
  surface?: 'default' | 'raised';
  /** `(nextSelected) => void` */
  onToggle?: (nextSelected: boolean) => void;
  className?: string;
}

/**
 * Topic chip. Interactive by default: a toggle (`aria-pressed`) with a + / − icon.
 * `readOnly` renders a plain label. `surface="raised"` lifts it on an inset areaBg block.
 */
export function TopicPill({ label, selected = false, priceTag, readOnly = false, surface = 'default', onToggle, className }: TopicPillProps) {
  const classes = ['topic-pill', `topic-pill--${surface}`, readOnly && 'topic-pill--static', className].filter(Boolean).join(' ');
  const tag = priceTag && <span className="topic-pill__tag">{priceTag}</span>;

  if (readOnly) {
    return (
      <span className={classes} data-selected={selected || undefined}>
        {label}
        {tag}
      </span>
    );
  }

  return (
    <button
      type="button"
      className={classes}
      aria-pressed={selected}
      data-selected={selected || undefined}
      onClick={() => onToggle?.(!selected)}
    >
      <Icon name={selected ? 'Minus' : 'Plus'} size="sm" />
      {label}
      {tag}
    </button>
  );
}
