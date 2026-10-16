import './PriceDisplay.css';

export interface PriceDisplayProps {
  /** Pre-formatted amount, e.g. "$28" */
  amount: string;
  /** e.g. "/month" */
  period?: string;
  className?: string;
}

/** Large price figure (display size — prices and key figures only). Formatting is the caller's job. */
export function PriceDisplay({ amount, period, className }: PriceDisplayProps) {
  return (
    <div className={['price-display', className].filter(Boolean).join(' ')}>
      <span className="price-display__amount">{amount}</span>
      {period && <span className="price-display__period">{period}</span>}
    </div>
  );
}
