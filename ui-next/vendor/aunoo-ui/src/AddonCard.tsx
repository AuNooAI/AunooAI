import { useId } from 'react';
import { Button } from './Button';
import { Chip } from './Chip';
import { Icon } from './Icon';
import { PriceChip } from './PriceChip';
import { SettingRow } from './SettingRow';
import type { IconName } from './icons';
import './AddonCard.css';

const STATUS_CHIP: Record<string, { icon: IconName; label: string }> = {
  inTrial: { icon: 'Lightning', label: 'In trial' },
  added: { icon: 'Check', label: 'Added' },
};

export interface AddonCardProps {
  name: string;
  description?: React.ReactNode;
  /** Pre-formatted amount, e.g. "$19" */
  price: string;
  period?: string;
  status?: 'available' | 'inTrial' | 'added';
  layout?: 'card' | 'row';
  addLabel?: string;
  removeLabel?: string;
  /** `() => void` — Add clicked (available or in trial). */
  onAdd?: () => void;
  /** `() => void` — Remove clicked (added). */
  onRemove?: () => void;
  className?: string;
}

/**
 * A premium add-on and its status.
 * - `available`: primary Add
 * - `inTrial`: "In trial" chip + secondary Add
 * - `added`: "Added" chip + secondary Remove
 * `layout="card"` stacks vertically (Connection tab); `layout="row"` uses SettingRow (Billing tab).
 */
export function AddonCard({
  name,
  description,
  price,
  period = '/month',
  status = 'available',
  layout = 'card',
  addLabel = 'Add',
  removeLabel = 'Remove',
  onAdd,
  onRemove,
  className,
}: AddonCardProps) {
  const titleId = useId();
  const chip = STATUS_CHIP[status];

  const actions = (
    <>
      {chip && (
        <Chip tone="accent" icon={<Icon name={chip.icon} size="sm" />}>
          {chip.label}
        </Chip>
      )}
      {status === 'added' ? (
        <Button variant="secondary" onClick={onRemove} aria-describedby={titleId}>{removeLabel}</Button>
      ) : (
        <Button variant={status === 'available' ? 'primary' : 'secondary'} onClick={onAdd} aria-describedby={titleId}>
          {addLabel}
        </Button>
      )}
    </>
  );

  if (layout === 'row') {
    return (
      <SettingRow
        className={className}
        titleId={titleId}
        title={name}
        description={description}
        price={<PriceChip amount={price} period={period} />}
        actions={actions}
      />
    );
  }

  return (
    <div className={['addon-card', className].filter(Boolean).join(' ')} role="group" aria-labelledby={titleId}>
      <div id={titleId} className="addon-card__name">{name}</div>
      {description && <div className="addon-card__description">{description}</div>}
      <div className="addon-card__price">{price}{period}</div>
      <div className="addon-card__actions">{actions}</div>
    </div>
  );
}
