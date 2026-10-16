import { useId } from 'react';
import { Button } from './Button';
import { Chip } from './Chip';
import { Eyebrow } from './Eyebrow';
import { LineItems, type LineItemsItem, type LineItemsTotal } from './LineItems';
import { PriceDisplay } from './PriceDisplay';
import { StatusPill } from './StatusPill';
import { Text } from './Text';
import './PlanCard.css';

export interface PlanCardProps {
  eyebrow?: string;
  /** e.g. "Free" or "Free + add-ons" */
  planName: string;
  /** `{ label, tone }` — e.g. `{ label: 'Active' }` or `{ label: 'Trial · 30 days left', tone: 'accent' }` */
  status?: { label: string; tone?: 'live' | 'accent' | 'pending' };
  /** Pre-formatted, e.g. "$0" */
  price: string;
  period?: string;
  note?: React.ReactNode;
  /** Inclusion chips, e.g. ["3 topic slots", "8 MCP tools"] */
  includes?: string[];
  /** See LineItems `items`. */
  lineItems?: LineItemsItem[];
  /** See LineItems `total`. */
  total?: LineItemsTotal;
  /** `{ label, onClick, busy }` — the one primary action. */
  cta?: { label: React.ReactNode; onClick?: () => void; busy?: boolean };
  finePrint?: React.ReactNode;
  className?: string;
}

/**
 * Current plan summary: name, status, price, note and inclusions on the left;
 * itemised charges, one CTA and fine print on the right. Stacks under 1000px.
 */
export function PlanCard({
  eyebrow = 'Current plan',
  planName,
  status,
  price,
  period = '/month',
  note,
  includes = [],
  lineItems,
  total,
  cta,
  finePrint,
  className,
}: PlanCardProps) {
  const nameId = useId();
  return (
    <section className={['plan-card', className].filter(Boolean).join(' ')} aria-labelledby={nameId}>
      <div className="plan-card__main">
        <Eyebrow>{eyebrow}</Eyebrow>
        <div className="plan-card__head">
          <h2 id={nameId} className="plan-card__name">{planName}</h2>
          {status && (
            <StatusPill variant="muted" tone={status.tone ?? 'live'}>
              {status.label}
            </StatusPill>
          )}
        </div>
        <PriceDisplay amount={price} period={period} />
        {note && <Text variant="description" className="plan-card__note">{note}</Text>}
        {includes.length > 0 && (
          <ul className="plan-card__includes" aria-label="Included">
            {includes.map((item) => (
              <li key={item}><Chip tone="neutral">{item}</Chip></li>
            ))}
          </ul>
        )}
      </div>
      <div className="plan-card__side">
        {lineItems && <LineItems label="Monthly charges" items={lineItems} total={total} />}
        {cta && (
          <Button size="lg" fullWidth busy={cta.busy} onClick={cta.onClick} className="plan-card__cta">
            {cta.label}
          </Button>
        )}
        {finePrint && <Text variant="fine" align="center" className="plan-card__fine">{finePrint}</Text>}
      </div>
    </section>
  );
}
