import './TotalRow.css';

export interface TotalRowProps {
  /** e.g. "Estimated monthly total" or the free-quota explanation. */
  label: React.ReactNode;
  /** Pre-formatted total, e.g. "$6/month". */
  value: React.ReactNode;
  /** Summary above the value, e.g. "5 topics · 2 paid". Wrap the paid count in `<strong>` to tint it pink. */
  aside?: React.ReactNode;
  className?: string;
}

/** Divider + label on the left, bold total on the right, with optional summary text above the total. */
export function TotalRow({ label, value, aside, className }: TotalRowProps) {
  return (
    <div className={['total-row', className].filter(Boolean).join(' ')}>
      <span className="total-row__label">{label}</span>
      <div className="total-row__summary">
        {aside && <div className="total-row__aside">{aside}</div>}
        <div className="total-row__value">{value}</div>
      </div>
    </div>
  );
}
