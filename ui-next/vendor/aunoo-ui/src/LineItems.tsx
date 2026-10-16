import './LineItems.css';

export interface LineItemsItem {
  id?: string;
  label: React.ReactNode;
  amount: React.ReactNode;
}

export interface LineItemsTotal {
  label: React.ReactNode;
  amount: React.ReactNode;
}

export interface LineItemsProps {
  /** `[{ id?, label, amount }]`, e.g. `{ label: 'Foresight', amount: '$19' }` */
  items: LineItemsItem[];
  /** `{ label, amount }`, e.g. `{ label: 'Billed monthly', amount: '$28' }` */
  total?: LineItemsTotal;
  /** Accessible name for the list, e.g. "Monthly charges". */
  label?: string;
  className?: string;
}

/** Itemised costs on an inset surface, with an optional bold total. Amounts are pre-formatted. */
export function LineItems({ items, total, label, className }: LineItemsProps) {
  return (
    <dl className={['line-items', className].filter(Boolean).join(' ')} aria-label={label}>
      {items.map((item, index) => (
        <div key={item.id ?? index} className="line-items__line">
          <dt>{item.label}</dt>
          <dd>{item.amount}</dd>
        </div>
      ))}
      {total && (
        <div className="line-items__line line-items__line--total">
          <dt>{total.label}</dt>
          <dd>{total.amount}</dd>
        </div>
      )}
    </dl>
  );
}
