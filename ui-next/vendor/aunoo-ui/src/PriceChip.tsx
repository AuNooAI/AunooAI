import './PriceChip.css';

export interface PriceChipProps {
  /** Pre-formatted amount, e.g. "$3" */
  amount: string;
  /** Muted suffix, e.g. "/month" or "/month each" */
  period?: string;
  className?: string;
}

/** Neutral price label ("$3/month each"). Not an action, so no accent (§5 rule 6). Formatting is the caller's job. */
export function PriceChip({ amount, period, className }: PriceChipProps) {
  return (
    <span className={['price-chip', className].filter(Boolean).join(' ')}>
      {amount}
      {period && <span className="price-chip__period">{period}</span>}
    </span>
  );
}
