import { Chip } from './Chip';
import { Icon } from './Icon';
import './TopicCard.css';

export interface TopicCardProps {
  name: string;
  description?: string;
  /** Decorative emoji before the name (hidden from screen readers). */
  emoji?: string;
  /** Tag text, e.g. "Free" or "$3/mo". */
  priceTag?: string;
  /** Style the tag as paid (pink). */
  paid?: boolean;
  selected?: boolean;
  disabled?: boolean;
  /** `(nextSelected) => void` */
  onToggle?: (nextSelected: boolean) => void;
  className?: string;
}

/** Selectable topic: emoji, name, description, price tag. A toggle button (`aria-pressed`). */
export function TopicCard({ name, description, emoji, priceTag, paid = false, selected = false, disabled = false, onToggle, className }: TopicCardProps) {
  return (
    <button
      type="button"
      className={['topic-card', className].filter(Boolean).join(' ')}
      aria-pressed={selected}
      disabled={disabled}
      data-selected={selected || undefined}
      onClick={() => onToggle?.(!selected)}
    >
      <span className="topic-card__head">
        {emoji && <span className="topic-card__emoji" aria-hidden="true">{emoji}</span>}
        <span className="topic-card__name">{name}</span>
        <span className="topic-card__check" aria-hidden="true">
          {selected && <Icon name="Check" size="md" />}
        </span>
      </span>
      {description && <span className="topic-card__description">{description}</span>}
      {priceTag && (
        <Chip size="sm" tone={paid ? 'accent' : 'muted'}>
          {priceTag}
        </Chip>
      )}
    </button>
  );
}
